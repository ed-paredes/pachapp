"""SQLModel tables for pachapp (docs/specs/02-data-model.md).

Conventions (see the spec's "Convenciones" section):
- Every primary key is a UUIDv4 stored as `TEXT` (SQLite has no native UUID
  type), except `setting.id` which is a fixed singleton integer.
- Every timestamp is `DATETIME` in UTC, written by the application layer
  (never a DB `server_default`) — the `default_factory=_utcnow` on `created_
  at`/`updated_at` fields is that application-layer write happening at
  construction time, not a database-side default.
- JSON columns are stored as SQLite `TEXT` via SQLAlchemy's `JSON` type.
  SQLite has no native JSON type, so **every** read/write of these columns
  MUST go through the matching Pydantic model in `shared.schemas` — never
  direct dict/list access. The column's Python-side type here is the raw
  JSON-compatible shape (`dict`/`list`), not the Pydantic model itself.

DAT-REQ-001: enums are imported from `shared.enums`, never redefined here.
"""

from datetime import UTC, datetime
from datetime import date as _Date
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON as SAJSON
from sqlalchemy import CheckConstraint, Column, Index, LargeBinary, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel

from shared.enums import (
    GarmentCategory,
    GarmentPattern,
    GarmentStatus,
    JobStatus,
    JobStep,
    OutfitSlot,
    OutfitSource,
)


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sa_enum(enum_cls: type[StrEnum]) -> SAEnum:
    """A SQLite-friendly `Enum` column: plain `TEXT` storing `.value`, no
    generated `CHECK` constraint (02's tables document these as `TEXT
    (enum)`, not `TEXT` with a `CHECK` — closed-set validation for these
    columns happens at the application/Pydantic boundary, D16)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Garment(SQLModel, table=True):
    __tablename__ = "garment"
    __table_args__ = (
        Index("idx_garment_status", "status"),
        Index("idx_garment_category", "category"),
        Index("idx_garment_needs_review", "needs_review"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

    img_original: str = Field(nullable=False)
    img_cutout: str | None = Field(default=None, nullable=True)
    img_thumb: str | None = Field(default=None, nullable=True)

    category: GarmentCategory | None = Field(
        default=None, sa_column=Column(_sa_enum(GarmentCategory), nullable=True)
    )
    subcategory: str | None = Field(default=None, nullable=True)
    colors: list[dict] | None = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    is_neutral: bool | None = Field(default=None, nullable=True)
    pattern: GarmentPattern | None = Field(
        default=None, sa_column=Column(_sa_enum(GarmentPattern), nullable=True)
    )
    formality: int | None = Field(default=None, nullable=True)
    style_tags: list[str] | None = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    seasons: list[str] | None = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    warmth: int | None = Field(default=None, nullable=True)
    material: str | None = Field(default=None, nullable=True)
    brand: str | None = Field(default=None, nullable=True)
    notes: str | None = Field(default=None, nullable=True)

    status: GarmentStatus = Field(
        default=GarmentStatus.active,
        sa_column=Column(_sa_enum(GarmentStatus), nullable=False),
    )

    # Vector float32, dimension read from the model at runtime (never fixed
    # in code, VIS-REQ-002); null until the `embedding` worker step runs.
    embedding: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    # `<model id>@<revision>`, DAT-REQ-020.
    embedding_model: str | None = Field(default=None, nullable=True)
    embedding_dim: int | None = Field(default=None, nullable=True)

    # `{field: {value, confidence, source}}`, DAT-REQ-021 — see
    # `shared.schemas.AiConfidence`.
    ai_confidence: dict | None = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    color_confidence: float | None = Field(default=None, nullable=True)

    needs_review: bool = Field(default=False, nullable=False)
    user_verified: bool = Field(default=False, nullable=False)
    wear_count: int = Field(default=0, nullable=False)
    last_worn_at: _Date | None = Field(default=None, nullable=True)

    outfit_items: list["OutfitItem"] = Relationship(back_populates="garment")
    jobs: list["Job"] = Relationship(back_populates="garment")
    ai_corrections: list["AiCorrection"] = Relationship(back_populates="garment")


class Outfit(SQLModel, table=True):
    __tablename__ = "outfit"
    __table_args__ = (CheckConstraint("rating IN (-1, 0, 1)", name="ck_outfit_rating"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    source: OutfitSource = Field(sa_column=Column(_sa_enum(OutfitSource), nullable=False))
    score: float | None = Field(default=None, nullable=True)
    # `{color, style, novelty, preference, total}` — see
    # `shared.schemas.ScoreBreakdown`.
    score_breakdown: dict | None = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    is_favorite: bool = Field(default=False, nullable=False)
    rating: int = Field(default=0, nullable=False)  # DAT-REQ-005: {-1, 0, 1}
    name: str | None = Field(default=None, nullable=True)
    explanation: str | None = Field(default=None, nullable=True)

    items: list["OutfitItem"] = Relationship(back_populates="outfit")
    wear_logs: list["WearLog"] = Relationship(back_populates="outfit")


class OutfitItem(SQLModel, table=True):
    __tablename__ = "outfit_item"
    __table_args__ = (
        Index("idx_outfit_item_outfit", "outfit_id"),
        Index("idx_outfit_item_garment", "garment_id"),
        UniqueConstraint("outfit_id", "garment_id", name="uq_outfit_item_outfit_garment"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    outfit_id: str = Field(foreign_key="outfit.id", nullable=False)
    garment_id: str = Field(foreign_key="garment.id", nullable=False)
    slot: OutfitSlot = Field(sa_column=Column(_sa_enum(OutfitSlot), nullable=False))
    # Stacking order for rendering; NULL for `accessory` rows (DAT-REQ-006).
    layer: int | None = Field(default=None, nullable=True)

    outfit: "Outfit" = Relationship(back_populates="items")
    garment: "Garment" = Relationship(back_populates="outfit_items")


class WearLog(SQLModel, table=True):
    __tablename__ = "wear_log"

    id: str = Field(default_factory=_uuid, primary_key=True)
    # Aliased on import (`_Date`) to avoid the annotation shadowing this
    # attribute's own name (both are `date`, DAT-REQ-007).
    date: _Date = Field(nullable=False, unique=True)
    outfit_id: str = Field(foreign_key="outfit.id", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    outfit: "Outfit" = Relationship(back_populates="wear_logs")


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = (Index("idx_job_status", "status"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    garment_id: str = Field(foreign_key="garment.id", nullable=False)
    status: JobStatus = Field(
        default=JobStatus.pending, sa_column=Column(_sa_enum(JobStatus), nullable=False)
    )
    step: JobStep | None = Field(default=None, sa_column=Column(_sa_enum(JobStep), nullable=True))
    progress: int = Field(default=0, nullable=False)
    attempts: int = Field(default=0, nullable=False)
    error: str | None = Field(default=None, nullable=True)
    # Non-error metadata, e.g. duplicate-candidate info — see
    # `shared.schemas.DuplicateCandidate`.
    result: dict | None = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    claimed_by: str | None = Field(default=None, nullable=True)
    claimed_at: datetime | None = Field(default=None, nullable=True)
    started_at: datetime | None = Field(default=None, nullable=True)
    finished_at: datetime | None = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    garment: "Garment" = Relationship(back_populates="jobs")


class Setting(SQLModel, table=True):
    """Singleton row (`id = 1`), seeded by an Alembic data migration on the
    first `make migrate` (docs/specs/02-data-model.md)."""

    __tablename__ = "setting"

    id: int = Field(default=1, primary_key=True)
    weight_color: float = Field(default=0.35, nullable=False)
    weight_style: float = Field(default=0.25, nullable=False)
    weight_novelty: float = Field(default=0.25, nullable=False)
    weight_preference: float = Field(default=0.15, nullable=False)
    no_repeat_days: int = Field(default=14, nullable=False)
    max_accessories: int = Field(default=2, nullable=False)
    duplicate_warning_threshold: float = Field(default=0.92, nullable=False)
    needs_review_threshold: float = Field(default=0.7, nullable=False)
    color_review_threshold: float = Field(default=0.7, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class AiCorrection(SQLModel, table=True):
    __tablename__ = "ai_correction"
    __table_args__ = (Index("idx_ai_correction_field", "field"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    garment_id: str = Field(foreign_key="garment.id", nullable=False)
    field: str = Field(nullable=False)
    ai_value: dict | list | str | int | float | bool = Field(
        sa_column=Column(SAJSON, nullable=False)
    )
    corrected_value: dict | list | str | int | float | bool = Field(
        sa_column=Column(SAJSON, nullable=False)
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    garment: "Garment" = Relationship(back_populates="ai_corrections")
