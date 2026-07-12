"""add telegram channel

Revision ID: 74c829a5e9f1
Revises: 2f34c81d7a20
Create Date: 2026-07-12 16:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "74c829a5e9f1"
down_revision: str | Sequence[str] | None = "2f34c81d7a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("webhook_endpoints") as batch_op:
        batch_op.add_column(
            sa.Column(
                "channel_type",
                sa.String(length=32),
                nullable=False,
                server_default="generic",
            )
        )
        batch_op.add_column(
            sa.Column(
                "encrypted_config",
                sa.LargeBinary(),
                nullable=False,
                server_default=sa.text("X''"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("webhook_endpoints") as batch_op:
        batch_op.drop_column("encrypted_config")
        batch_op.drop_column("channel_type")
