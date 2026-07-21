"""Create the Tahap 8 privacy-minimized metadata schema."""

from __future__ import annotations

from alembic import op
from backend.metadata.models import METADATA_SCHEMA, Base

revision = "20260720_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {METADATA_SCHEMA} AUTHORIZATION migration_user")
    Base.metadata.create_all(bind=connection, checkfirst=False)
    op.execute(f"REVOKE ALL ON SCHEMA {METADATA_SCHEMA} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {METADATA_SCHEMA} TO app_metadata_user")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "
        f"{METADATA_SCHEMA} TO app_metadata_user"
    )
    op.execute(
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {METADATA_SCHEMA} TO app_metadata_user"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE migration_user IN SCHEMA {METADATA_SCHEMA} "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_metadata_user"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE migration_user IN SCHEMA {METADATA_SCHEMA} "
        "GRANT USAGE, SELECT ON SEQUENCES TO app_metadata_user"
    )


def downgrade() -> None:
    connection = op.get_bind()
    Base.metadata.drop_all(bind=connection, checkfirst=False)
    op.execute(f"DROP SCHEMA IF EXISTS {METADATA_SCHEMA}")
