from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251215_021016"
down_revision: str = "20251215_012743"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Create umap_projections table to store 2D UMAP projections for document embeddings.

    This table stores precomputed 2D coordinates (x, y) for document embeddings,
    enabling interactive visualization in the frontend. Each projection is linked
    to a document and tracks which embedding model was used.
    """
    op.create_table(
        "umap_projections",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id", "model_name", name="uq_umap_projections_document_model"
        ),
    )


def downgrade() -> None:
    """Drop the umap_projections table."""
    op.drop_table("umap_projections")
