from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260119_145653"
down_revision: str = "20260111_195346"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clusters", sa.Column("name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("clusters", "name")
