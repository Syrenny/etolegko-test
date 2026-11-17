"""Measure sequential HTTP download throughput using the standard library."""

import argparse
from dataclasses import dataclass
from http.client import HTTPException
import math
import signal
import sys
from time import perf_counter
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


def measure(url: str, timeout: float) -> Measurement:
    total_bytes = 0
    durations = []
    for _ in range(REQUEST_COUNT):
        started = perf_counter()
        downloaded = 0
        request = Request(url, headers={"Accept-Encoding": "identity"})
        with urlopen(request, timeout=timeout) as response:
            while chunk := response.read(CHUNK_SIZE):
                downloaded += len(chunk)
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
        result = measure(args.url, args.timeout)
        speed = result.speed_mbps
        print(f"Requests:              {len(result.durations)}/{REQUEST_COUNT}")
        print(f"Total downloaded:      {result.total_bytes / 1_048_576:.2f} MiB ({result.total_bytes} bytes)")
        print(f"Average request time:  {result.average_time:.3f} s")
        print(f"Download speed:        {speed:.2f} Mbps")
        return 0
    except KeyboardInterrupt:
        print("Interrupted (SIGINT)", file=sys.stderr)
        return 130
    except Terminated:
        print("Terminated (SIGTERM)", file=sys.stderr)
        return 143
    except (URLError, HTTPException, OSError, ValueError) as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
