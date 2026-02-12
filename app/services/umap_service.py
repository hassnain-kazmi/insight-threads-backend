import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.embeddings import DEFAULT_MODEL_NAME
from app.models import Cluster, ClusterMember, Document, UMAPProjection

logger = logging.getLogger(__name__)


async def get_cluster_umap_projections(
    cluster_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    model_name: str = DEFAULT_MODEL_NAME,
) -> list[tuple[Document, UMAPProjection, UUID | None]]:
    """
    Get UMAP projections for all documents in a cluster.

    Args:
        cluster_id: Cluster unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session
        model_name: UMAP model name to filter by (default: DEFAULT_MODEL_NAME)

    Returns:
        List of tuples containing (Document, UMAPProjection, primary_cluster_id)
    """

    cluster_query = select(Cluster).where(
        Cluster.id == cluster_id, Cluster.user_id == user_id
    )
    cluster_result = await db.execute(cluster_query)
    cluster = cluster_result.scalar_one_or_none()

    if not cluster:
        return []

    query = (
        select(Document, UMAPProjection)
        .select_from(Document)
        .join(ClusterMember, Document.id == ClusterMember.document_id)
        .outerjoin(
            UMAPProjection,
            (UMAPProjection.document_id == Document.id)
            & (UMAPProjection.model_name == model_name),
        )
        .where(
            ClusterMember.cluster_id == cluster_id,
            Document.user_id == user_id,
        )
    )

    result = await db.execute(query)
    rows = result.all()

    projections = []
    for row in rows:
        document, projection = row
        if projection:
            projections.append((document, projection, cluster_id))

    logger.info(
        f"Retrieved {len(projections)} UMAP projections for cluster {cluster_id}"
    )

    return projections


async def get_user_umap_projections(
    user_id: UUID,
    db: AsyncSession,
    model_name: str = DEFAULT_MODEL_NAME,
    limit: int = 1000,
) -> list[tuple[Document, UMAPProjection, UUID | None]]:
    """
    Get UMAP projections for all documents belonging to a user.

    Args:
        user_id: User unique identifier
        db: Database session
        model_name: UMAP model name to filter by (default: DEFAULT_MODEL_NAME)
        limit: Maximum number of projections to return

    Returns:
        List of tuples containing (Document, UMAPProjection, primary_cluster_id)
    """

    subquery = select(
        ClusterMember.document_id,
        ClusterMember.cluster_id,
        func.row_number()
        .over(
            partition_by=ClusterMember.document_id,
            order_by=ClusterMember.membership_strength.desc().nulls_last(),
        )
        .label("rn"),
    ).subquery()

    primary_cluster_subquery = (
        select(subquery.c.document_id, subquery.c.cluster_id)
        .where(subquery.c.rn == 1)
        .subquery()
    )

    query = (
        select(Document, UMAPProjection, primary_cluster_subquery.c.cluster_id)
        .select_from(Document)
        .outerjoin(
            UMAPProjection,
            (UMAPProjection.document_id == Document.id)
            & (UMAPProjection.model_name == model_name),
        )
        .outerjoin(
            primary_cluster_subquery,
            primary_cluster_subquery.c.document_id == Document.id,
        )
        .where(Document.user_id == user_id)
        .where(UMAPProjection.id.isnot(None))
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    projections = [
        (document, projection, cluster_id) for document, projection, cluster_id in rows
    ]

    logger.info(f"Retrieved {len(projections)} UMAP projections for user {user_id}")

    return projections
