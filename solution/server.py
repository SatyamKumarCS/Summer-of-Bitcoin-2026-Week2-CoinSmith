#!/usr/bin/env python3
"""
Simple web server for the PSBT builder.
Serves the UI and exposes /api/health and /api/build.
"""
import json
import os
import sys
import tempfile
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from builder import build_transaction
from src.fixture import FixtureError
from src.coin_selection import InsufficientFundsError, MaxInputsExceededError
from src.report import build_error_report

PORT = int(os.environ.get("PORT", 3000))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # keep logs on stderr so they don't pollute stdout
        sys.stderr.write(f"[web] {fmt % args}\n")

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path, content_type="text/html"):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def do_GET(self):
        if self.path == "/api/health":
            self._json_response({"ok": True})
        elif self.path in ("/", "/index.html"):
            self._serve_file(os.path.join(STATIC, "index.html"))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/build":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            fixture_data = json.loads(raw)

            # write to a temp file so we can reuse the same builder logic
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
                json.dump(fixture_data, tmp)
                tmp_path = tmp.name

            try:
                report = build_transaction(tmp_path)
                self._json_response(report)
            finally:
                os.unlink(tmp_path)

        except FixtureError as e:
            self._json_response(build_error_report(e.code, e.message), 400)
        except (InsufficientFundsError, MaxInputsExceededError) as e:
            self._json_response(build_error_report("INSUFFICIENT_FUNDS", str(e)), 400)
        except json.JSONDecodeError as e:
            self._json_response(build_error_report("INVALID_JSON", str(e)), 400)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            self._json_response(build_error_report("INTERNAL_ERROR", str(e)), 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
