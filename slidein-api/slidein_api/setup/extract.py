"""Business-profile extraction from setup sources.

Deterministic first: the same inputs always produce the same profile, and
every extracted value keeps its provenance (which source said it, whether
it was stated outright or inferred, and how confident the reading is).

Nothing is invented to make a profile look complete. A value with no
support stays `unknown`; a value read out of prose rather than a label is
`assumption`; two sources that disagree become an explicit `conflict`
instead of a silent overwrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from ..factory.compiler import _infer_industry_key
from .sources import Source

# --------------------------------------------------------------------------
# Field catalogue — the canonical business profile the mission asks for.
# --------------------------------------------------------------------------

FIELD_LABELS: dict[str, str] = {
    "legal_name": "Business name",
    "website_url": "Website URL",
    "industry": "Industry",
    "business_description": "Business description",
    "core_value_prop": "Core value proposition",
    "business_model": "Business model",
    "products_services": "Products and services",
    "differentiators": "Differentiators",
    "target_market": "Target market",
    "ideal_customer_profile": "Ideal customer profile",
    "qualification_rules": "Qualification rules",
    "exclusion_rules": "Exclusion rules",
    "geography": "Geographic constraints",
    "industries_served": "Industries served",
    "brand_voice": "Brand voice and communication preferences",
    "goals": "Business goals",
    "success_measures": "Success measures",
    "processes": "Existing processes",
    "team_responsibilities": "Team responsibilities",
    "integrations_required": "Required integrations",
    "data_available": "Available data",
    "operational_constraints": "Operational constraints",
    "approval_requirements": "Approval requirements",
    "service_scope": "Agreed service scope",
}

FIELD_ORDER: tuple[str, ...] = tuple(FIELD_LABELS)

#: Label aliases → field. Matched case-insensitively at the start of a line
#: or section heading.
ALIASES: dict[str, str] = {
    "business name": "legal_name",
    "company name": "legal_name",
    "company": "legal_name",
    "client": "legal_name",
    "name": "legal_name",
    "website": "website_url",
    "website url": "website_url",
    "web site": "website_url",
    "url": "website_url",
    "site": "website_url",
    "industry": "industry",
    "sector": "industry",
    "vertical": "industry",
    "business description": "business_description",
    "description": "business_description",
    "about": "business_description",
    "about us": "business_description",
    "core value proposition": "core_value_prop",
    "value prop": "core_value_prop",
    "our promise": "core_value_prop",
    "business model": "business_model",
    "model": "business_model",
    "products": "products_services",
    "product": "products_services",
    "services": "products_services",
    "service": "products_services",
    "offers": "products_services",
    "offer": "products_services",
    "what we sell": "products_services",
    "differentiators": "differentiators",
    "differentiator": "differentiators",
    "usp": "differentiators",
    "why us": "differentiators",
    "value proposition": "differentiators",
    "target market": "target_market",
    "market": "target_market",
    "market segment": "target_market",
    "icp": "ideal_customer_profile",
    "ideal customer": "ideal_customer_profile",
    "ideal customer profile": "ideal_customer_profile",
    "target customer": "ideal_customer_profile",
    "who we serve": "ideal_customer_profile",
    "qualification": "qualification_rules",
    "qualification rules": "qualification_rules",
    "qualify": "qualification_rules",
    "qualifying": "qualification_rules",
    "exclusions": "exclusion_rules",
    "exclusion": "exclusion_rules",
    "exclusion rules": "exclusion_rules",
    "disqualify": "exclusion_rules",
    "never contact": "exclusion_rules",
    "do not contact": "exclusion_rules",
    "geography": "geography",
    "geographic": "geography",
    "locations": "geography",
    "regions": "geography",
    "industries": "industries_served",
    "verticals": "industries_served",
    "brand voice": "brand_voice",
    "voice": "brand_voice",
    "tone": "brand_voice",
    "tone of voice": "brand_voice",
    "communication": "brand_voice",
    "goals": "goals",
    "goal": "goals",
    "objectives": "goals",
    "success measures": "success_measures",
    "success metrics": "success_measures",
    "kpis": "success_measures",
    "metrics": "success_measures",
    "how we measure success": "success_measures",
    "processes": "processes",
    "process": "processes",
    "how we work": "processes",
    "workflow": "processes",
    "team": "team_responsibilities",
    "responsibilities": "team_responsibilities",
    "roles": "team_responsibilities",
    "team responsibilities": "team_responsibilities",
    "integrations": "integrations_required",
    "tools": "integrations_required",
    "crm": "integrations_required",
    "required integrations": "integrations_required",
    "data": "data_available",
    "data sources": "data_available",
    "available data": "data_available",
    "constraints": "operational_constraints",
    "operational constraints": "operational_constraints",
    "limits": "operational_constraints",
    "approvals": "approval_requirements",
    "approval": "approval_requirements",
    "approval requirements": "approval_requirements",
    "review": "approval_requirements",
    "scope": "service_scope",
    "service scope": "service_scope",
    "engagement": "service_scope",
}

#: Prose patterns. These read a statement out of a sentence, so they are
#: always `assumption` — the writer did not fill in a field. Only the first
#: match per pattern is kept, so free text never manufactures a conflict.
PROSE_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "legal_name",
        "Opening sentence names the business",
        re.compile(
            r"^\s{0,3}([A-Z][\w&'.,-]{1,40}(?:\s+[A-Z][\w&'.,-]{1,40}){0,5})"
            r"\s+(?:helps|helping|is an?|offers|provides|sells|works with)\b",
            re.MULTILINE,
        ),
    ),
    (
        "products_services",
        "Offer statement",
        re.compile(
            r"\b(?:we|they)\s+(?:sell|offer|provide|build|make|deliver|specialise in|"
            r"specialize in)\s+([^.!?\n]{3,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "core_value_prop",
        "Stated promise",
        re.compile(
            r"\b(?:our (?:promise|value prop\w*)|the value proposition)\s*"
            r"(?:is|:)\s*([^.!?\n]{4,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "exclusion_rules",
        "Negated audience statement",
        re.compile(
            r"\b(?:we|our team|clients?)\s+(?:don'?t|do not|never|won'?t)\s+"
            r"(?:work with|serve|accept|target|contact)\s+([^.!?\n]{4,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "qualification_rules",
        "Audience narrowing statement",
        re.compile(
            r"\b(?:we|our team)\s+(?:only|exclusively)\s+"
            r"(?:work with|serve|accept|target|sell to)\s+([^.!?\n]{4,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "ideal_customer_profile",
        "Ideal-customer statement",
        re.compile(
            r"\bour\s+(?:ideal\s+customer|icp|best\s+customer)\s+"
            r"(?:is|are)\s+([^.!?\n]{4,240})",
            re.IGNORECASE,
        ),
    ),
    (
        "target_market",
        "Audience statement",
        re.compile(
            r"\bwe\s+(?:help|helping|work with|sell to)\s+"
            r"([^.!?\n]{4,240})",
            re.IGNORECASE,
        ),
    ),
    (
        "geography",
        "Geographic statement",
        re.compile(
            r"\b(?:based in|serving|available in|operating in)\s+"
            r"([A-Z][\w'&,.-]*(?:\s+[A-Z][\w'&,.-]*){0,5})",
        ),
    ),
    (
        "goals",
        "Goal statement",
        re.compile(
            r"\b(?:our\s+)?(?:goal|objective|target)\s+(?:is|are)?\s*"
            r"[:\-]?\s*([^.!?\n]{4,240})",
            re.IGNORECASE,
        ),
    ),
    (
        "success_measures",
        "Success-measure statement",
        re.compile(
            r"\b(?:we measure success|success (?:is|looks like)|"
            r"key (?:metrics|kpis?))\s*(?:by|with|[:\-])?\s*([^.!?\n]{4,240})",
            re.IGNORECASE,
        ),
    ),
    (
        "brand_voice",
        "Tone statement",
        re.compile(
            r"\b(?:our\s+)?(?:brand\s+)?tone\s+(?:is|should be|must be)\s+"
            r"([^.!?\n]{3,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "service_scope",
        "Scope statement",
        re.compile(
            r"\b(?:scope of (?:work|engagement)|we are (?:hired|engaged) to|"
            r"your scope)\s*(?:is|are|:)?\s*([^.!?\n]{4,240})",
            re.IGNORECASE,
        ),
    ),
)

_SECTION_HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s+|\*\*|__)?([A-Za-z][A-Za-z /&'-]{2,60}?)(?:\*\*|__)?\s*:?\s*$")
_LABELED = re.compile(r"^\s*(?:[-*•]\s*)?([A-Za-z][A-Za-z /&'.,()-]{1,60})\s*:\s*(.+)$")
_NAME_LABELED = re.compile(
    r"^\s*(?:business name|company name|company|client name|legal name)\s*:\s*(.+)$",
    re.IGNORECASE,
)

_STATUS_RANK = {"confirmed": 0, "assumption": 1, "unknown": 2}


@dataclass
class Claim:
    key: str
    value: str
    status: str
    confidence: float
    source_id: str
    source_label: str
    basis: str


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip().strip("-•*")
    text = text.strip(" .;:")
    return text[:2000]


def _alias_for(label: str) -> str | None:
    normalised = re.sub(r"[^a-z ]", "", label.lower()).strip()
    normalised = re.sub(r"\s+", " ", normalised)
    if normalised in ALIASES:
        return ALIASES[normalised]
    for alias, key in ALIASES.items():
        if normalised == alias or normalised.startswith(alias + " "):
            return key
    return None


def _claims_from_labels(source: Source) -> Iterable[Claim]:
    """`Label: value` lines — the writer filled in a field on purpose."""
    current_key: str | None = None
    bucket: list[str] = []

    def flush() -> Iterable[Claim]:
        if current_key and bucket:
            yield Claim(
                key=current_key,
                value=_clean("; ".join(bucket)),
                status="confirmed",
                confidence=0.95,
                source_id=source.id,
                source_label=source.label,
                basis="stated as a labelled value",
            )

    for raw_line in source.text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        name_match = _NAME_LABELED.match(line)
        if name_match:
            yield from flush()
            current_key, bucket = None, []
            yield Claim(
                key="legal_name",
                value=_clean(name_match.group(1)),
                status="confirmed",
                confidence=0.95,
                source_id=source.id,
                source_label=source.label,
                basis="stated as a labelled value",
            )
            continue

        heading = _SECTION_HEADING.match(line)
        if heading:
            yield from flush()
            current_key = _alias_for(heading.group(1))
            bucket = []
            continue

        labeled = _LABELED.match(line)
        if labeled:
            key = _alias_for(labeled.group(1))
            if key:
                yield from flush()
                current_key = key
                bucket = [_clean(labeled.group(2))]
                continue
            if current_key and line.lstrip().startswith(("-", "*", "•")):
                # A bullet under an open section, phrased "label: value".
                bucket.append(_clean(labeled.group(2)))
                continue
            yield from flush()
            current_key, bucket = None, []
            continue

        if current_key and (line.lstrip().startswith(("-", "*", "•", "|")) or line.startswith(" ")):
            bucket.append(_clean(line.lstrip("-•* |")))
            continue
        if current_key and not line.lstrip().startswith("#"):
            # Continuation of an open labelled value.
            bucket.append(_clean(line))
            continue
        yield from flush()
        current_key, bucket = None, []

    yield from flush()


def _claims_from_prose(source: Source) -> Iterable[Claim]:
    for key, basis, pattern in PROSE_PATTERNS:
        match = pattern.search(source.text)
        if match is None:
            continue
        value = _clean(match.group(1))
        if len(value) < 4:
            continue
        yield Claim(
            key=key,
            value=value,
            status="assumption",
            confidence=0.6,
            source_id=source.id,
            source_label=source.label,
            basis=basis,
        )


def _claims_from_website(source: Source) -> Iterable[Claim]:
    """Website text carries the site's own words — trusted, but the site
    describes itself, so it is `confirmed` for identity and description."""
    for line in source.text.splitlines():
        if line.startswith("Site title:"):
            title = _clean(line.split(":", 1)[1])
            name = re.split(r"\s+[|—–-]\s+", title)[0].strip()
            if name:
                yield Claim("legal_name", _clean(name), "confirmed", 0.85,
                            source.id, source.label, "website title")
            if title:
                yield Claim("business_description", title, "confirmed", 0.8,
                            source.id, source.label, "website title")
        elif line.startswith("Site description:"):
            value = _clean(line.split(":", 1)[1])
            if value:
                yield Claim("business_description", value, "confirmed", 0.9,
                            source.id, source.label, "website meta description")
                yield Claim("differentiators", value, "assumption", 0.5,
                            source.id, source.label, "website positioning copy")
        elif line.startswith("Heading:"):
            heading = _clean(line.split(":", 1)[1])
            if heading and len(heading) < 120:
                key = _alias_for(heading)
                if key:
                    yield Claim(key, heading, "confirmed", 0.7,
                                source.id, source.label, "website heading")

    for key, basis, pattern in PROSE_PATTERNS:
        match = pattern.search(source.text)
        if match is None:
            continue
        value = _clean(match.group(1))
        if len(value) >= 4:
            yield Claim(key, value, "assumption", 0.55,
                        source.id, source.label, f"website {basis.lower()}")


def collect_claims(sources: list[Source]) -> list[Claim]:
    claims: list[Claim] = []
    for source in sources:
        if source.status not in ("ready", "truncated") or not source.text.strip():
            continue
        if source.type == "website":
            claims.extend(_claims_from_website(source))
        else:
            claims.extend(_claims_from_labels(source))
            claims.extend(_claims_from_prose(source))
    return claims


def _resolve(claims: list[Claim]) -> tuple[dict[str, dict], list[dict]]:
    """Pick one value per field and surface every disagreement."""
    by_key: dict[str, list[Claim]] = {}
    for claim in claims:
        if claim.value:
            by_key.setdefault(claim.key, []).append(claim)

    fields: dict[str, dict] = {}
    conflicts: list[dict] = []

    for key in FIELD_ORDER:
        label = FIELD_LABELS[key]
        group = by_key.get(key, [])
        if not group:
            fields[key] = {
                "key": key, "label": label, "value": "", "status": "unknown",
                "confidence": 0.0, "sources": [], "basis": "not stated in any source",
            }
            continue

        ordered = sorted(
            group,
            key=lambda c: (_STATUS_RANK.get(c.status, 9), -c.confidence, c.source_label),
        )
        winner = ordered[0]
        same_value = [c for c in ordered if _normalise(c.value) == _normalise(winner.value)]
        others = [c for c in ordered if _normalise(c.value) != _normalise(winner.value)]

        sources_seen: list[str] = []
        for claim in same_value:
            if claim.source_id not in sources_seen:
                sources_seen.append(claim.source_id)

        note = winner.basis
        if others:
            seen_values: list[str] = []
            values = []
            for claim in same_value + others:
                norm = _normalise(claim.value)
                if norm in seen_values:
                    continue
                seen_values.append(norm)
                values.append({
                    "value": claim.value, "source": claim.source_label,
                    "status": claim.status, "confidence": claim.confidence,
                })
            conflicts.append({
                "key": key, "label": label, "values": values,
                "chosen": winner.value, "chosen_from": winner.source_label,
                "resolution": "needs_decision",
            })
            note = f"{winner.basis}; conflicts with other source(s) — confirm before activation"

        fields[key] = {
            "key": key,
            "label": label,
            "value": winner.value,
            "status": winner.status,
            "confidence": round(winner.confidence, 2),
            "sources": sources_seen,
            "basis": note,
        }

    return fields, conflicts


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())[:120]


#: Bucket → how the industry reads on screen. Used only when a keyword in
#: the sources actually matched; `agency` is the silent fallback, so it
#: never prefills an industry the sources did not support.
INDUSTRY_LABELS: dict[str, str] = {
    "mortgage": "Mortgage and lending",
    "dental": "Dental",
    "healthcare": "Healthcare",
    "saas": "Software / SaaS",
}


def _set_field(
    fields: dict[str, dict], key: str, value: str, status: str,
    confidence: float, source_id: str, source_label: str, basis: str,
) -> None:
    if not value:
        return
    fields[key] = {
        "key": key,
        "label": FIELD_LABELS[key],
        "value": _clean(value),
        "status": status,
        "confidence": confidence,
        "sources": [source_id],
        "basis": basis,
    }


def _fallbacks(fields: dict[str, dict], sources: list[Source]) -> str:
    """Read the last few basics a source plainly states but no pattern
    matched. Every fallback fills an *unknown* field and is marked as an
    inference, so it still has to be confirmed."""
    if not fields["website_url"]["value"]:
        for source in sources:
            if source.type == "website" and source.url and source.status in ("ready", "error"):
                _set_field(fields, "website_url", source.url, "confirmed", 0.9,
                           source.id, source.label,
                           "supplied as the website source")
                break

    if not fields["business_description"]["value"]:
        for source in sources:
            if source.status not in ("ready", "truncated") or not source.text.strip():
                continue
            for line in source.text.splitlines():
                sentence = line.strip().strip("#* ").strip()
                if 20 <= len(sentence) <= 240:
                    _set_field(fields, "business_description", sentence,
                               "assumption", 0.5, source.id, source.label,
                               "opening line of the supplied context")
                    break
            if fields["business_description"]["value"]:
                break

    hint = " ".join(filter(None, [
        fields["legal_name"]["value"], fields["industries_served"]["value"],
        fields["business_description"]["value"], fields["products_services"]["value"],
    ]))
    industry_key = _infer_industry_key(hint)
    if not fields["industry"]["value"] and industry_key in INDUSTRY_LABELS:
        _set_field(fields, "industry", INDUSTRY_LABELS[industry_key], "assumption",
                   0.55, "sources", "all sources",
                   "inferred from keywords in the supplied context — confirm")
    return industry_key


def extract_profile(sources: list[Source]) -> dict:
    """Sources → canonical business profile draft with provenance."""
    claims = collect_claims(sources)
    fields, conflicts = _resolve(claims)
    industry_key = _fallbacks(fields, sources)

    corpus = "\n".join(s.text for s in sources if s.text)

    unknown = [k for k, f in fields.items() if f["status"] == "unknown"]
    assumptions = [k for k, f in fields.items() if f["status"] == "assumption"]

    website_urls = [s.url for s in sources if s.type == "website" and s.url]

    return {
        "fields": fields,
        "conflicts": conflicts,
        "industry_key": industry_key,
        "website_url": website_urls[0] if website_urls else "",
        "counts": {
            "confirmed": sum(1 for f in fields.values() if f["status"] == "confirmed"),
            "assumption": len(assumptions),
            "unknown": len(unknown),
            "conflicts": len(conflicts),
        },
        "unknown_keys": unknown,
        "assumption_keys": assumptions,
        "corpus_chars": len(corpus),
    }


def field_value(draft: dict, key: str, answers: dict | None = None) -> str:
    """Answer wins over extraction; extraction wins over nothing."""
    if answers and str(answers.get(key, "")).strip():
        return _clean(str(answers[key]))
    field = draft.get("fields", {}).get(key) or {}
    return str(field.get("value") or "").strip()


def apply_answer(draft: dict, key: str, value: str) -> None:
    """Record an operator answer as a confirmed, sourced fact."""
    if key not in FIELD_LABELS or not str(value).strip():
        return
    draft.setdefault("fields", {})[key] = {
        "key": key,
        "label": FIELD_LABELS[key],
        "value": _clean(str(value)),
        "status": "confirmed",
        "confidence": 1.0,
        "sources": ["operator_answer"],
        "basis": "answered by the operator during setup",
    }
    unknown = [k for k in draft.get("unknown_keys", []) if k != key]
    draft["unknown_keys"] = unknown
    counts = draft.setdefault("counts", {})
    counts["unknown"] = max(0, int(counts.get("unknown", 0)) - 1)
    counts["confirmed"] = int(counts.get("confirmed", 0)) + 1
