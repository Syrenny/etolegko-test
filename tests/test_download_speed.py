import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from werkzeug.wrappers import Response

import download_speed as app


@pytest.fixture(autouse=True)
def bypass_local_proxy(monkeypatch):
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,::1")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1")


@pytest.fixture
def slow_download(httpserver):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def body():
        try:
            yield b"x"
            started.set()
            release.wait(5)
            yield b"y"
        finally:
            finished.set()

    httpserver.expect_request("/slow").respond_with_handler(
        lambda request: Response(body(), content_type="application/octet-stream")
    )
    try:
        yield httpserver.url_for("/slow"), started
    finally:
        release.set()
        if started.is_set():
            assert finished.wait(5), "response did not finish"


@pytest.mark.parametrize("kind", ["body", "no-length", "empty", "redirect"])
def test_full_downloads(httpserver, kind):
    body = b"x" * 150_000 if kind != "empty" else b""
    if kind == "no-length":
        httpserver.expect_request("/file").respond_with_handler(
            lambda request: Response(iter([body[:70_000], body[70_000:]]))
        )
    else:
        httpserver.expect_request("/file").respond_with_data(body)
    path = "/file"
    if kind == "redirect":
        httpserver.expect_request("/redirect").respond_with_data(
            status=302, headers={"Location": "/file"}
        )
        path = "/redirect"

    result = app.measure(httpserver.url_for(path), 2)

    assert result.total_bytes == len(body) * 10
    assert len(result.durations) == 10
    if kind == "empty":
        assert result.speed_mbps == 0
    if kind == "no-length":
        assert all("Content-Length" not in response.headers
                   for request, response in httpserver.log)
    assert all(duration > 0 for duration in result.durations)
    assert len(httpserver.log) == (20 if kind == "redirect" else 10)
    assert all(request.headers["Accept-Encoding"] == "identity"
               for request, response in httpserver.log)
    httpserver.check_assertions()


def test_known_calculation():
    result = app.Measurement(10_000_000, (0.5, 1.5) * 5)
    assert result.average_time == 1
    assert result.speed_mbps == 8
    with pytest.raises(ValueError, match="positive"):
        app.Measurement(1, (0.0,) * 10).speed_mbps


def test_cli_success(httpserver, capsys):
    body = b"x" * 100_000
    httpserver.expect_request("/file").respond_with_data(body)
    assert app.main([httpserver.url_for("/file")]) == 0
    out = capsys.readouterr()
    assert "10/10" in out.out
    assert f"({len(body) * 10} bytes)" in out.out
    assert "Mbps" in out.out
    assert out.err == ""


def assert_download_failed(capsys):
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Download failed:" in captured.err
    assert "Traceback" not in captured.err


def test_http_error_has_no_summary_or_retry(httpserver, capsys):
    httpserver.expect_request("/missing").respond_with_data(status=404)
    assert app.main([httpserver.url_for("/missing")]) == 1
    assert_download_failed(capsys)
    assert len(httpserver.log) == 1


def test_timeout_has_no_summary(slow_download, capsys):
    url, started = slow_download
    assert app.main([url, "--timeout", "0.1"]) == 1
    assert started.is_set()
    assert_download_failed(capsys)


@pytest.mark.parametrize("arguments", [
    ["ftp://example.com"], ["http:///path"], ["http://host:bad"],
    ["http://localhost", "--timeout", "0"],
    ["http://localhost", "--timeout", "-1"],
    ["http://localhost", "--timeout", "nan"],
    ["http://localhost", "--timeout", "inf"],
    ["http://localhost", "--timeout", "oops"],
])
def test_invalid_arguments(arguments, capsys):
    with pytest.raises(SystemExit) as error:
        app.main(arguments)
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_interrupt(monkeypatch, capsys):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(app, "measure", interrupt)
    assert app.main(["http://localhost"]) == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SIGINT" in captured.err


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal semantics required")
def test_sigterm_during_download(slow_download):
    url, started = slow_download
    command = [sys.executable, str(Path(app.__file__).resolve()), url]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        assert started.wait(5), "download did not start"
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 143
        assert stdout == ""
        assert "SIGTERM" in stderr
        assert "Traceback" not in stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


@pytest.mark.parametrize("status", [200, 404])
def test_interactive_progress(httpserver, monkeypatch, capsys, status):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    httpserver.expect_request("/file").respond_with_data(b"x" * 100_000, status=status)

    assert app.main([httpserver.url_for("/file")]) == (0 if status == 200 else 1)

    captured = capsys.readouterr()
    assert "Downloading 1/10" in captured.err
    assert "MiB received" in captured.err
    assert "Downloading" not in captured.out
    if status == 200:
        assert "Downloading 10/10" in captured.err
        assert "0.95 MiB received" in captured.err
        assert "Download speed:" in captured.out
        assert captured.err.endswith("\n")
    else:
        assert "\nDownload failed:" in captured.err
        assert captured.out == ""
