from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251216_224745"
down_revision: str = "20251215_155030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clusters", sa.Column("trending_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("clusters", "trending_score")

