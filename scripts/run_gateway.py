from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LiteLLM Proxy with the receptionist routes.")
    parser.add_argument("--env-file", type=Path, default=ROOT / "gateway.env")
    parser.add_argument("--config", type=Path, default=ROOT / "litellm_config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4000)
    args = parser.parse_args()

    gateway_env_path = args.env_file.expanduser().resolve()
    if not gateway_env_path.is_file():
        raise SystemExit("Copy gateway.env.example to gateway.env and set the gateway key/provider key first.")

    env = os.environ.copy()
    env.update({key: value for key, value in dotenv_values(gateway_env_path).items() if value is not None})
    if not env.get("LITELLM_MASTER_KEY"):
        raise SystemExit("Set LITELLM_MASTER_KEY in gateway.env.")

    local_cli = Path(sys.executable).with_name("litellm")
    gateway_cli = str(local_cli if local_cli.exists() else shutil.which("litellm") or "litellm")
    command = [
        gateway_cli,
        "--config",
        str(args.config.expanduser().resolve()),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    raise SystemExit(subprocess.call(command, cwd=ROOT, env=env))


if __name__ == "__main__":
    main()
