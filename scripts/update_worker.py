#!/usr/bin/env python3
"""Update the Cloudflare Worker with the current contract from .env."""

import os
import re
import subprocess
import sys
from pathlib import Path


def load_env() -> dict:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print(f"Error: .env not found at {env_path}")
        sys.exit(1)

    result = {}
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def validate_address(addr: str | None) -> str:
    if not addr:
        print("Error: KINGOFTHEHILL_ADDRESS is not set in .env")
        sys.exit(1)
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", addr):
        print(f"Error: KINGOFTHEHILL_ADDRESS does not look like a valid address: {addr}")
        sys.exit(1)
    return addr


def run(cmd: list[str], *, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=Path(__file__).parent,
        input=stdin,
        text=False,
        capture_output=True,
        check=True,
    )


def main() -> None:
    env = load_env()
    addr = validate_address(env.get("KINGOFTHEHILL_ADDRESS"))
    rpc_url = env.get("ALCHEMY_RPC_URL")
    account_id = env.get("CLOUDFLARE_ACCOUNT_ID")

    if not rpc_url:
        print("Error: ALCHEMY_RPC_URL is not set in .env")
        sys.exit(1)
    if not account_id:
        print("Error: CLOUDFLARE_ACCOUNT_ID is not set in .env")
        sys.exit(1)

    # Wrangler reads these from the environment.
    os.environ["CLOUDFLARE_API_TOKEN"] = env.get("CLOUDFLARE_API_TOKEN", "")
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = account_id

    if not os.environ["CLOUDFLARE_API_TOKEN"]:
        print("Error: CLOUDFLARE_API_TOKEN is not set in .env")
        sys.exit(1)

    print(f"Updating worker for contract: {addr}\n")

    run(["npx", "wrangler", "secret", "put", "KINGOFTHEHILL_ADDRESS"], stdin=addr.encode())
    run(["npx", "wrangler", "secret", "put", "ALCHEMY_RPC_URL"], stdin=rpc_url.encode())
    run(["npx", "wrangler", "deploy"])

    print("\nWorker updated successfully.")
    print(f"New contract address: {addr}")


if __name__ == "__main__":
    main()
