"""Tests for the KumoMTA deliverability lab.

Pure-config tests run anywhere. Integration tests (marked `integration`) require
the lab running on 127.0.0.1 and are skipped otherwise.
"""
import os
import urllib.request
import smtplib
import pytest

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(LAB, "policy")
SCENARIOS_FILE = os.path.join(POLICY, "sink-scenarios.yaml")
SHAPING_FILE = os.path.join(POLICY, "provider-shaping.toml")

KUMO_HOST, KUMO_PORT = "127.0.0.1", 2587
USER, PASS, FROM = "lab", "lab-secret", "test@lab.internal"
SINK_METRICS = "http://127.0.0.1:8467/metrics"

EXPECTED_SCENARIOS = {
    "default", "gmail-throttle", "yahoo-tempfail", "microsoft-tarpit",
    "apple-quarantine", "proton-defer", "proofpoint-tempfail", "random-4xx",
    "permanent-reject", "slow-mx", "chaos-reset", "tls-refusal", "generic-accept",
}


def test_scenarios_yaml_parses_and_complete():
    import yaml
    with open(SCENARIOS_FILE) as f:
        doc = yaml.safe_load(f)
    names = {s["name"] for s in doc["scenarios"]}
    missing = EXPECTED_SCENARIOS - names
    assert not missing, f"missing scenarios: {missing}"
    # every scenario must have at least one step
    for s in doc["scenarios"]:
        assert s.get("steps"), f"{s['name']} has no steps"


def test_shaping_toml_parses_and_has_providers():
    try:
        import tomllib as t
    except ImportError:  # py<3.11
        import tomli as t  # type: ignore
    with open(SHAPING_FILE, "rb") as f:
        doc = t.load(f)
    for prov in ("gmail", "yahoo", "microsoft", "apple", "proton", "generic", "global_governor"):
        assert prov in doc, f"shaping missing provider {prov}"
    assert doc["global_governor"]["messages_per_minute"] > 0


def _lab_up():
    try:
        with urllib.request.urlopen(SINK_METRICS, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.mark.integration
def test_lab_submits_and_sink_records():
    if not _lab_up():
        pytest.skip("lab not running on 127.0.0.1")

    def parse(text):
        msgs, scen = {}, {}
        for line in text.splitlines():
            if line.startswith("sink_messages_total{"):
                res = line.split('result="')[1].split('"')[0]
                msgs[res] = msgs.get(res, 0) + int(line.rsplit(" ", 1)[1])
            elif line.startswith("sink_scenario_total{"):
                n = line.split('scenario="')[1].split('"')[0]
                scen[n] = scen.get(n, 0) + int(line.rsplit(" ", 1)[1])
        return msgs, scen

    to = "rcpt@yahoo.sink.lab.internal"
    body = (f"From: {FROM}\r\nTo: {to}\r\nSubject: t\r\n\r\nbody\r\n").encode()
    with smtplib.SMTP(KUMO_HOST, KUMO_PORT, timeout=30) as s:
        s.ehlo(); s.login(USER, PASS); s.sendmail(FROM, [to], body)

    with urllib.request.urlopen(SINK_METRICS, timeout=10) as r:
        msgs, scen = parse(r.read().decode())
    assert msgs.get("deferred", 0) >= 1, f"expected yahoo deferral, got {msgs}"
    assert scen.get("yahoo-tempfail", 0) >= 1
