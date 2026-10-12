"""add setting.tryon_gender and setting.tryon_skin_tone

Revision ID: d5f1a9b73e20
Revises: c4e8f21a6d93
Create Date: 2026-10-12 12:00:00.000000

Try-on dummy model settings (tryon-dummy V6b): the base gender and the flat skin tone (1-6).
Additive with server defaults, so the seeded singleton row gets woman / 3.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f1a9b73e20"
down_revision: str | None = "c4e8f21a6d93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("setting", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tryon_gender",
                sqlmodel.sql.sqltypes.AutoString(),
                server_default="woman",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("tryon_skin_tone", sa.Integer(), server_default="3", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("setting", schema=None) as batch_op:
        batch_op.drop_column("tryon_skin_tone")
        batch_op.drop_column("tryon_gender")
