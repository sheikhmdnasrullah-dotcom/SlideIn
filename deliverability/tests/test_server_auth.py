"""Auth tests for deliverability/server.py (audit S2).

Every /v1/* route except /health requires a valid workspace API key.
No-key and wrong-key requests are rejected with 401 BEFORE any state
change or send. /v1/workspaces never exposes key material.

Socket-free: the handler instance is faked with in-memory streams so the
suite runs anywhere (no loopback bind needed).

Run: python3 -m unittest discover -s deliverability/tests -p "test_*.py"
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import server as server_mod
from core.models import Conversation, Workspace
from core.models import Message as ChatMessage
from core.repository import SlideInRepository


def make_handler(repo, method="GET", path="/", headers=None, body=b""):
    """Build a SlideInAPIHandler without a socket."""
    handler = server_mod.SlideInAPIHandler.__new__(server_mod.SlideInAPIHandler)
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.headers = Message()
    for key, value in (headers or {}).items():
        handler.headers[key] = value
    if body:
        handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.client_address = ("127.0.0.1", 0)
    server_mod.repo = repo
    return handler


def send(handler):
    if handler.command == "GET":
        handler.do_GET()
    elif handler.command == "POST":
        handler.do_POST()
    else:
        raise AssertionError(f"unsupported method {handler.command}")
    raw = handler.wfile.getvalue()
    head, _, response_body = raw.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n")[0].decode("latin-1")
    status = int(status_line.split()[1])
    return status, response_body


class ServerAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = SlideInRepository(os.path.join(self.tmp.name, "auth_test.db"))
        self.addCleanup(setattr, server_mod, "repo", server_mod.repo)
        workspaces = self.repo.list_workspaces()
        self.assertGreaterEqual(len(workspaces), 1)
        self.ws_id = workspaces[0].id
        self.api_key = workspaces[0].api_key

    def get(self, path, headers=None):
        return send(make_handler(self.repo, "GET", path, headers))

    def post(self, path, payload, headers=None):
        body = json.dumps(payload).encode("utf-8")
        all_headers = {"Content-Type": "application/json"}
        all_headers.update(headers or {})
        return send(make_handler(self.repo, "POST", path, all_headers, body))

    def test_status_rejects_missing_key(self):
        status, body = self.get("/v1/status")
        self.assertEqual(status, 401)
        self.assertIn("error", json.loads(body))

    def test_status_rejects_wrong_key(self):
        status, _ = self.get("/v1/status", {"X-API-Key": "sk_live_wrong_key"})
        self.assertEqual(status, 401)

    def test_status_accepts_api_key_header(self):
        status, body = self.get("/v1/status", {"X-API-Key": self.api_key})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["workspace_id"], self.ws_id)

    def test_status_accepts_bearer_header(self):
        status, body = self.get(
            "/v1/status", {"Authorization": f"Bearer {self.api_key}"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["workspace_id"], self.ws_id)

    def test_workspaces_requires_auth(self):
        status, _ = self.get("/v1/workspaces")
        self.assertEqual(status, 401)

    def test_workspaces_redacts_key_material(self):
        status, body = self.get("/v1/workspaces", {"X-API-Key": self.api_key})
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertNotIn(self.api_key, text)
        self.assertNotIn("api_key", text)
        self.assertIn(self.ws_id, text)

    def test_lead_submit_rejects_unauthenticated_without_side_effects(self):
        status, _ = self.post("/v1/leads/submit", {"email": "prospect@example.com"})
        self.assertEqual(status, 401)
        self.assertIsNone(self.repo.get_lead_by_email(self.ws_id, "prospect@example.com"))

    def test_reply_rejects_unauthenticated(self):
        status, _ = self.post(
            "/v1/conversations/conv_missing/reply", {"body_text": "hello"}
        )
        self.assertEqual(status, 401)

    def test_draft_score_rejects_unauthenticated(self):
        status, _ = self.post("/v1/drafts/score", {"subject": "hi", "body_text": "x"})
        self.assertEqual(status, 401)

    def test_health_stays_public(self):
        status, _ = self.get("/health")
        self.assertEqual(status, 200)

    def test_unknown_path_stays_404(self):
        status, _ = self.get("/v1/no-such-endpoint")
        self.assertEqual(status, 404)


class CrossWorkspaceTest(unittest.TestCase):
    """Conversation-by-ID lookups are scoped to the caller's workspace.

    Cross-workspace IDs answer 404 (never the other tenant's data), and
    inbound thread matching never attaches to another workspace's thread.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = SlideInRepository(os.path.join(self.tmp.name, "xws_test.db"))
        self.addCleanup(setattr, server_mod, "repo", server_mod.repo)
        default_ws = self.repo.list_workspaces()[0]
        self.key_a = default_ws.api_key
        self.ws_b = Workspace(id="ws_b_01", slug="b", name="Workspace B")
        self.repo.save_workspace(self.ws_b)
        self.key_b = self.ws_b.api_key
        self.conv_b = Conversation(
            id="conv_b_01",
            workspace_id=self.ws_b.id,
            lead_email="b-lead@example.com",
            subject="B thread",
            thread_root_msg_id="<root-b@example.com>",
        )
        self.repo.save_conversation(self.conv_b)
        self.repo.save_message(
            ChatMessage(
                id="msg_b_root",
                conversation_id=self.conv_b.id,
                workspace_id=self.ws_b.id,
                message_id_header="<root-b@example.com>",
            )
        )

    def get(self, path, headers=None):
        return send(make_handler(self.repo, "GET", path, headers))

    def post(self, path, payload, headers=None):
        body = json.dumps(payload).encode("utf-8")
        all_headers = {"Content-Type": "application/json"}
        all_headers.update(headers or {})
        return send(make_handler(self.repo, "POST", path, all_headers, body))

    def test_single_conversation_cross_workspace_is_404(self):
        status, body = self.get(
            f"/v1/conversations/{self.conv_b.id}", {"X-API-Key": self.key_a}
        )
        self.assertEqual(status, 404)
        self.assertNotIn("B thread", body.decode("utf-8"))

    def test_single_conversation_own_workspace_ok(self):
        status, body = self.get(
            f"/v1/conversations/{self.conv_b.id}", {"X-API-Key": self.key_b}
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["conversation"]["id"], self.conv_b.id)

    def test_reply_cross_workspace_is_404_without_side_effects(self):
        before = self.repo.get_conversation(self.conv_b.id).message_count
        status, _ = self.post(
            f"/v1/conversations/{self.conv_b.id}/reply",
            {"body_text": "intruder reply"},
            {"X-API-Key": self.key_a},
        )
        self.assertEqual(status, 404)
        after = self.repo.get_conversation(self.conv_b.id)
        self.assertEqual(after.message_count, before)

    def test_inbound_thread_match_ignores_other_workspace(self):
        # in_reply_to references workspace B's thread root, but the caller
        # authenticates as workspace A: the inbound mail must NOT attach to
        # (or mutate) workspace B's conversation.
        before = self.repo.get_conversation(self.conv_b.id).message_count
        status, body = self.post(
            "/v1/inbound/webhook",
            {
                "from_addr": "stranger@example.com",
                "subject": "Re: B thread",
                "body_text": "Not interested, please stop contacting me.",
                "in_reply_to": "<root-b@example.com>",
            },
            {"X-API-Key": self.key_a},
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(json.loads(body)["conversation_id"], self.conv_b.id)
        self.assertEqual(
            self.repo.get_conversation(self.conv_b.id).message_count, before
        )


class WorkspaceKeyTest(unittest.TestCase):
    """Seed keys are random per database and rotatable (audit S5)."""

    def test_fresh_databases_get_unique_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            key1 = SlideInRepository(
                os.path.join(tmp, "a.db")).list_workspaces()[0].api_key
            key2 = SlideInRepository(
                os.path.join(tmp, "b.db")).list_workspaces()[0].api_key
        self.assertTrue(key1.startswith("sk_live_"))
        self.assertGreaterEqual(len(key1), 40)
        self.assertNotEqual(key1, key2)

    def test_no_hardcoded_seed_key_in_repository_source(self):
        import core.repository as repo_mod

        source = open(repo_mod.__file__, encoding="utf-8").read()
        self.assertNotIn("sk_live_slidein", source)

    def test_rotation_invalidates_old_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = SlideInRepository(os.path.join(tmp, "r.db"))
            old_key = repo.list_workspaces()[0].api_key
            new_key = repo.rotate_workspace_key("default")
        self.assertNotEqual(old_key, new_key)
        server_mod.repo = repo
        self.addCleanup(setattr, server_mod, "repo", server_mod.repo)
        status_old, _ = send(
            make_handler(repo, "GET", "/v1/status", {"X-API-Key": old_key}))
        status_new, body = send(
            make_handler(repo, "GET", "/v1/status", {"X-API-Key": new_key}))
        self.assertEqual(status_old, 401)
        self.assertEqual(status_new, 200)
        self.assertEqual(json.loads(body)["workspace_id"], "ws_default_01")

    def test_rotation_unknown_workspace_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = SlideInRepository(os.path.join(tmp, "r.db"))
            with self.assertRaises(KeyError):
                repo.rotate_workspace_key("ws_missing")


class LeadSubmitEligibilityTest(unittest.TestCase):
    """POST /v1/leads/submit enforces suppression and breaker state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = SlideInRepository(os.path.join(self.tmp.name, "sub.db"))
        self.addCleanup(setattr, server_mod, "repo", server_mod.repo)
        server_mod.repo = self.repo
        self.api_key = self.repo.list_workspaces()[0].api_key
        from core import state as st_mod

        self.store = st_mod.Store(os.path.join(self.tmp.name, "state.db"))
        store_patch = mock.patch.object(
            server_mod.st, "Store", return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)

    def submit(self, email, headers=None):
        body = json.dumps({"email": email}).encode("utf-8")
        all_headers = {"Content-Type": "application/json"}
        all_headers.update(headers or {})
        return send(make_handler(self.repo, "POST", "/v1/leads/submit",
                                 all_headers, body))

    def test_suppressed_recipient_rejected_without_side_effects(self):
        self.store.suppress("opted-out@example.com", "unsubscribe")
        with mock.patch.object(
                server_mod, "ConversationalEngine") as engine_cls:
            status, _ = self.submit(
                "opted-out@example.com", {"X-API-Key": self.api_key})
        self.assertEqual(status, 403)
        engine_cls.assert_not_called()
        self.assertIsNone(
            self.repo.get_lead_by_email("ws_default_01",
                                        "opted-out@example.com"))

    def test_open_breaker_rejected_without_side_effects(self):
        self.store.set_circuit("open", "test trip", {})
        with mock.patch.object(
                server_mod, "ConversationalEngine") as engine_cls:
            status, _ = self.submit(
                "fresh@example.com", {"X-API-Key": self.api_key})
        self.assertEqual(status, 503)
        engine_cls.assert_not_called()
        self.assertIsNone(
            self.repo.get_lead_by_email("ws_default_01", "fresh@example.com"))

    def test_eligible_submit_still_sends(self):
        engine = mock.Mock()
        engine.generate_speed_to_lead_email.return_value = (
            "Subj", "text", "<p>html</p>")
        delivery = mock.Mock(message_id="<m@example.com>", provider="mock",
                             status="sent", is_success=True)
        engine.dispatch_outbound_message.return_value = (
            delivery, {"score": 95, "grade": "A"})
        with mock.patch.object(
                server_mod, "ConversationalEngine", return_value=engine):
            status, body = self.submit(
                "fresh@example.com", {"X-API-Key": self.api_key})
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)["success"])
        self.assertIsNotNone(
            self.repo.get_lead_by_email("ws_default_01", "fresh@example.com"))


if __name__ == "__main__":
    unittest.main()
