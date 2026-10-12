"""THE ONE APPROVED OUTBOUND PATH.

Every production email MUST go through send_via_pipeline(). It enforces:
   1) circuit breaker not open
   2) pre-send gate passed (analyzer + seed placement)
   3) send via the configured transport (SMTP relay, KumoMTA submission, or
      Gophish REST — selected by config["transport"])
   4) record a send_event for monitoring

There is intentionally no other public send function. Future agents must call this.
"""
from __future__ import annotations

import json
import re
import smtplib
import ssl
import time
from typing import Callable, Optional

from .gate import Blocked
from . import profiles as profile_mod


class BlockedSend(Exception):
    pass


def _log_send_event(store, recipient: str, stage: str, result: str, detail: str = "", **extra) -> None:
    """Record a structured send event for observability."""
    event = {
        "ts": time.time(),
        "recipient": recipient,
        "stage": stage,
        "result": result,
        "detail": detail,
        **extra,
    }
    try:
        store.record_send_event(
            recipient,
            stage,
            result,
            detail,
            bounce_type=extra.get("bounce_type", ""),
            dsn_status=extra.get("dsn_status", ""),
        )
    except Exception:
        pass


def _send_smtp(smtp_cfg: dict, eml_bytes: bytes, recipient: str,
               sender: Optional[str] = None) -> None:
    ctx = ssl.create_default_context()
    host = smtp_cfg["host"]
    port = int(smtp_cfg.get("port", 465))
    timeout = smtp_cfg.get("timeout", 30)
    mail_from = sender or smtp_cfg.get("from_addr", "") or ""
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout) as s:
            if smtp_cfg.get("user"):
                s.login(smtp_cfg["user"], smtp_cfg.get("password", ""))
            s.sendmail(mail_from, [recipient], eml_bytes)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            s.ehlo()
            if smtp_cfg.get("use_tls", True):
                s.starttls(context=ctx)
                s.ehlo()
            if smtp_cfg.get("user"):
                s.login(smtp_cfg["user"], smtp_cfg.get("password", ""))
            s.sendmail(mail_from, [recipient], eml_bytes)


def _send_gophish(api_cfg: dict, eml_bytes: bytes, recipient: str,
                  sender: Optional[str] = None) -> None:
    """Optional: send through Gophish REST (campaign send). Stub; extend as needed."""
    raise NotImplementedError("Gophish transport must be wired to the REST API explicitly.")


def _resolve_sender(eml_bytes: bytes, config: dict,
                    sender: Optional[str]) -> str:
    """Envelope MAIL FROM for this send.

    Precedence: explicit ``sender`` arg -> ``From`` header of the .eml. The
    result MUST be in the configured profile/domain allowlist and MUST equal
    the message's From address (DMARC/SPF alignment), so a profile cannot be
    smuggled under an approved .eml that was gated with a different identity.
    """
    resolved = profile_mod.envelope_sender(eml_bytes, sender)
    if not resolved:
        raise BlockedSend("could not resolve envelope sender (From header missing?)")
    if not profile_mod.is_approved_sender(config, resolved):
        raise BlockedSend(f"SENDER NOT APPROVED: {resolved}")

    # Identity alignment: envelope sender must match the .eml From header exactly.
    header_sender = profile_mod.envelope_sender(eml_bytes, None)
    if header_sender and header_sender.lower() != resolved.lower():
        raise BlockedSend(
            f"sender={resolved} does not match .eml From={header_sender}; "
            "re-render the .eml with the correct From and re-run gate-check."
        )
    return resolved


def _check_auth_alignment(eml_bytes: bytes, approved_domains: list) -> None:
    """Fail closed when Authentication-Results show SPF/DKIM/DMARC failures."""
    msg = eml_bytes if isinstance(eml_bytes, bytes) else eml_bytes.encode()
    text = msg.decode(errors="ignore").lower()
    ar = None
    for line in text.splitlines():
        if line.lower().startswith("authentication-results:"):
            ar = line
            break
    if not ar:
        return
    for mech in ("spf", "dkim", "dmarc"):
        if f"{mech}=fail" in ar:
            raise BlockedSend(
                f"{mech.upper()} failed per Authentication-Results; fix DNS/auth before sending."
            )
        if f"{mech}=softfail" in ar and mech == "spf":
            raise BlockedSend(
                "SPF softfail (~all) is not acceptable for production sending; use -all or proper alignment."
            )
    for domain in approved_domains:
        if f"header.from={domain}" in ar:
            return


def _check_lab_allowlist(recipient: str, config: dict) -> None:
    """Hard containment gate for experimental/lab mode.

    When ``config["lab"]["enabled"]`` is True, the pipeline will ONLY deliver to
    recipients present in ``config["lab"]["allowed_recipients"]``. An empty
    allowlist blocks every send (fail-closed). This keeps lab experiments from
    ever reaching a real third party. When lab mode is disabled this is a no-op,
    so production behavior is unchanged.
    """
    lab = config.get("lab") or {}
    if not lab.get("enabled"):
        return
    allowed = [a.strip().lower() for a in (lab.get("allowed_recipients") or [])]
    if not allowed:
        raise BlockedSend(
            "LAB MODE: allowed_recipients is empty. Define lab.allowed_recipients "
            "in config.json before enabling any send (fail-closed)."
        )
    if not recipient or recipient.strip().lower() not in allowed:
        raise BlockedSend(f"LAB MODE: recipient {recipient!r} is not in the allowlist.")


def _check_suppression(recipient: str, store) -> None:
    """Block send to suppressed addresses (bounces, complaints, dead)."""
    if store.is_suppressed(recipient):
        raise BlockedSend(f"RECIPIENT SUPPRESSED: {recipient}")


def _enforce_pacing(store, min_delay: float = 60.0) -> None:
    """Enforce minimum delay between sends to prevent burst sending."""
    events = store.recent_send_events(limit=20)
    sent_events = [e for e in events if e.get("result") == "sent"]
    if sent_events:
        last_ts = sent_events[0]["ts"]
        elapsed = time.time() - last_ts
        if elapsed < min_delay:
            wait = min_delay - elapsed
            raise BlockedSend(
                f"PACING: wait {wait:.1f}s before next send (min {min_delay}s between sends)."
            )


def _check_blacklist(ip: str, domain: str, store, fail_closed: bool = True) -> None:
    """Check if sending IP/domain is on a blacklist.

    Fail-closed: a listed IP blocks the send, and an *inconclusive* check
    (DNS unavailable) blocks too unless the caller passes
    ``fail_closed=False`` (config ``blacklist.fail_open_on_error = true``).

    The previous implementation wrapped everything — including its own
    ``raise BlockedSend`` — in ``except Exception: pass``, so a listed IP
    never blocked anything (silent fail-open).
    """
    try:
        try:
            from . import dns_checks
        except ImportError:
            import dns_checks  # type: ignore
        checks = dns_checks.audit_blacklists(ip)
    except Exception as exc:
        msg = f"blacklist check failed ({exc})"
        if fail_closed:
            store.record_send_event("", "precheck", "blocked", msg)
            raise BlockedSend(
                f"PRECHECK BLOCKED: {msg}. Fix DNS or set "
                "blacklist.fail_open_on_error=true to send anyway."
            )
        return

    failed = [c for c in checks if c.status == "FAIL"]
    if failed:
        names = ", ".join(c.name for c in failed)
        store.record_send_event("", "precheck", "blocked", f"blacklisted: {names}")
        raise BlockedSend(f"PRECHECK BLOCKED: sending IP {ip} is listed on: {names}")

    inconclusive = [c for c in checks if c.status == "WARN"]
    if inconclusive:
        names = ", ".join(c.name for c in inconclusive)
        msg = f"blacklist lookup inconclusive: {names}"
        if fail_closed:
            store.record_send_event("", "precheck", "blocked", msg)
            raise BlockedSend(
                f"PRECHECK BLOCKED: {msg} (fail-closed; set "
                "blacklist.fail_open_on_error=true to override)"
            )


def _check_placement_risk(eml_bytes: bytes, config: dict) -> None:
    """Fail closed when promotions/spam risk exceeds threshold."""
    from .placement_risk import classify_placement_risk
    risk = classify_placement_risk(eml_bytes)
    threshold = config.get("placement", {}).get("max_promotions_risk", 30)
    if risk.promotions_risk > threshold:
        raise BlockedSend(
            f"PROMOTIONS RISK: {risk.promotions_risk:.1f}% > {threshold}% — "
            f"signals: {', '.join(risk.promotions_signals[:5])}. Fix content/headers."
        )
    threshold_spam = config.get("placement", {}).get("max_spam_risk", 30)
    if risk.spam_risk > threshold_spam:
        raise BlockedSend(
            f"SPAM RISK: {risk.spam_risk:.1f}% > {threshold_spam}% — "
            f"signals: {', '.join(risk.spam_signals[:5])}. Fix content/headers."
        )


def send_via_pipeline(
    recipient: str,
    eml_bytes: bytes,
    *,
    config: dict,
    store,
    gate,
    breaker,
    transport: Optional[Callable] = None,
    sender: Optional[str] = None,
) -> dict:
    send_start = time.time()
    _log_send_event(store, recipient, "pipeline", "started", "")

    # 0) Lab containment (hard allowlist gate). Runs before everything else so a
    # lab experiment can never reach a recipient outside the explicit allowlist.
    try:
        _check_lab_allowlist(recipient, config)
    except BlockedSend as e:
        _log_send_event(store, recipient, "lab", "blocked", str(e))
        raise

    # 0) Suppression list
    try:
        _check_suppression(recipient, store)
    except BlockedSend as e:
        _log_send_event(store, recipient, "suppression", "blocked", str(e))
        raise

    # 0.5) Pacing (anti-burst)
    try:
        _enforce_pacing(store, config.get("pacing", {}).get("min_delay_seconds", 60))
    except BlockedSend as e:
        _log_send_event(store, recipient, "pacing", "blocked", str(e))
        raise

    # 0.6) Pre-send blacklist check (fail-closed by default)
    sending_ip = config.get("sending_ip")
    sending_domain = config.get("sending_domain") or (sender.split("@")[1] if sender and "@" in sender else "")
    if sending_ip:
        fail_open = bool(config.get("blacklist", {}).get("fail_open_on_error", False))
        try:
            _check_blacklist(sending_ip, sending_domain, store, fail_closed=not fail_open)
        except BlockedSend as e:
            _log_send_event(store, recipient, "blacklist", "blocked", str(e))
            raise

    # 1) Circuit breaker
    if breaker.is_open():
        c = store.get_circuit()
        _log_send_event(store, recipient, "circuit", "blocked", c["reason"])
        raise BlockedSend(f"CIRCUIT OPEN: {c['reason']} — sending paused.")
    # While half-open only the probe batch may flow; once the budget is
    # spent the circuit waits for validation (re-trip or close).
    half_open = breaker.is_half_open()
    if half_open and not breaker.probe_send_allowed():
        c = store.get_circuit()
        _log_send_event(store, recipient, "circuit", "blocked", "half-open probe budget exhausted")
        raise BlockedSend(
            "CIRCUIT HALF-OPEN: probe budget exhausted — sending paused "
            f"until validation completes ({c['reason']})."
        )

    # 2) Gate
    try:
        gate.require_approval(eml_bytes)
    except Blocked as e:
        _log_send_event(store, recipient, "gate", "blocked", str(e))
        raise BlockedSend(str(e))

    # 2b) Sender identity (approved profile + aligned with From)
    try:
        resolved = _resolve_sender(eml_bytes, config, sender)
    except BlockedSend as e:
        _log_send_event(store, recipient, "sender", "blocked", str(e))
        raise

    # 2c) Auth alignment on the .eml itself
    approved_domains = profile_mod.approved_domains(config)
    try:
        _check_auth_alignment(eml_bytes, approved_domains)
    except BlockedSend as e:
        _log_send_event(store, recipient, "auth", "blocked", str(e))
        raise

    # 2e) Placement risk classifier (promotions/spam)
    try:
        _check_placement_risk(eml_bytes, config)
    except BlockedSend as e:
        _log_send_event(store, recipient, "placement", "blocked", str(e))
        raise

    # 2d) Warmup + per-profile volume enforcement
    from .warmup import WarmupTracker
    wtracker = WarmupTracker(store.conn)
    for d in approved_domains:
        wtracker.initialize_domain(d)
        ok, reason = wtracker.can_send(d, store)
        if not ok:
            _log_send_event(store, recipient, "warmup", "blocked", reason)
            raise BlockedSend(f"WARMUP: {reason}")
        wtracker.record_send(d, resolved, recipient)

    # 3) Send
    t = config.get("transport", "smtp")
    try:
        if transport is not None:
            transport(config.get(t, {}), eml_bytes, recipient)
        elif t == "kumo":
            from .kumo_transport import send_via_kumo
            send_via_kumo(eml_bytes, recipient, config["kumo"], sender=resolved)
        elif t in ("mailpit", "dev-sink"):
            from .provider import DevSinkProvider
            mp_cfg = config.get("mailpit", {})
            sink = DevSinkProvider(
                host=mp_cfg.get("host", "127.0.0.1"),
                port=int(mp_cfg.get("port", 1025))
            )
            res = sink.send(eml_bytes, recipient, resolved)
            if not res.is_success:
                raise BlockedSend(f"DevSink delivery error: {res.error}")
        elif t == "gophish":
            _send_gophish(config["gophish"], eml_bytes, recipient, sender=resolved)
        else:
            _send_smtp(config["smtp"], eml_bytes, recipient, sender=resolved)
    except BlockedSend:
        if half_open:
            breaker.record_probe(False, {"recipient": recipient, "error": "transport refused"})
        raise
    except Exception as e:
        _log_send_event(store, recipient, t, "error", str(e), bounce_type="error", dsn_status="")
        if half_open:
            # A failed probe re-trips the circuit (fail-closed recovery).
            breaker.record_probe(False, {"recipient": recipient, "error": str(e)})
        raise BlockedSend(f"SEND ERROR: {e}")

    elapsed = time.time() - send_start
    _log_send_event(store, recipient, t, "sent", "", sender=resolved, latency_seconds=round(elapsed, 3))
    if half_open:
        breaker.record_probe(True, {"recipient": recipient})
    return {"status": "sent", "recipient": recipient, "sender": resolved, "latency_seconds": round(elapsed, 3)}

