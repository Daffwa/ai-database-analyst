"""Add privacy-minimized durable agent clarification continuations."""

from __future__ import annotations

from alembic import op
from backend.metadata.models import METADATA_SCHEMA, AgentContinuationRecord

revision = "20260816_0002"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    AgentContinuationRecord.__table__.create(bind=connection, checkfirst=True)
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON "
        f"{METADATA_SCHEMA}.agent_continuations TO app_metadata_user"
    )


def downgrade() -> None:
    connection = op.get_bind()
    AgentContinuationRecord.__table__.drop(bind=connection, checkfirst=True)
