#!/usr/bin/env python3
"""MemCortex client -- dashboard host and API proxy.

This is the whole of the user-facing app. It does two things:

  1. serves the dashboard (a single self-contained page)
  2. forwards /api/* to a running MemCortex backend

The dashboard only ever calls relative "/api/..." paths, so it does not need
to know where the backend lives, and no frontend change is needed for the
split. Proxying rather than enabling CORS also means the identity session
cookie keeps working unchanged: the browser talks to one origin.

Standard library only, matching the backend's own approach. No framework.

Security properties, because this is the part that sits in front of an
authenticated API:

  * binds 127.0.0.1 unless MEMCORTEX_HOST says otherwise
  * forwards a fixed allowlist of request headers, so hop-by-hop headers and
    anything unexpected are dropped rather than relayed blindly
  * never logs Cookie or Authorization values, even at debug verbosity
  * refuses to start if the backend URL is not http(s)
  * does not follow redirects when proxying, so a backend that answers 302
    cannot bounce the caller to an arbitrary host

Run:  python3 bin/memcortex-client.py --backend http://127.0.0.1:8080
"""

import argparse
import json
import os
import posixpath
import ssl
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "dashboard"

# Only these are relayed. Cookie and Authorization carry the compartment
# credential and must survive; the rest is content negotiation.
FORWARD_REQUEST_HEADERS = (
    "cookie", "authorization", "content-type", "accept",
    "accept-language", "user-agent",
)
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}
MAX_BODY = 8 * 1024 * 1024  # the backend's own endpoints are all small


def log(msg):
    sys.stderr.write("[memcortex] %s\n" % msg)
    sys.stderr.flush()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "memcortex-client"

    # Set by main() once the backend URL is validated.
    backend = None

    # ---- dashboard ------------------------------------------------------
    def _serve_dashboard(self):
        body = (DASHBOARD / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The dashboard is static; it must never be served from a cache that
        # survives a redeploy, or a fixed client pins users to a stale build.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # deny everything: the dashboard needs no external origin, no inline
        # plugin, and no eval. It is a local tool served from loopback.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' "
            "'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ---- proxy ----------------------------------------------------------
    def _proxy(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._reply(413, json.dumps(
                {"error": "request body too large"}).encode(), "application/json")

        body = self.rfile.read(length) if length else None

        headers = {}
        for name in FORWARD_REQUEST_HEADERS:
            value = self.headers.get(name)
            if value:
                headers[name.title()] = value
        headers["X-Forwarded-For"] = self.client_address[0]

        url = self.backend.rstrip("/") + posixpath.normpath(path)
        if self.path.startswith("/api/") and "?" in self.path:
            url += "?" + self.path.split("?", 1)[1]

        req = urllib.request.Request(url, data=body, headers=headers,
                                     method=self.command)
        opener = urllib.request.build_opener(_NoRedirect)
        started = time.time()
        try:
            with opener.open(req, timeout=30) as resp:
                self._relay(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as e:
            # A 401/403 from the backend is a normal answer, not a proxy fault.
            self._relay(e.code, e.headers, e.read())
        except urllib.error.URLError as e:
            self._reply(502, json.dumps({
                "error": "backend unreachable",
                "detail": str(e.reason),
            }).encode(), "application/json")
        except Exception as e:  # noqa: BLE001 - never take the client down
            self._reply(502, json.dumps({
                "error": "backend error", "detail": str(e)}).encode(),
                "application/json")
        finally:
            # Method, path, status, duration. Never header values.
            log("%s %s -> %s (%.0fms)" % (self.command, path,
                                         getattr(self, "_status", "-"),
                                         (time.time() - started) * 1000))

    def _relay(self, status, headers, body):
        self._reply(status, body,
                    headers.get("Content-Type", "application/json"),
                    extra=headers)

    def _reply(self, status, body, ctype, extra=None):
        self._status = status
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra or {}).items():
            if name.lower() in HOP_BY_HOP:
                continue
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ---- verbs ----------------------------------------------------------
    def do_GET(self):
        self._route()

    def do_HEAD(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_PUT(self):
        self._route()

    def do_DELETE(self):
        self._route()

    def do_PATCH(self):
        self._route()

    def _route(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_dashboard()
        if path == "/healthz":
            return self._reply(200, json.dumps({"status": "ok"}).encode(),
                               "application/json")
        if path.startswith("/api/"):
            return self._proxy()
        # Anything else is an unknown path, not a directory to be walked.
        return self._reply(404, json.dumps({"error": "not found"}).encode(),
                           "application/json")

    def log_message(self, fmt, *a):
        pass  # replaced by the structured line in _proxy()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise urllib.error.HTTPError(
            a[0] if a else "", 307, "redirect refused by client proxy", {},
            None)


def main():
    ap = argparse.ArgumentParser(description="MemCortex dashboard and API proxy")
    ap.add_argument("--backend", default=os.environ.get("MEMCORTEX_BACKEND",
                                                        "http://127.0.0.1:8080"),
                    help="base URL of the running backend (default: %(default)s)")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("MEMCORTEX_PORT", "8095")))
    ap.add_argument("--host", default=os.environ.get("MEMCORTEX_HOST",
                                                     "127.0.0.1"))
    a = ap.parse_args()

    parsed = urlparse(a.backend)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        log("refusing to start: backend must be an http(s) URL, got %r"
            % a.backend)
        return 2
    if not (DASHBOARD / "index.html").is_file():
        log("dashboard/index.html missing; run from the repository root")
        return 2

    Handler.backend = a.backend.rstrip("/")
    log("dashboard on http://%s:%d -> backend %s" % (a.host, a.port,
                                                     Handler.backend))
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        log("WARNING: listening on %s, which is reachable off-host. The "
            "dashboard is unauthenticated and the API it proxies is not."
            % a.host)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("stopped")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
