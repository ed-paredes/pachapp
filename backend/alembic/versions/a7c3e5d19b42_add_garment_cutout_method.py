"""add garment.cutout_method

Revision ID: a7c3e5d19b42
Revises: 6df79e2c9cb0
Create Date: 2026-10-05 12:00:00.000000

Nullable marker of the cutout method/version a garment was last re-cut with
(`python -m worker.recut`, 08-local-vision.md VIS-REQ-032). Additive and nullable, so
existing rows stay valid (DAT-REQ-015 does not apply: nothing is dropped or restricted).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e5d19b42"
down_revision: str | None = "6df79e2c9cb0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("garment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cutout_method", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("garment", schema=None) as batch_op:
        batch_op.drop_column("cutout_method")
