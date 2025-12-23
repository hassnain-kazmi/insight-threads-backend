from collections.abc import Sequence

from alembic import op

revision: str = "20251215_012743"
down_revision: str = "20251208_213607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Create IVFFlat index on document_embeddings.embedding for efficient vector similarity search.

    IVFFlat index speeds up approximate nearest neighbor (ANN) queries using cosine distance.
    The index uses 100 lists as a default configuration, which provides good performance
    for datasets with up to ~100k vectors. For larger datasets, consider increasing the
    number of lists (recommended: sqrt(total_rows) up to total_rows/1000).

    Note: IVFFlat index requires some data in the table to build effectively. If the table
    is empty, the index will still be created but may need to be rebuilt once data is loaded.
    """

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_embeddings_embedding_ivfflat
        ON document_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
        """
    )


def downgrade() -> None:
    """Drop the IVFFlat index on document_embeddings.embedding."""
    op.execute("DROP INDEX IF EXISTS idx_document_embeddings_embedding_ivfflat;")
