"""Outfit engine package for pachapp (docs/specs/05-outfit-engine.md).

This package MUST stay pure: no I/O (no database session, no HTTP client, no
filesystem access) and no ML imports. It exists to be testable as plain
functions (see D1 in docs/architecture/c4.md).
"""

from engine.generate import generate_outfits
from engine.types import (
    EngineColor,
    EngineGarment,
    EngineSettings,
    GenerationRequest,
    InvalidRequest,
    PreferencePair,
    Proposal,
    ProposalItem,
    ScoreBreakdown,
    WornOutfit,
)

__all__ = [
    "EngineColor",
    "EngineGarment",
    "EngineSettings",
    "GenerationRequest",
    "InvalidRequest",
    "PreferencePair",
    "Proposal",
    "ProposalItem",
    "ScoreBreakdown",
    "WornOutfit",
    "generate_outfits",
]
