#!/usr/bin/env python3
"""
Static site server with a same-origin RPC proxy.

Reads the Alchemy RPC URL from the environment so it never ships to the
browser.  The frontend calls /api/rpc; this server forwards the request to
Alchemy and returns the raw JSON-RPC response.
"""

import json
import os
import socketserver
import sys
import urllib.error
import urllib.request
from http import server
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env from the project root (two levels up from scripts/serve_site.py).
# override=True ensures the file always wins over inherited shell env vars.
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

SITE_DIR = Path(__file__).parent.parent / "site"
PORT = int(os.environ.get("SITE_PORT", "8080"))

# Server-side secrets: never sent to the frontend.
RPC_URL = os.environ.get("ALCHEMY_RPC_URL")
# The live site reuses the deploy script's KINGOFTHEHILL_ADDRESS as the contract address.
CONTRACT_ADDRESS = os.environ.get("KINGOFTHEHILL_ADDRESS")
CHAIN_ID = int(os.environ.get("CHAIN_ID", "11155111"))


def _is_configured() -> tuple[bool, str]:
    if not RPC_URL:
        return False, "ALCHEMY_RPC_URL not set in .env"
    if not CONTRACT_ADDRESS:
        return False, "KINGOFTHEHILL_ADDRESS not set in .env"
    return True, ""


def serve(port: int):
    configured, reason = _is_configured()
    if not configured:
        print(f"Warning: {reason}; /api/rpc will return an error.", file=sys.stderr)
        print("The static site will still serve and the frontend will fall back to mock data.", file=sys.stderr)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving site at http://0.0.0.0:{port}")
        print(f"Proxying /api/rpc -> {RPC_URL.split('?')[0] if RPC_URL else '<not configured>'}")
        httpd.serve_forever()


class Handler(server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def end_headers(self):
        # Allow cross-origin requests during local development. The proxy is
        # only reachable where the server is running, so this is low risk.
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/config":
            self._send_json(
                {
                    "contractAddress": CONTRACT_ADDRESS,
                    "chainId": CHAIN_ID,
                    "rpcProxyUrl": "/api/rpc",
                }
            )
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/rpc":
            configured, reason = _is_configured()
            if not configured:
                self._send_json({"jsonrpc": "2.0", "error": {"code": -32000, "message": reason}}, status=500)
                return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                req = urllib.request.Request(
                    RPC_URL,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    out = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)
            except urllib.error.HTTPError as exc:
                self.send_response(exc.code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(exc.read())
            return

        self.send_error(404)

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Suppress per-request access logs to keep background-task output small.
        pass


@click.command()
@click.option(
    "--port",
    envvar="SITE_PORT",
    default=PORT,
    show_default=True,
    type=int,
    help="Local HTTP port.",
)
def cli(port: int):
    serve(port)


if __name__ == "__main__":
    cli()
