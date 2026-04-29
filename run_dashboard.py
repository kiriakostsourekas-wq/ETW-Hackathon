#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ETW optimizer API and React dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for both local servers.")
    parser.add_argument("--api-port", type=int, default=8000, help="Python optimizer API port.")
    parser.add_argument("--ui-port", type=int, default=5173, help="Preferred Vite dashboard port.")
    parser.add_argument("--skip-api", action="store_true", help="Only start the React dashboard.")
    return parser.parse_args()


def api_is_healthy(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def stream_output(process: subprocess.Popen[str], label: str) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{label}] {line}", end="", flush=True)


def start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    label: str,
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=stream_output, args=(process, label), daemon=True)
    thread.start()
    return process


def terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.time() + 5
    for process in processes:
        remaining = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    args = parse_args()

    if not FRONTEND_DIR.exists():
        print(f"Missing frontend directory: {FRONTEND_DIR}", file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)

    def shutdown(signum: int, _frame) -> None:
        print("\nStopping dashboard servers...", flush=True)
        terminate(processes)
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        if args.skip_api:
            print("Skipping optimizer API startup.")
        elif api_is_healthy(args.host, args.api_port):
            print(f"Optimizer API already running at http://{args.host}:{args.api_port}")
        else:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "src")
            processes.append(
                start_process(
                    [
                        sys.executable,
                        "-m",
                        "batteryhack.api_server",
                        "--host",
                        args.host,
                        "--port",
                        str(args.api_port),
                    ],
                    cwd=ROOT,
                    env=env,
                    label="api",
                )
            )
            print(f"Starting optimizer API at http://{args.host}:{args.api_port}")

        env = os.environ.copy()
        env.setdefault("VITE_API_BASE", f"http://{args.host}:{args.api_port}")
        processes.append(
            start_process(
                ["npm", "run", "dev", "--", "--host", args.host, "--port", str(args.ui_port)],
                cwd=FRONTEND_DIR,
                env=env,
                label="ui",
            )
        )
        print(f"Starting dashboard. Open the Vite URL printed below, usually http://{args.host}:{args.ui_port}/")

        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    terminate([item for item in processes if item is not process])
                    return code
            time.sleep(0.25)
    finally:
        terminate(processes)


if __name__ == "__main__":
    raise SystemExit(main())
