"""JSON-schema round trips for shared.schemas (D16): every JSON column's
Pydantic model must accept the shape 02 documents and reject an invalid one.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from shared.enums import ConfidenceSource
from shared.schemas import (
    AiConfidence,
    AttributeConfidence,
    ColorEntry,
    Colors,
    DuplicateCandidate,
    ScoreBreakdown,
)


def test_colors_round_trip_through_json_text() -> None:
    colors = Colors(
        root=[
            ColorEntry(name="marino", hex="#1a2b4c", lab=(30.0, 5.0, -20.0), proportion=0.7),
            ColorEntry(name="blanco", hex="#ffffff", lab=(95.0, 0.0, 0.0), proportion=0.3),
        ]
    )

    stored_text = colors.model_dump_json()  # what SQLite's JSON/TEXT column holds
    restored = Colors.model_validate(json.loads(stored_text))

    assert restored == colors
    assert restored.root[0].name == "marino"  # dominant color stays first


def test_colors_defaults_to_empty_list() -> None:
    assert Colors().root == []


def test_color_entry_proportion_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        ColorEntry(name="marino", hex="#1a2b4c", lab=(0.0, 0.0, 0.0), proportion=1.5)


def test_ai_confidence_round_trip_through_json_text() -> None:
    confidence = AiConfidence(
        root={
            "category": AttributeConfidence(
                value="top", confidence=0.92, source=ConfidenceSource.zero_shot
            ),
            "style_tags": AttributeConfidence(
                value=["casual", "minimal"], confidence=0.6, source=ConfidenceSource.knn
            ),
            "formality": AttributeConfidence(value=3, confidence=1.0, source=ConfidenceSource.user),
        }
    )

    stored_text = confidence.model_dump_json()
    restored = AiConfidence.model_validate(json.loads(stored_text))

    assert restored == confidence
    assert restored.root["formality"].source == ConfidenceSource.user


def test_attribute_confidence_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        AttributeConfidence(value="top", confidence=0.9, source="guess")  # type: ignore[arg-type]


def test_attribute_confidence_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AttributeConfidence(value="top", confidence=1.5, source=ConfidenceSource.llm)


def test_score_breakdown_round_trip() -> None:
    breakdown = ScoreBreakdown(color=0.8, style=0.6, novelty=0.5, preference=0.9, total=0.7)

    restored = ScoreBreakdown.model_validate(json.loads(breakdown.model_dump_json()))

    assert restored == breakdown


def test_duplicate_candidate_round_trip() -> None:
    candidate = DuplicateCandidate(
        duplicate_candidate_garment_id="11111111-1111-1111-1111-111111111111",
        similarity=0.95,
    )

    restored = DuplicateCandidate.model_validate(json.loads(candidate.model_dump_json()))

    assert restored == candidate


def test_duplicate_candidate_similarity_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        DuplicateCandidate(duplicate_candidate_garment_id="x", similarity=1.2)
