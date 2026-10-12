"""Auth tests for the local review servers (audit S4).

dashboard_server.py and sent_emails_review_server.py expose recipient
emails, full message bodies, and a CSV archive download. Every route
requires a valid workspace API key (header or ?api_key=), and both
servers bind loopback only.

Socket-free: handlers are faked with in-memory streams.

Run: python3 -m unittest discover -s deliverability/tests -p "test_*.py"
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from email.message import Message

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import dashboard_server as dash_mod
import sent_emails_review_server as review_mod
from core.repository import SlideInRepository


def get(handler_cls, path, headers=None):
    handler = handler_cls.__new__(handler_cls)
    handler.command = "GET"
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"GET {path} HTTP/1.1"
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    handler.headers = msg
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.client_address = ("127.0.0.1", 0)
    handler.do_GET()
    raw = handler.wfile.getvalue()
    head = raw.partition(b"\r\n\r\n")[0]
    status = int(head.split(b"\r\n")[0].decode("latin-1").split()[1])
    return status


class ReviewServerAuthTest(unittest.TestCase):
    MODULES = (
        (dash_mod, "/api/data"),
        (review_mod, "/api/emails"),
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = SlideInRepository(os.path.join(self.tmp.name, "ws.db"))
        self.api_key = self.repo.list_workspaces()[0].api_key
        self.db_path = os.path.join(self.tmp.name, "ws.db")
        for mod, _ in self.MODULES:
            patch = unittest.mock.patch.object(
                mod, "WORKSPACE_DB", self.db_path)
            patch.start()
            self.addCleanup(patch.stop)

    def test_routes_reject_missing_key(self):
        for mod, route in self.MODULES:
            with self.subTest(server=mod.__name__):
                self.assertEqual(get(mod.DashboardHandler, route), 401)

    def test_routes_reject_wrong_key(self):
        for mod, route in self.MODULES:
            with self.subTest(server=mod.__name__):
                status = get(mod.DashboardHandler, route,
                             {"X-API-Key": "sk_live_wrong"})
                self.assertEqual(status, 401)

    def test_routes_accept_header_key(self):
        for mod, route in self.MODULES:
            with self.subTest(server=mod.__name__):
                status = get(mod.DashboardHandler, route,
                             {"X-API-Key": self.api_key})
                self.assertEqual(status, 200)

    def test_routes_accept_query_key(self):
        for mod, route in self.MODULES:
            with self.subTest(server=mod.__name__):
                status = get(mod.DashboardHandler,
                             f"{route}?api_key={self.api_key}")
                self.assertEqual(status, 200)

    def test_index_requires_auth(self):
        for mod, _ in self.MODULES:
            with self.subTest(server=mod.__name__):
                self.assertEqual(get(mod.DashboardHandler, "/"), 401)

    def test_bind_loopback_only(self):
        self.assertEqual(dash_mod.HOST, "127.0.0.1")
        self.assertEqual(review_mod.HOST, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
