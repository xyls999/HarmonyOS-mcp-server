"""Thread-bounded HTTP server for resource-constrained gateway devices."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Reject excess connections before they can allocate request threads."""

    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(
        self,
        server_address,
        request_handler_class,
        *,
        max_workers: int = 64,
        slot_acquire_timeout: float = 0.25,
    ):
        self.max_workers = max(1, int(max_workers))
        self.slot_acquire_timeout = max(0.0, float(slot_acquire_timeout))
        self._request_slots = threading.BoundedSemaphore(self.max_workers)
        super().__init__(server_address, request_handler_class)

    def process_request(self, request, client_address):
        acquired = self._request_slots.acquire(timeout=self.slot_acquire_timeout)
        if not acquired:
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()
