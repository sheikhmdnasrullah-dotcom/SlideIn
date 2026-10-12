"""Pre-send placement GATE.

No production email leaves without a fresh, passing decision here.

Decision: approved iff
  analyzer_grade >= MIN_GRADE
  AND seed placement == 100% INBOX (no Spam/Junk/Promotions)
  AND decision_age <= VALIDITY_WINDOW_HOURS
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


class Blocked(Exception):
    pass


@dataclass
class GateConfig:
    min_grade: str = "B"          # minimum analyzer grade A-F
    validity_window_hours: float = 24.0
    require_seed: bool = True

_GRADE_RANK = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def _hash(eml_bytes: bytes) -> str:
    return hashlib.sha256(eml_bytes).hexdigest()[:16]


class Gate:
    def __init__(self, store, cfg: GateConfig):
        self.store = store
        self.cfg = cfg

    def evaluate(self, eml_bytes: bytes, analyzer, seed_runner) -> dict:
        """Run analyzer + seed test, store decision, return it."""
        eml_hash = _hash(eml_bytes)
        analysis = analyzer(eml_bytes)
        grade_rank = _GRADE_RANK.get(analysis.grade, 0)
        grade_ok = grade_rank >= _GRADE_RANK.get(self.cfg.min_grade, 3)

        seed_results = []
        seed_pass = True
        if self.cfg.require_seed:
            seed_results = seed_runner(eml_bytes)
            # Fail closed: with no seed results we cannot PROVE 100% INBOX, so the
            # gate must not approve. (Previously an empty list vacuously passed.)
            seed_pass = bool(seed_results) and all(r.passed for r in seed_results)

        approved = grade_ok and seed_pass
        decision = {
            "email_hash": eml_hash,
            "analyzer_grade": analysis.grade,
            "analyzer_score": analysis.score,
            "seed_pass": seed_pass,
            "seed_detail": [r.to_dict() for r in seed_results],
            "approved": approved,
            "reason": "" if approved else self._reason(grade_ok, seed_pass, seed_results, analysis),
        }
        self.store.record_gate_decision(decision)
        return decision

    def _reason(self, grade_ok, seed_pass, seed_results, analysis) -> str:
        reasons = []
        if not grade_ok:
            reasons.append(f"analyzer grade {analysis.grade} < {self.cfg.min_grade}")
        if not seed_pass:
            bad = [f"{r.provider}:{r.folder}" for r in seed_results if not r.passed]
            reasons.append("seed placement failed: " + ", ".join(bad))
        return "; ".join(reasons)

    def is_fresh_approved(self, eml_bytes: bytes) -> bool:
        latest = self.store.latest_gate_decision()
        if not latest:
            return False
        if not latest["approved"]:
            return False
        if latest["email_hash"] != _hash(eml_bytes):
            return False
        age_h = (time.time() - latest["ts"]) / 3600.0
        return age_h <= self.cfg.validity_window_hours

    def require_approval(self, eml_bytes: bytes) -> None:
        if not self.is_fresh_approved(eml_bytes):
            raise Blocked(
                "GATE NOT PASSED: run `cli.py gate-check` / `seed-test` first. "
                "Production send blocked."
            )
