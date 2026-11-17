"""Measure sequential HTTP download throughput using the standard library."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPException
import math
import os
import signal
import sys
from time import perf_counter
from typing import TextIO
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

__version__ = "0.1.0"
REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class Measurement:
    total_bytes: int
    durations: tuple[float, ...]

    @property
    def average_time(self) -> float:
        return sum(self.durations) / len(self.durations)

    @property
    def speed_mbps(self) -> float:
        elapsed = sum(self.durations)
        if elapsed <= 0:
            raise ValueError("Measured duration must be positive")
        return self.total_bytes * 8 / elapsed / 1_000_000


def http_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("expected an HTTP or HTTPS URL with a host")
        parsed.port
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return value


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return timeout


def colored(text: str, code: str, stream: TextIO) -> str:
    if stream.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb":
        return f"\033[{code}m{text}\033[0m"
    return text


class Progress:
    """Display throttled progress only on an interactive stderr."""

    def __init__(self) -> None:
        self.enabled = sys.stderr.isatty()
        self.request_number = 0
        self.total_bytes = 0
        self.last_update = 0.0
        self.width = 0

    def __call__(self, request_number: int, total_bytes: int) -> None:
        new_request = request_number != self.request_number
        self.request_number = request_number
        self.total_bytes = total_bytes
        if self.enabled:
            now = perf_counter()
            if new_request or now - self.last_update >= 0.2:
                self.render()
                self.last_update = now

    def render(self) -> None:
        line = (f"Downloading {self.request_number}/{REQUEST_COUNT} · "
                f"{self.total_bytes / 1_048_576:.2f} MiB received")
        self.width = max(self.width, len(line))
        print(f"\r{line:<{self.width}}", end="", file=sys.stderr, flush=True)

    def finish(self) -> None:
        if self.enabled and self.request_number:
            self.render()
            print(file=sys.stderr, flush=True)


def measure(
    url: str,
    timeout: float,
    progress: Callable[[int, int], None] | None = None,
) -> Measurement:
    total_bytes = 0
    durations = []
    for request_number in range(1, REQUEST_COUNT + 1):
        if progress is not None:
            progress(request_number, total_bytes)
        started = perf_counter()
        downloaded = 0
        request = Request(url, headers={"Accept-Encoding": "identity"})
        with urlopen(request, timeout=timeout) as response:
            while chunk := response.read(CHUNK_SIZE):
                downloaded += len(chunk)
                if progress is not None:
                    progress(request_number, total_bytes + downloaded)
            # HTTPResponse handles chunked framing; Content-Length applies otherwise.
            if not response.chunked:
                length = response.headers.get("Content-Length")
                if length is not None and downloaded < int(length):
                    raise ValueError("Incomplete response body")
        durations.append(perf_counter() - started)
        total_bytes += downloaded
    return Measurement(total_bytes, tuple(durations))


class Terminated(BaseException):
    """Interrupt a download without treating termination as a network failure."""


def handle_sigterm(signum, frame):
    raise Terminated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=http_url, help="HTTP or HTTPS resource to download ten times")
    parser.add_argument("--timeout", type=positive_timeout, default=30.0,
                        metavar="SECONDS", help="network operation timeout (default: 30)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    previous_handler = signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        progress = Progress()
        try:
            result = measure(args.url, args.timeout, progress=progress)
        finally:
            progress.finish()
        speed = result.speed_mbps
        print(f"Requests:              {len(result.durations)}/{REQUEST_COUNT}")
        print(f"Total downloaded:      {result.total_bytes / 1_048_576:.2f} MiB ({result.total_bytes} bytes)")
        print(f"Average request time:  {result.average_time:.3f} s")
        print("Download speed:        " + colored(f"{speed:.2f} Mbps", "32", sys.stdout))
        return 0
    except KeyboardInterrupt:
        print(colored("Interrupted (SIGINT)", "31", sys.stderr), file=sys.stderr)
        return 130
    except Terminated:
        print(colored("Terminated (SIGTERM)", "31", sys.stderr), file=sys.stderr)
        return 143
    except (URLError, HTTPException, OSError, ValueError) as error:
        print(colored(f"Download failed: {error}", "31", sys.stderr), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
