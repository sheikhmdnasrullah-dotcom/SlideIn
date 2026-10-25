"""Client setup: context in, usable workspace out.

    provide context -> generate setup -> review exceptions
    -> connect tools -> test -> activate

Modules:
    sources.py    normalise operator-supplied context (never invents text)
    extract.py    deterministic profile extraction with provenance + conflicts
    questions.py  the short list of decisions only a human can make
    blueprint.py  proposed modules, terminology, integrations, deployment config
    service.py    orchestration: generate / answer / status
"""

from __future__ import annotations

from .blueprint import propose_blueprint
from .extract import extract_profile
from .questions import build_questions, grouped, open_blocking
from .service import SETUP_STAGES, SetupService
from .sources import normalise_sources

__all__ = [
    "SETUP_STAGES",
    "SetupService",
    "build_questions",
    "extract_profile",
    "grouped",
    "normalise_sources",
    "open_blocking",
    "propose_blueprint",
]
