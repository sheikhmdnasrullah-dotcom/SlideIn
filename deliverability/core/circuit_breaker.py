"""Deliverability CIRCUIT BREAKER.

Continuously protects the campaign: the moment placement or reputation degrades,
it trips OPEN and pauses all outbound email. It stays open until a fresh full
validation passes (never auto-resumes blindly). After a trip it enters HALF-OPEN
state to allow a small probe batch before fully closing.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass
class BreakerConfig:
    min_seed_inbox_pct: float = 100.0     # require all seeds in inbox
    max_bounce_rate: float = 2.0          # percent
    max_complaint_rate: float = 0.1       # percent
    min_analyzer_grade: str = "B"
    blacklist_is_fatal: bool = True
    half_open_probe_count: int = 5        # max sends allowed in half-open
    half_open_cooldown_seconds: float = 300.0  # 5 min cooldown before half-open


_GRADE_RANK = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}


class CircuitBreaker:
    def __init__(self, store, cfg: BreakerConfig):
        self.store = store
        self.cfg = cfg

    def is_open(self) -> bool:
        return self.store.get_circuit()["status"] == "open"

    def is_half_open(self) -> bool:
        return self.store.get_circuit()["status"] == "half-open"

    def _trip(self, reason: str, metrics: dict) -> None:
        self.store.set_circuit("open", reason, metrics)
        self.store.set_campaign("cold-outreach", "PAUSED", paused_reason=reason)

    def _half_open(self, reason: str, metrics: dict) -> None:
        self.store.set_circuit("half-open", reason, metrics)

    def _close(self, reason: str, metrics: dict) -> None:
        self.store.set_circuit("closed", reason, metrics)
        # A closed circuit means sending is allowed again; the campaign was
        # PAUSED when the breaker tripped, so resume it here. Callers that
        # need extra ceremony use resume_after_validation() instead.
        self.store.set_campaign("cold-outreach", "ACTIVE")

    def evaluate(self, metrics: dict) -> tuple[bool, str]:
        """Return (tripped, reason). Trips if any threshold breached.

        Healthy metrics NEVER auto-close an open (or half-open) circuit:
        recovery requires resume_after_validation() or a completed probe
        batch (module docstring: "never auto-resumes blindly"). Without this
        guard a single healthy monitor tick would silently undo a trip.
        """
        reasons = []
        if metrics.get("seed_inbox_pct", 100.0) < self.cfg.min_seed_inbox_pct:
            reasons.append(f"seed inbox {metrics['seed_inbox_pct']}% < {self.cfg.min_seed_inbox_pct}%")
        if metrics.get("bounce_rate", 0.0) > self.cfg.max_bounce_rate:
            reasons.append(f"bounce {metrics['bounce_rate']}% > {self.cfg.max_bounce_rate}%")
        if metrics.get("complaint_rate", 0.0) > self.cfg.max_complaint_rate:
            reasons.append(f"complaint {metrics['complaint_rate']}% > {self.cfg.max_complaint_rate}%")
        g = metrics.get("analyzer_grade", "A")
        if _GRADE_RANK.get(g, 4) < _GRADE_RANK.get(self.cfg.min_analyzer_grade, 3):
            reasons.append(f"analyzer grade {g} < {self.cfg.min_analyzer_grade}")
        if self.cfg.blacklist_is_fatal and metrics.get("blacklisted"):
            reasons.append("sending IP/domain on DNSBL")

        if reasons:
            reason = "; ".join(reasons)
            self._trip(reason, metrics)
            return True, reason
        # No breach this tick. Keep whatever state we are in; only a fresh
        # circuit stays closed. (Previously this called _close() and would
        # auto-resume an open circuit from one healthy evaluation.)
        return False, ""

    def maybe_half_open(self) -> bool:
        """Transition from open -> half-open after cooldown if probes haven't started."""
        if not self.is_open():
            return False
        circuit = self.store.get_circuit()
        trip_ts = circuit.get("ts", 0)
        if (time.time() - trip_ts) >= self.cfg.half_open_cooldown_seconds:
            self._half_open("cooldown elapsed", {})
            return True
        return False

    def probe_send_allowed(self) -> bool:
        """True when a probe send is permitted in half-open state."""
        if not self.is_half_open():
            return False
        circuit = self.store.get_circuit()
        metrics = json.loads(circuit.get("metrics_json") or "{}")
        probes = int(metrics.get("half_open_probes", 0))
        return probes < self.cfg.half_open_probe_count

    def record_probe(self, success: bool, metrics: dict) -> None:
        """Record a probe send result.

        A failed probe re-trips immediately. The circuit only closes after
        ``half_open_probe_count`` successful probes — a single lucky delivery
        is not evidence that placement/reputation recovered.
        """
        circuit = self.store.get_circuit()
        current = json.loads(circuit.get("metrics_json") or "{}")
        current["half_open_probes"] = int(current.get("half_open_probes", 0)) + 1
        if not success:
            self._trip("probe failed", current)
            return
        current["half_open_successes"] = int(current.get("half_open_successes", 0)) + 1
        if current["half_open_successes"] >= self.cfg.half_open_probe_count:
            self._close("probe validation passed", current)
        else:
            # Persist the running counts while staying half-open.
            self.store.set_circuit(
                "half-open",
                f"probe validation in progress "
                f"({current['half_open_successes']}/{self.cfg.half_open_probe_count})",
                current,
            )

    def resume_after_validation(self, validation_passed: bool, metrics: dict) -> bool:
        """Only allow resume if a fresh full validation passed."""
        if not validation_passed:
            return False
        self._close("resumed after validation", metrics)
        self.store.set_campaign("cold-outreach", "ACTIVE")
        return True
