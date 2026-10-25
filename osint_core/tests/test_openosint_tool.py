"""Unit tests for the OpenOSINT CLI bridge (app/modules/openosint_tool.py).

A fake `openosint` executable stands in for the real binary: same argv
contract (``openosint --json [ --allow-active ] <tool> <target>``), same
JSON envelopes, including the exposure report-object exception. No network
and no real CLI required.

Run from ``saas/osint_core``::

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import stat
import tempfile
import unittest

from app.modules.openosint_tool import (
    DEFAULT_LOOKUPS,
    exposure_lines,
    run_openosint,
    targets_for,
)

FAKE_CLI = r"""#!/usr/bin/env python3
import json, sys

pos = [a for a in sys.argv[1:] if not a.startswith("--")]
tool, target = pos[0], pos[1]

if tool == "dns":
    print(json.dumps({
        "tool": "dns", "target": target, "error": None,
        "results": [
            "[DNS] A: 93.184.216.34",
            "\x1b[32m[DNS] SPF: v=spf1 -all\x1b[0m",
            "[DNS] DKIM not checked: selector probing is enumeration (needs --allow-active).",
        ],
    }))
elif tool == "exposure":
    print(json.dumps({
        "domain": target, "grade": "B", "score": 88,
        "score_is_partial": False,
        "checks": {"tls": {"status": "ok", "reason": None},
                   "email": {"status": "warn", "reason": "no DMARC"}},
        "findings": [{"severity": "low", "title": "Old TLS cipher"}],
    }))
elif tool in ("email", "username"):
    if "--allow-active" not in sys.argv:
        print(json.dumps({"tool": tool, "target": target, "results": [],
                          "error": "active tool ran without --allow-active"}))
        sys.exit(3)
    print(json.dumps({"tool": tool, "target": target, "error": None,
                      "results": ["[+] site.example"]}))
else:
    print(json.dumps({"tool": tool, "target": target, "results": [],
                      "error": "unknown tool"}))
"""


class FakeCliTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "openosint")
        with open(path, "w") as fh:
            fh.write(FAKE_CLI)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP)
        self.cli = path

    async def test_dns_ok_and_ansi_stripped(self) -> None:
        out = await run_openosint(domain="example.com",
                                  lookups=["dns"], cli=self.cli)
        self.assertTrue(out["available"])
        self.assertEqual(out["source"], "openosint-cli")
        row = out["lookups"][0]
        self.assertEqual((row["lookup"], row["target"], row["ok"]),
                         ("dns", "example.com", True))
        self.assertIn("[DNS] SPF: v=spf1 -all", row["lines"])
        self.assertFalse(any("\x1b" in line for line in row["lines"]))

    async def test_exposure_report_object_flattened(self) -> None:
        out = await run_openosint(domain="example.com",
                                  lookups=["exposure"], cli=self.cli)
        row = out["lookups"][0]
        self.assertTrue(row["ok"], row["error"])
        self.assertEqual(row["lines"][0], "[exposure] example.com grade B score 88")
        self.assertIn("[exposure] check tls: ok", row["lines"])
        self.assertIn("[exposure] low: Old TLS cipher", row["lines"])

    async def test_active_lookup_gated_without_allow_active(self) -> None:
        out = await run_openosint(email="a@b.example",
                                  lookups=["email"], allow_active=False,
                                  cli=self.cli)
        row = out["lookups"][0]
        self.assertFalse(row["ok"])
        self.assertIn("active/noisy", row["error"])

    async def test_active_lookup_runs_with_allow_active(self) -> None:
        out = await run_openosint(email="a@b.example",
                                  lookups=["email"], allow_active=True,
                                  cli=self.cli)
        row = out["lookups"][0]
        self.assertTrue(row["ok"], row["error"])
        self.assertEqual(row["lines"], ["[+] site.example"])

    async def test_missing_binary_degrades_without_raising(self) -> None:
        out = await run_openosint(domain="example.com", lookups=["dns"],
                                  cli="/nonexistent/bin/openosint")
        self.assertFalse(out["available"])
        row = out["lookups"][0]
        self.assertFalse(row["ok"])
        self.assertIn("not found", row["error"])

    async def test_unknown_lookup_ignored(self) -> None:
        out = await run_openosint(domain="example.com",
                                  lookups=["nope", "dns"], cli=self.cli)
        self.assertEqual([r["lookup"] for r in out["lookups"]], ["dns"])

    async def test_defaults_are_passive(self) -> None:
        self.assertEqual(DEFAULT_LOOKUPS, ("dns", "exposure", "github"))


class PureHelperTests(unittest.TestCase):
    def test_targets_for(self) -> None:
        self.assertEqual(
            targets_for(email="jane@acme.example", handle="jane",
                        domain="acme.example", local_part="jane"),
            {"dns": "acme.example", "exposure": "acme.example",
             "github": "jane", "email": "jane@acme.example",
             "username": "jane"},
        )

    def test_username_falls_back_to_email_local_part(self) -> None:
        targets = targets_for(email="jane@acme.example", handle="",
                              domain="", local_part="jane")
        self.assertEqual(targets["username"], "jane")

    def test_exposure_lines_handles_partial_and_missing_score(self) -> None:
        lines = exposure_lines({"domain": "x.example", "grade": "C",
                                "score_is_partial": True})
        self.assertEqual(lines, ["[exposure] x.example grade C (partial)"])

    def test_exposure_lines_caps_findings(self) -> None:
        findings = [{"severity": "low", "title": f"f{i}"} for i in range(50)]
        lines = exposure_lines({"domain": "x.example", "grade": "A",
                                "findings": findings})
        finding_lines = [l for l in lines if l.startswith("[exposure] low:")]
        self.assertEqual(len(finding_lines), 20)

    def test_settings_expose_openosint_knobs(self) -> None:
        from app.config import settings
        self.assertTrue(settings.openosint_bin)
        self.assertIsInstance(settings.openosint_allow_active, bool)


if __name__ == "__main__":
    unittest.main()
