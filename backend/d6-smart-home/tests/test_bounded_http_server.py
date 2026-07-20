import socket
import unittest
from http.server import BaseHTTPRequestHandler

try:
    from bounded_http_server import BoundedThreadingHTTPServer
except ImportError:
    BoundedThreadingHTTPServer = None


class QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, _format, *args):
        return


class BoundedHTTPServerTests(unittest.TestCase):
    def test_server_has_a_fixed_request_slot_limit(self):
        self.assertIsNotNone(BoundedThreadingHTTPServer)
        server = BoundedThreadingHTTPServer(
            ("127.0.0.1", 0), QuietHandler, max_workers=2,
            slot_acquire_timeout=0.01,
        )
        try:
            self.assertTrue(server._request_slots.acquire(blocking=False))
            self.assertTrue(server._request_slots.acquire(blocking=False))
            self.assertFalse(server._request_slots.acquire(blocking=False))
        finally:
            server.server_close()

    def test_full_server_rejects_connection_without_spawning_another_thread(self):
        self.assertIsNotNone(BoundedThreadingHTTPServer)
        server = BoundedThreadingHTTPServer(
            ("127.0.0.1", 0), QuietHandler, max_workers=1,
            slot_acquire_timeout=0.01,
        )
        accepted, peer = socket.socketpair()
        try:
            self.assertTrue(server._request_slots.acquire(blocking=False))
            server.process_request(accepted, ("127.0.0.1", 1))
            peer.settimeout(1)
            self.assertEqual(peer.recv(1), b"")
        finally:
            server._request_slots.release()
            peer.close()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
