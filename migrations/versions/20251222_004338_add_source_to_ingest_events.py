from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251222_004338"
down_revision: str = "20251216_224745"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source column to ingest_events table."""
    op.add_column("ingest_events", sa.Column("source", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Remove source column from ingest_events table."""
    op.drop_column("ingest_events", "source")

