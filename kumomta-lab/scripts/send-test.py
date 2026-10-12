#!/usr/bin/env python3
"""Lab end-to-end harness: submit one message per sink scenario via KumoMTA,
then read the sink MX metrics and report dispositions.

Requires the lab running (scripts/deploy.sh). Talks ONLY to 127.0.0.1.
"""
import smtplib
import sys
import urllib.request

KUMO_HOST = "127.0.0.1"
KUMO_PORT = 2587
USER = "lab"
PASS = "lab-secret"
FROM = "test@lab.internal"
SINK_METRICS = "http://127.0.0.1:8467/metrics"

# scenario name -> recipient domain (must match sink-scenarios.yaml domain_match)
SCENARIOS = {
    "default": "sink.lab.internal",
    "gmail-throttle": "gmail.sink.lab.internal",
    "yahoo-tempfail": "yahoo.sink.lab.internal",
    "microsoft-tarpit": "outlook.sink.lab.internal",
    "apple-quarantine": "icloud.sink.lab.internal",
    "proton-defer": "proton.sink.lab.internal",
    "proofpoint-tempfail": "proofpoint.sink.lab.internal",
    "random-4xx": "flaky.sink.lab.internal",
    "permanent-reject": "reject.sink.lab.internal",
    "slow-mx": "slow.sink.lab.internal",
    "chaos-reset": "chaos.sink.lab.internal",
    "tls-refusal": "tlsfail.sink.lab.internal",
    "generic-accept": "generic.sink.lab.internal",
}


def send_one(recipient: str) -> None:
    body = (
        f"From: {FROM}\r\n"
        f"To: {recipient}\r\n"
        f"Subject: lab test {recipient}\r\n"
        f"Date: now\r\nMessage-ID: <{recipient}@lab.internal>\r\n\r\n"
        f"body for {recipient}\r\n"
    ).encode()
    with smtplib.SMTP(KUMO_HOST, KUMO_PORT, timeout=30) as s:
        s.ehlo()
        s.login(USER, PASS)
        s.sendmail(FROM, [recipient], body)


def parse_metrics(text: str):
    msgs = {}
    scen = {}
    for line in text.splitlines():
        if line.startswith("sink_messages_total{"):
            # sink_messages_total{result="accepted"} 12
            result = line.split('result="')[1].split('"')[0]
            val = int(line.rsplit(" ", 1)[1])
            msgs[result] = msgs.get(result, 0) + val
        elif line.startswith("sink_scenario_total{"):
            name = line.split('scenario="')[1].split('"')[0]
            val = int(line.rsplit(" ", 1)[1])
            scen[name] = scen.get(name, 0) + val
    return msgs, scen


def main() -> int:
    only = sys.argv[1:] or list(SCENARIOS)
    print(f"Submitting {len(only)} scenario message(s) via KumoMTA {KUMO_HOST}:{KUMO_PORT} ...")
    for name in only:
        if name not in SCENARIOS:
            print(f"  unknown scenario: {name} (known: {', '.join(SCENARIOS)})")
            continue
        rcpt = f"rcpt@{SCENARIOS[name]}"
        try:
            send_one(rcpt)
            print(f"  submitted -> {name} ({rcpt})")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR sending to {name}: {e}")

    print("Reading sink metrics...")
    try:
        with urllib.request.urlopen(SINK_METRICS, timeout=10) as r:
            msgs, scen = parse_metrics(r.read().decode())
    except Exception as e:  # noqa: BLE001
        print(f"  could not read sink metrics: {e}")
        return 1

    print("\nDispositions (sink):")
    for k in ("accepted", "deferred", "rejected"):
        print(f"  {k:10s}: {msgs.get(k, 0)}")
    print("\nBy scenario:")
    for k, v in sorted(scen.items()):
        print(f"  {k:22s}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
