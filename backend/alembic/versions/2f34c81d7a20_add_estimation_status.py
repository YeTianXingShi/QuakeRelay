"""add estimation status

Revision ID: 2f34c81d7a20
Revises: 13aa8a52fffc
Create Date: 2026-07-12 15:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f34c81d7a20"
down_revision: str | Sequence[str] | None = "13aa8a52fffc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("impact_estimates") as batch_op:
        batch_op.add_column(
            sa.Column(
                "estimation_status",
                sa.String(length=32),
                nullable=False,
                server_default="estimated",
            )
        )
        batch_op.add_column(sa.Column("estimation_error", sa.String(length=500), nullable=True))
    op.execute(
        """
        UPDATE impact_estimates
        SET estimation_status = CASE
            WHEN estimated_intensity IS NOT NULL THEN 'estimated'
            WHEN epicentral_distance_km > 1000 THEN 'out_of_range'
            ELSE 'insufficient_data'
        END
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("impact_estimates") as batch_op:
        batch_op.drop_column("estimation_error")
        batch_op.drop_column("estimation_status")
