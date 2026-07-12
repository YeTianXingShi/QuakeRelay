"""purge deleted location impacts

Revision ID: c4a3180f9d22
Revises: b7d912ef463a
Create Date: 2026-07-12 19:00:00

This migration is intentionally irreversible because the user requested permanent deletion.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a3180f9d22"
down_revision: str | Sequence[str] | None = "b7d912ef463a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    deleted_ids = [
        str(row.id)
        for row in connection.execute(
            sa.text("SELECT id FROM locations WHERE deleted_at IS NOT NULL")
        )
    ]
    if not deleted_ids:
        return

    jobs = connection.execute(
        sa.text(
            "SELECT id, payload FROM notification_jobs "
            "WHERE earthquake_id IS NOT NULL"
        )
    ).all()
    for job in jobs:
        payload = json.loads(job.payload) if isinstance(job.payload, str) else job.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("impacts"), list):
            continue
        impacts = payload["impacts"]
        retained = [
            impact
            for impact in impacts
            if not isinstance(impact, dict) or impact.get("location_id") not in deleted_ids
        ]
        if len(retained) != len(impacts):
            payload["impacts"] = retained
            connection.execute(
                sa.text("UPDATE notification_jobs SET payload = :payload WHERE id = :id"),
                {"payload": json.dumps(payload, ensure_ascii=False), "id": job.id},
            )

    for location_id in deleted_ids:
        connection.execute(
            sa.text("DELETE FROM impact_estimates WHERE location_id = :location_id"),
            {"location_id": location_id},
        )
        connection.execute(
            sa.text("DELETE FROM locations WHERE id = :location_id"),
            {"location_id": location_id},
        )


def downgrade() -> None:
    # Permanently deleted user data cannot be reconstructed.
    pass
