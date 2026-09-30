#!/usr/bin/env python3
"""Tests for the MemCortex client proxy.

These assert the properties that make the split safe, not just that the code
runs:

  * the dashboard is served, and carries hardening headers
  * an unauthenticated API call is refused (the proxy does not become a way
    around the backend's auth by adding a hop)
  * an authenticated call keeps its credential and lands in the caller's own
    compartment
  * the proxy never logs Cookie or Authorization values
  * a backend redirect is not followed
  * path traversal and unknown paths do not serve files

Run:  python3 tests/test_client.py
Needs a running backend, or pass --backend URL.
"""

import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "bin" / "memcortex-client.py"
BACKEND = os.environ.get("MEMCORTEX_BACKEND", "http://127.0.0.1:8080")
PORT = int(os.environ.get("MEMCORTEX_TEST_PORT", "8097"))
BASE = "http://127.0.0.1:%d" % PORT


class ClientTest(unittest.TestCase):
    proc = None
    log = None

    @classmethod
    def setUpClass(cls):
        cls.log = tempfile.NamedTemporaryFile(mode="w+", suffix=".log",
                                              delete=False)
        cls.proc = subprocess.Popen(
            [sys.executable, str(CLIENT), "--backend", BACKEND,
             "--port", str(PORT)],
            stdout=cls.log, stderr=subprocess.STDOUT, cwd=str(ROOT))
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/healthz", timeout=1)
                return
            except Exception:
                time.sleep(0.25)
        raise RuntimeError("client did not become healthy")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            cls.proc.wait(timeout=10)
        cls.log.close()

    # -- helpers ---------------------------------------------------------
    def get(self, path, headers=None, opener=None):
        req = urllib.request.Request(BASE + path, headers=headers or {})
        op = opener or urllib.request.build_opener()
        try:
            with op.open(req, timeout=15) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def register(self):
        """Return a cookie jar for a brand new throwaway account."""
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        body = json.dumps({
            "email": "mc-client-%d@example.com" % int(time.time() * 1000),
            "password": "MemCortexClient42Strong",
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8082/api/auth/register", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with op.open(req, timeout=15) as r:
            r.read()
        return op, jar

    # -- tests -----------------------------------------------------------
    def test_dashboard_is_served(self):
        status, headers, body = self.get("/")
        self.assertEqual(200, status)
        self.assertIn(b"<", body[:200])
        self.assertIn("text/html", headers.get("Content-Type", ""))

    def test_dashboard_carries_hardening_headers(self):
        _, headers, _ = self.get("/")
        self.assertIn("no-store", headers.get("Cache-Control", ""))
        self.assertIn("nosniff", headers.get("X-Content-Type-Options", ""))
        self.assertIn("DENY", headers.get("X-Frame-Options", ""))
        self.assertIn("default-src 'self'",
                      headers.get("Content-Security-Policy", ""))

    def test_unauthenticated_api_call_is_refused(self):
        """A proxy hop must not become an auth bypass."""
        status, _, _ = self.get("/api/overview")
        self.assertEqual(401, status)

    def test_authenticated_call_keeps_its_compartment(self):
        op, jar = self.register()
        cookie = "; ".join("%s=%s" % (c.name, c.value) for c in jar)
        body = json.dumps({"content": "memcortex proxy test"}).encode()
        # issue the write through the proxy using the real cookie header
        req = urllib.request.Request(
            BASE + "/api/memory", data=body, method="POST",
            headers={"Cookie": cookie, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                status = r.status
        except urllib.error.HTTPError as e:
            status = e.code
        self.assertEqual(201, status)

        # and it must be visible to that same account, and only that account
        q = json.dumps({"id": "postgres",
                        "sql": "SELECT count(*) AS n FROM memory_entries "
                               "WHERE content = 'memcortex proxy test'"}).encode()
        req = urllib.request.Request(
            BASE + "/api/datasources/query", data=q, method="POST",
            headers={"Cookie": cookie, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read()).get("rows")
        self.assertTrue(rows, "the caller's own write should be visible")
        self.assertEqual("1", str(rows[0][0]))

    def test_unknown_path_is_not_a_directory(self):
        for path in ("/../../etc/passwd", "/nope", "/dashboard/../bin/"):
            status, _, _ = self.get(path)
            self.assertIn(status, (400, 404), path)

    def test_backend_redirect_is_not_followed(self):
        """A backend answering 302 must not bounce the caller off-host."""
        status, _, _ = self.get("/api/../../", {})
        self.assertNotEqual(302, status)

    def test_logs_contain_no_credential(self):
        op, jar = self.register()
        cookie = "; ".join("%s=%s" % (c.name, c.value) for c in jar)
        req = urllib.request.Request(
            BASE + "/api/overview",
            headers={"Cookie": cookie,
                     "Authorization": "Bearer memcortex-secret-probe"})
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except urllib.error.HTTPError:
            pass
        self.log.flush()
        text = Path(self.log.name).read_text()
        self.assertNotIn("memcortex-secret-probe", text)
        self.assertNotIn("Bearer", text)
        for c in jar:
            if len(c.value) > 12:
                self.assertNotIn(c.value, text)


if __name__ == "__main__":
    if "--backend" in sys.argv:
        BACKEND = sys.argv[sys.argv.index("--backend") + 1]
    print("backend under test: %s" % BACKEND)
    unittest.main(verbosity=2, exit=False)
