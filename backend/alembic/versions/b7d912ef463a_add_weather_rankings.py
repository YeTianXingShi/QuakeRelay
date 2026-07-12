"""add weather rankings

Revision ID: b7d912ef463a
Revises: 8c51a620b7ef
Create Date: 2026-07-12 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d912ef463a"
down_revision: str | Sequence[str] | None = "8c51a620b7ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "_alembic_tmp_webhook_endpoints" in tables:
        op.drop_table("_alembic_tmp_webhook_endpoints")
    location_columns = {column["name"] for column in inspector.get_columns("locations")}
    if "province" not in location_columns:
        op.add_column(
            "locations",
            sa.Column("province", sa.String(length=100), nullable=False, server_default="")
        )
    if "city" not in location_columns:
        op.add_column(
            "locations",
            sa.Column("city", sa.String(length=100), nullable=False, server_default="")
        )
    if "district" not in location_columns:
        op.add_column(
            "locations",
            sa.Column("district", sa.String(length=100), nullable=False, server_default="")
        )
    webhook_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("webhook_endpoints")
    }
    if "earthquake_enabled" not in webhook_columns:
        op.add_column(
            "webhook_endpoints",
            sa.Column("earthquake_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    if "weather_enabled" not in webhook_columns:
        op.add_column(
            "webhook_endpoints",
            sa.Column("weather_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_table(
        "weather_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hour_key", sa.String(length=12), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_rank", sa.JSON(), nullable=False),
        sa.Column("rain_rank", sa.JSON(), nullable=False),
        sa.Column("wind_rank", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_weather_snapshots_hour_key"), "weather_snapshots", ["hour_key"], unique=True
    )
    op.create_index(
        op.f("ix_weather_snapshots_observed_at"),
        "weather_snapshots",
        ["observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_weather_snapshots_observed_at"), table_name="weather_snapshots")
    op.drop_index(op.f("ix_weather_snapshots_hour_key"), table_name="weather_snapshots")
    op.drop_table("weather_snapshots")
    op.drop_column("webhook_endpoints", "weather_enabled")
    op.drop_column("webhook_endpoints", "earthquake_enabled")
    op.drop_column("locations", "district")
    op.drop_column("locations", "city")
    op.drop_column("locations", "province")
