"""Setup intake sources: one normaliser for every kind of client input.

A setup run accepts any combination of transcripts, notes, documents,
requirements, CRM exports, plain-language descriptions, and the company
website. The caller may start with one source or none: a source that
cannot be read is reported, never fatal, so setup always reaches the
questions that actually need a human.

Website reading reuses the research connector's fetcher and page parser
(`services.research`) — the same code that already proves what a page
actually says. Nothing here invents a fetcher.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from ..services.research import _PageParser, _fetch

#: Order matters: earlier types win when two sources state the same fact.
SOURCE_TYPES: tuple[str, ...] = (
    "notes",
    "description",
    "requirements",
    "transcript",
    "document",
    "campaign_examples",
    "crm_export",
    "website",
)

SOURCE_PRIORITY: dict[str, int] = {
    "notes": 0,
    "description": 1,
    "requirements": 2,
    "document": 3,
    "campaign_examples": 4,
    "transcript": 5,
    "crm_export": 6,
    "website": 7,
}

#: Binary formats we cannot read without a dependency we do not have.
UNSUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".png",
    ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".mp4", ".wav",
)

MAX_SOURCE_CHARS = 100_000
MAX_TOTAL_CHARS = 400_000


@dataclass
class Source:
    """One normalised input. `text` is what extraction reads."""

    id: str
    type: str
    label: str
    text: str = ""
    url: str = ""
    filename: str = ""
    status: str = "ready"  # ready | error | unsupported | truncated
    error: str = ""
    char_count: int = 0
    retrieved_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "text": self.text,
            "url": self.url,
            "filename": self.filename,
            "status": self.status,
            "error": self.error,
            "char_count": self.char_count,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Source":
        return cls(
            id=str(raw.get("id") or ""),
            type=str(raw.get("type") or "notes"),
            label=str(raw.get("label") or ""),
            text=str(raw.get("text") or ""),
            url=str(raw.get("url") or ""),
            filename=str(raw.get("filename") or ""),
            status=str(raw.get("status") or "ready"),
            error=str(raw.get("error") or ""),
            char_count=int(raw.get("char_count") or 0),
            retrieved_at=str(raw.get("retrieved_at") or ""),
        )


@dataclass
class NormalisedSources:
    sources: list[Source] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)

    @property
    def errors(self) -> list[dict[str, str]]:
        return [
            {"source": s.label or s.id or s.type, "type": s.type, "error": s.error}
            for s in self.sources
            if s.status in ("error", "unsupported")
        ]


def _slug(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return cleaned[:48] or fallback


def _safe_website_url(raw: str) -> str:
    """Normalise to an http(s) URL, refusing local/private targets.

    Setup input is operator-supplied, but a website fetch is still a server
    side request: refuse anything that is not a public web address.
    """
    value = (raw or "").strip()
    if not value:
        raise ValueError("website URL is empty")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("only http(s) website URLs are accepted")
    host = (parsed.hostname or "").strip().lower()
    if not host or host in ("localhost", "localhost.localdomain"):
        raise ValueError("local addresses are not accepted")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and (literal.is_private or literal.is_loopback
                                or literal.is_link_local or literal.is_reserved):
        raise ValueError("private or loopback addresses are not accepted")
    if literal is None:
        # Refuse names that resolve locally without touching the network.
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:  # unresolvable: reported, never fatal
            raise ValueError(f"could not resolve {host}: {exc}") from None
        for info in infos[:4]:
            try:
                addr = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError(f"{host} resolves to a private address")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def website_text(url: str) -> tuple[str, str]:
    """Read a public page into plain text. Returns (text, error)."""
    try:
        safe_url = _safe_website_url(url)
    except ValueError as exc:
        return "", str(exc)
    try:
        html, status = _fetch(safe_url)
    except Exception as exc:  # noqa: BLE001 — any transport failure is a source error
        return "", f"could not read {safe_url}: {exc}"
    if status >= 400:
        return "", f"{safe_url} returned HTTP {status}"
    parser = _PageParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — malformed HTML still yields partial text
        pass

    parts: list[str] = []
    if parser.title_parts and parser.title_parts[0]:
        parts.append(f"Site title: {parser.title_parts[0].strip()}")
    if parser.meta_description:
        parts.append(f"Site description: {parser.meta_description}")
    for heading in parser.headings[:12]:
        parts.append(f"Heading: {heading}")
    for paragraph in parser.paragraphs[:60]:
        parts.append(paragraph)
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        return "", f"{safe_url} contained no readable text"
    return text[:MAX_SOURCE_CHARS], ""


def normalise_sources(raw: Any) -> NormalisedSources:
    """Validate and fetch everything the caller supplied.

    Never raises for a bad individual source: it is recorded with a status
    so the setup screen can show what was and was not read.
    """
    out = NormalisedSources()
    if raw is None:
        return out
    if not isinstance(raw, list):
        out.rejected.append({"source": "sources", "error": "sources must be a list"})
        return out

    total = 0
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            out.rejected.append(
                {"source": f"item {index}", "error": "each source must be an object"}
            )
            continue
        source_type = str(item.get("type") or "").strip().lower()
        if source_type not in SOURCE_TYPES:
            out.rejected.append({
                "source": str(item.get("label") or item.get("filename") or f"item {index}"),
                "error": f"unsupported source type {source_type!r}",
            })
            continue

        text = str(item.get("text") or "")
        url = str(item.get("url") or "").strip()
        filename = str(item.get("filename") or "").strip()
        label = str(item.get("label") or "").strip()

        if filename:
            lowered = filename.lower()
            if any(lowered.endswith(ext) for ext in UNSUPPORTED_EXTENSIONS):
                out.sources.append(Source(
                    id=f"src_{index}", type=source_type, label=label or filename,
                    filename=filename, status="unsupported",
                    error=(
                        f"{filename} is a binary format this build cannot parse; "
                        "paste its text into a notes source instead"
                    ),
                ))
                continue

        status = "ready"
        error = ""
        if source_type == "website":
            if not url:
                out.sources.append(Source(
                    id=f"src_{index}", type=source_type,
                    label=label or url or "website", status="error",
                    error="a website source needs a url",
                ))
                continue
            text, error = website_text(url)
            status = "ready" if not error else "error"
            label = label or url

        if total + len(text) > MAX_TOTAL_CHARS:
            status = "truncated"
            error = "total intake size limit reached; this source was truncated"
            text = text[: max(0, MAX_TOTAL_CHARS - total)]

        if len(text) > MAX_SOURCE_CHARS:
            text = text[:MAX_SOURCE_CHARS]
            status = "truncated"
            error = error or "source exceeds the per-source size limit; truncated"

        source = Source(
            id=f"src_{index}",
            type=source_type,
            label=label or filename or url or source_type.title(),
            text=text,
            url=url,
            filename=filename,
            status=status,
            error=error,
            char_count=len(text),
        )
        total += len(text)
        out.sources.append(source)

    out.sources.sort(key=lambda s: (SOURCE_PRIORITY.get(s.type, 99), s.id))
    return out


def sources_payload(raw: Any) -> tuple[list[dict], list[dict]]:
    """Convenience for routes: (serialisable sources, rejected items)."""
    normalised = normalise_sources(raw)
    return [s.to_dict() for s in normalised.sources], normalised.rejected
