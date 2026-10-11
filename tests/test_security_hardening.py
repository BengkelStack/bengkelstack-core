import unittest
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.security import (
    verify_auth,
    RateLimiter,
    get_security_headers,
    MAX_PAYLOAD_SIZE,
    sanitize_input_str
)


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        # Save env var state
        self.orig_api_key = os.environ.get("BENGKELSTACK_API_KEY")

    def tearDown(self):
        if self.orig_api_key is not None:
            os.environ["BENGKELSTACK_API_KEY"] = self.orig_api_key
        else:
            os.environ.pop("BENGKELSTACK_API_KEY", None)

    def test_verify_auth_with_configured_token(self):
        os.environ["BENGKELSTACK_API_KEY"] = "super-secret-token-12345"
        
        # 1. Missing header -> 401
        ok, code, msg = verify_auth(headers={}, client_ip="127.0.0.1")
        self.assertFalse(ok)
        self.assertEqual(code, 401)

        # 2. Invalid header format -> 401
        ok, code, msg = verify_auth(headers={"Authorization": "Basic 12345"}, client_ip="127.0.0.1")
        self.assertFalse(ok)
        self.assertEqual(code, 401)

        # 3. Wrong token -> 401
        ok, code, msg = verify_auth(headers={"Authorization": "Bearer wrong-token"}, client_ip="127.0.0.1")
        self.assertFalse(ok)
        self.assertEqual(code, 401)

        # 4. Correct token -> 200
        ok, code, msg = verify_auth(headers={"Authorization": "Bearer super-secret-token-12345"}, client_ip="127.0.0.1")
        self.assertTrue(ok)
        self.assertEqual(code, 200)

    def test_verify_auth_loopback_fallback(self):
        os.environ.pop("BENGKELSTACK_API_KEY", None)
        
        # Local loopback client without token -> allowed in dev/offline mode
        ok, code, _ = verify_auth(headers={}, client_ip="127.0.0.1")
        self.assertTrue(ok)
        self.assertEqual(code, 200)

        # External IP without token -> 403 Forbidden
        ok, code, _ = verify_auth(headers={}, client_ip="192.168.1.100")
        self.assertFalse(ok)
        self.assertEqual(code, 403)

    def test_rate_limiter_sliding_window(self):
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)
        client_ip = "10.0.0.1"

        # First 5 requests should pass
        for _ in range(5):
            self.assertTrue(limiter.is_allowed(client_ip))

        # 6th request within window must be rejected
        self.assertFalse(limiter.is_allowed(client_ip))

        # Different client should pass
        self.assertTrue(limiter.is_allowed("10.0.0.2"))

    def test_security_headers_structure(self):
        headers = get_security_headers()
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn("Referrer-Policy", headers)

    def test_sanitize_input_str(self):
        raw = "  <script>alert('hack')</script> B 1234 XYZ  "
        clean = sanitize_input_str(raw)
        self.assertNotIn("<script>", clean)
        self.assertEqual(clean, "alert('hack') B 1234 XYZ")

    def test_live_server_security_flow(self):
        import urllib.request
        import urllib.error
        import threading
        from app.server import run_server

        test_port = 8991
        t = threading.Thread(target=run_server, args=(test_port,), daemon=True)
        t.start()
        
        # Poll for server readiness instead of fixed sleep
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/motor-models", timeout=1):
                    break
            except Exception:
                time.sleep(0.1)

        # 1. Normal GET local loopback without env token
        req = urllib.request.Request(f"http://127.0.0.1:{test_port}/api/motor-models")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
            self.assertIn("Content-Security-Policy", resp.headers)

        # 2. Oversized payload (413)
        oversized = b"A" * (MAX_PAYLOAD_SIZE + 100)
        req_over = urllib.request.Request(
            f"http://127.0.0.1:{test_port}/api/calculate",
            data=oversized,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req_over) as resp:
                self.fail("Expected 413 HTTPError or BrokenPipeError on oversized payload")
        except urllib.error.HTTPError as ctx:
            self.assertEqual(ctx.code, 413)
            ctx.close()
        except urllib.error.URLError:
            # Server immediately resets/terminates socket on oversized payload
            pass
        except (BrokenPipeError, ConnectionResetError):
            # On macOS/Unix TCP stack, socket termination before full send is a valid reject outcome
            pass


if __name__ == "__main__":
    unittest.main()
