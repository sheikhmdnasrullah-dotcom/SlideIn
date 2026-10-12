"""Async SMTP server with scenario-driven responses.

Each accepted connection:
  - reads EHLO/HELO, MAIL FROM, RCPT TO, DATA
  - records a structured event to a JSONL log
  - selects a scenario from the YAML file based on the recipient domain
  - replays the scenario's SMTP responses (250, 421, 450, 550, slow reads, etc.)
  - exposes Prometheus metrics on SINK_METRICS_ADDR
"""
import asyncio
import json
import logging
import os
import random
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml
from aiohttp import web

LOG = logging.getLogger("sink")
logging.basicConfig(level=os.environ.get("SINK_LOG_LEVEL", "INFO"))


@dataclass
class ScenarioStep:
    kind: str  # "reply" | "delay" | "tls" | "reset"
    code: int = 250
    enhanced: str = ""
    text: str = ""
    seconds: float = 0.0


@dataclass
class Scenario:
    name: str
    domain_match: list
    steps: list


def load_scenarios(path: str) -> Dict[str, Scenario]:
    raw = yaml.safe_load(Path(path).read_text())
    out: Dict[str, Scenario] = {}
    for s in raw.get("scenarios", []):
        steps = [ScenarioStep(**step) for step in s.get("steps", [])]
        out[s["name"]] = Scenario(
            name=s["name"],
            domain_match=s.get("domain_match", []),
            steps=steps,
        )
    return out


class Metrics:
    def __init__(self) -> None:
        self.connections: int = 0
        self.messages_accepted: int = 0
        self.messages_deferred: int = 0
        self.messages_rejected: int = 0
        self.tls_failures: int = 0
        self.by_scenario: Dict[str, int] = {}
        self.lock = asyncio.Lock()

    async def render(self) -> str:
        async with self.lock:
            lines = [
                "# HELP sink_connections_total Total SMTP connections received.",
                f"# TYPE sink_connections_total counter",
                f"sink_connections_total {self.connections}",
                "# HELP sink_messages_total Total messages handled by final disposition.",
                "# TYPE sink_messages_total counter",
                f'sink_messages_total{{result="accepted"}} {self.messages_accepted}',
                f'sink_messages_total{{result="deferred"}} {self.messages_deferred}',
                f'sink_messages_total{{result="rejected"}} {self.messages_rejected}',
                "# HELP sink_tls_failures_total TLS handshake failures.",
                "# TYPE sink_tls_failures_total counter",
                f"sink_tls_failures_total {self.tls_failures}",
                "# HELP sink_scenario_total Messages routed by scenario.",
                "# TYPE sink_scenario_total counter",
            ]
            for name, n in self.by_scenario.items():
                lines.append(f'sink_scenario_total{{scenario="{name}"}} {n}')
            return "\n".join(lines) + "\n"


METRICS = Metrics()
SCENARIOS: Dict[str, Scenario] = {}
LOG_PATH = os.environ.get("SINK_LOG_PATH", "/var/log/sink/events.jsonl")


def match_scenario(recipient_domain: str) -> Scenario:
    recipient_domain = recipient_domain.lower()
    for s in SCENARIOS.values():
        for d in s.domain_match:
            if d.startswith("*") and recipient_domain.endswith(d[1:]):
                return s
            if d.lower() == recipient_domain:
                return s
    if "default" in SCENARIOS:
        return SCENARIOS["default"]
    return Scenario(name="passthrough", domain_match=[], steps=[
        ScenarioStep(kind="reply", code=250, text="OK"),
    ])


async def write_event(event: dict) -> None:
    path = Path(LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, sort_keys=True)
    async with asyncio.Lock():
        with path.open("a") as f:
            f.write(line + "\n")


async def handle_scenario(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, scenario: Scenario) -> None:
    peer = writer.get_extra_info("peername")
    METRICS.connections += 1
    event = {
        "ts": time.time(),
        "peer": f"{peer[0]}:{peer[1]}" if peer else "?",
        "scenario": scenario.name,
        "trace": [],
    }

    async def send_line(line: str) -> None:
        writer.write((line + "\r\n").encode())
        await writer.drain()

    await send_line("220 sink.lab.internal ESMTP lab-sink")

    buf = b""
    in_data = False
    data_buf = bytearray()
    rcpt_to: Optional[str] = None
    mail_from: Optional[str] = None
    rejected = False
    deferred = False

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(reader.readline(), timeout=120)
            except asyncio.TimeoutError:
                await send_line("421 4.4.2 Connection timed out")
                rejected = True
                break
            if not chunk:
                break
            line = chunk.rstrip(b"\r\n").decode("utf-8", "replace")
            event["trace"].append({"dir": "recv", "line": line})

            if in_data:
                if line == ".":
                    in_data = False
                else:
                    data_buf.extend(line.encode() + b"\r\n")
                continue

            upper = line.upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                await send_line("250-sink.lab.internal")
                await send_line("250-PIPELINING")
                await send_line("250-8BITMIME")
                await send_line("250-STARTTLS")
                await send_line("250 SIZE 52428800")
            elif upper.startswith("STARTTLS"):
                # We do not provide TLS in lab mode — record as TLS failure only
                # if the scenario asked for it. By default: refuse politely.
                await send_line("454 4.7.0 TLS not available in lab")
                METRICS.tls_failures += 1
            elif upper.startswith("MAIL FROM"):
                mail_from = line
                await send_line("250 2.1.0 Sender OK")
            elif upper.startswith("RCPT TO"):
                rcpt_to = line
                # Decide which scenario applies to this recipient.
                domain = rcpt_to.split(":", 1)[1].split("@", 1)[-1].rstrip(">").strip()
                active = match_scenario(domain)
                # Replay configured steps as the RCPT response. If a step already
                # answered RCPT (4xx/5xx/250), do NOT also emit a trailing 250.
                rcpt_answered = False
                for step in active.steps:
                    if step.kind == "reply":
                        await send_line(f"{step.code} {step.enhanced} {step.text}".strip())
                        rcpt_answered = True
                        if 400 <= step.code < 500:
                            deferred = True
                            break
                        if 500 <= step.code < 600:
                            rejected = True
                            break
                    elif step.kind == "delay":
                        await asyncio.sleep(step.seconds)
                    elif step.kind == "reset":
                        writer.close()
                        return
                if not rcpt_answered:
                    await send_line("250 2.1.5 Recipient OK")
            elif upper == "DATA":
                if rcpt_to is None:
                    await send_line("503 5.5.1 MAIL/RCPT first")
                    continue
                await send_line("354 End data with <CR><LF>.<CR><LF>")
                in_data = True
            elif upper == "QUIT":
                await send_line("221 2.0.0 Bye")
                break
            elif upper == "RSET":
                await send_line("250 2.0.0 Reset")
            elif upper == "NOOP":
                await send_line("250 2.0.0 Noop")
            elif upper.startswith("VRFY"):
                await send_line("252 2.5.0 Cannot VRFY")
            else:
                await send_line("500 5.5.2 Unrecognized")
    finally:
        if not rejected and not deferred:
            METRICS.messages_accepted += 1
        elif deferred:
            METRICS.messages_deferred += 1
        elif rejected:
            METRICS.messages_rejected += 1
        async with METRICS.lock:
            METRICS.by_scenario[scenario.name] = METRICS.by_scenario.get(scenario.name, 0) + 1
        event["outcome"] = "rejected" if rejected else "deferred" if deferred else "accepted"
        event["mail_from"] = mail_from
        event["rcpt_to"] = rcpt_to
        event["data_bytes"] = len(data_buf)
        await write_event(event)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # Default scenario is selected later in the SMTP exchange.
    await handle_scenario(reader, writer, SCENARIOS.get("default") or Scenario("default", [], []))


async def metrics_handler(_request: web.Request) -> web.Response:
    return web.Response(text=await METRICS.render(), content_type="text/plain")


async def scenarios_handler(_request: web.Request) -> web.Response:
    payload = {n: {"steps": [{"kind": s.kind, "code": s.code, "text": s.text} for s in s.steps]} for n, s in SCENARIOS.items()}
    return web.json_response(payload)


async def main() -> None:
    global SCENARIOS
    SCENARIOS = load_scenarios(os.environ.get("SINK_SCENARIOS_FILE", "/etc/sink/scenarios.yaml"))

    listen = os.environ.get("SINK_LISTEN_ADDR", "0.0.0.0:25")
    if ":" in listen:
        smtp_host, _, smtp_port = listen.rpartition(":")
        smtp_port = int(smtp_port)
    else:
        smtp_host = listen
        smtp_port = int(os.environ.get("SINK_LISTEN_PORT", "25"))

    metrics_addr = os.environ.get("SINK_METRICS_ADDR", "0.0.0.0:8467")
    metrics_host, metrics_port = metrics_addr.split(":")

    loop = asyncio.get_event_loop()
    stop = loop.add_signal_handler if hasattr(loop, "add_signal_handler") else None

    smtp_server = await asyncio.start_server(client_connected, smtp_host, smtp_port)
    LOG.info("sink-mx listening on %s:%d", smtp_host, smtp_port)

    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/scenarios", scenarios_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, metrics_host, int(metrics_port))
    await site.start()
    LOG.info("sink-mx metrics on %s", metrics_addr)

    async with smtp_server:
        await smtp_server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())