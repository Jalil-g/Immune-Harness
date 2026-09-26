"""Run integration tests against an isolated, temporary local MongoDB replica set.

Requires mongod on PATH. Does not use or modify an existing MongoDB service.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Run the visible live demo locally")
    args = parser.parse_args()
    mongod = shutil.which("mongod")
    if not mongod:
        print("mongod is not installed. Use MONGODB_TEST_URI with Atlas instead.", file=sys.stderr)
        return 1
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="immune-harness-mongo-") as directory:
        log_path = Path(directory) / "mongod.log"
        with log_path.open("w") as output:
            process = subprocess.Popen(
                [
                    mongod,
                    "--replSet",
                    "immune_test",
                    "--bind_ip",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--dbpath",
                    directory,
                    "--quiet",
                    "--setParameter",
                    "diagnosticDataCollectionEnabled=false",
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            client = MongoClient(
                f"mongodb://127.0.0.1:{port}/?directConnection=true",
                serverSelectionTimeoutMS=500,
                connectTimeoutMS=500,
                socketTimeoutMS=2000,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Temporary mongod exited during startup")
                    try:
                        client.admin.command("ping")
                        break
                    except PyMongoError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.1)
                client.admin.command(
                    "replSetInitiate",
                    {
                        "_id": "immune_test",
                        "members": [{"_id": 0, "host": f"127.0.0.1:{port}"}],
                    },
                )
                while not client.admin.command("hello").get("isWritablePrimary"):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Temporary replica set did not elect a primary")
                    time.sleep(0.1)
                env = {
                    **os.environ,
                    "MONGODB_TEST_URI": f"mongodb://127.0.0.1:{port}/?replicaSet=immune_test",
                }
                if args.demo:
                    env["MONGODB_URI"] = env["MONGODB_TEST_URI"]
                    env["MONGODB_DB"] = "immune_local_demo"
                    print("LOCAL demonstration on a temporary replica set (not Atlas)", flush=True)
                    return subprocess.call(
                        [sys.executable, "scripts/live_demo.py"],
                        env=env,
                        cwd=Path(__file__).resolve().parent.parent,
                    )
                print(
                    "Running real MongoDB integration test in a temporary replica set", flush=True
                )
                return subprocess.call(
                    [sys.executable, "-m", "pytest", "-q", "-m", "integration"],
                    env=env,
                    cwd=Path(__file__).resolve().parent.parent,
                )
            except Exception:
                print(log_path.read_text()[-6000:], file=sys.stderr)
                raise
            finally:
                client.close()
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
