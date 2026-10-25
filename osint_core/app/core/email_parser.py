"""Email address decomposition.

Derives the username handle, plausible name tokens, and candidate handles that
Maigret-style enumeration should probe. Handles Gmail-style plus-addressing and
dot-insensitivity, and `first.last` corporate conventions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com",
    "hotmail.com", "live.com", "icloud.com", "me.com", "mac.com", "aol.com",
    "proton.me", "protonmail.com", "pm.me", "gmx.com", "gmx.net", "zoho.com",
    "yandex.com", "mail.com", "fastmail.com", "tutanota.com", "hey.com",
}

DOT_INSENSITIVE = {"gmail.com", "googlemail.com"}

_SEPARATORS = re.compile(r"[._\-]+")
_NON_HANDLE = re.compile(r"[^a-z0-9_]+")


@dataclass
class ParsedLead:
    email: str
    local: str
    domain: str
    is_free_provider: bool
    base_local: str              # local part minus plus-addressing, dots stripped where dot-insensitive
    name_tokens: list[str] = field(default_factory=list)
    username_candidates: list[str] = field(default_factory=list)
    plus_tag: str | None = None

    @property
    def primary_handle(self) -> str:
        return self.username_candidates[0] if self.username_candidates else self.base_local


def parse_email(email: str) -> ParsedLead:
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    domain = domain.encode("idna").decode("ascii") if domain else domain

    plus_tag = None
    base = local
    if "+" in local:
        base, _, plus_tag = local.partition("+")

    if domain in DOT_INSENSITIVE:
        base = base.replace(".", "")

    tokens = [t for t in _SEPARATORS.split(base) if len(t) >= 2 and t.isalpha()]

    candidates: list[str] = []
    seen: set[str] = set()

    def _push(handle: str) -> None:
        handle = _NON_HANDLE.sub("", handle.lower())[:30]
        if handle and handle not in seen:
            seen.add(handle)
            candidates.append(handle)

    _push(base)
    for t in tokens:
        _push(t)
    if len(tokens) >= 2:
        first, last = tokens[0], tokens[-1]
        _push(first + last)
        _push(first[0] + last)
        _push(first + last[0])
        _push(last + first)

    return ParsedLead(
        email=email,
        local=local,
        domain=domain,
        is_free_provider=domain in FREE_PROVIDERS,
        base_local=base,
        name_tokens=tokens,
        username_candidates=candidates,
        plus_tag=plus_tag,
    )
