from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251215_155030"
down_revision: str = "20251215_021016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("timeseries_summary", sa.Column("momentum", sa.Float(), nullable=True))
    op.add_column("timeseries_summary", sa.Column("forecast_lower", sa.Float(), nullable=True))
    op.add_column("timeseries_summary", sa.Column("forecast_upper", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("timeseries_summary", "forecast_upper")
    op.drop_column("timeseries_summary", "forecast_lower")
    op.drop_column("timeseries_summary", "momentum")

