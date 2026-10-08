"""add tryon_renders

Revision ID: c4e8f21a6d93
Revises: a7c3e5d19b42
Create Date: 2026-10-08 12:00:00.000000

Virtual try-on renders (09-virtual-tryon.md §6.6). Additive: a new table with its own claim
columns, so `job` is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8f21a6d93"
down_revision: str | None = "a7c3e5d19b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tryon_renders",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("cache_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("mannequin_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("garment_ids", sa.JSON(), nullable=False),
        sa.Column("skipped_garment_ids", sa.JSON(), nullable=False),
        sa.Column("unsupported_garment_ids", sa.JSON(), nullable=False),
        sa.Column("outfit_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "claimed",
                "running",
                "done",
                "failed",
                name="jobstatus",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("step", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("claimed_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("img_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("peak_vram_mb", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key", name="uq_tryon_renders_cache_key"),
    )
    op.create_index("idx_tryon_renders_status", "tryon_renders", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_tryon_renders_status", table_name="tryon_renders")
    op.drop_table("tryon_renders")
