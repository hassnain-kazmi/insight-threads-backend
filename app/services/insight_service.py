import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cluster, Insight

logger = logging.getLogger(__name__)


async def get_insight(
    insight_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Insight | None:
    """
    Get insight by ID.

    Returns insight details. Only returns insights for clusters owned by the specified user.

    Args:
        insight_id: Insight unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session

    Returns:
        Insight object, or None if not found or cluster not owned by user
    """
    query = (
        select(Insight)
        .join(Cluster, Insight.cluster_id == Cluster.id)
        .where(Insight.id == insight_id, Cluster.user_id == user_id)
    )

    result = await db.execute(query)
    insight = result.scalar_one_or_none()

    if insight:
        logger.info(f"Retrieved insight {insight_id} for user {user_id}")
    else:
        logger.debug(
            f"Insight {insight_id} not found or cluster not owned by user {user_id}"
        )

    return insight


async def get_insights(
    user_id: UUID,
    db: AsyncSession,
    cluster_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Insight], int]:
    """
    Get insights for a user with optional cluster filter.

    Returns insights filtered by cluster. Only returns insights for clusters owned by the specified user.

    Args:
        user_id: User unique identifier
        db: Database session
        cluster_id: Optional cluster ID filter
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)

    Returns:
        Tuple of (list of insights, total count)
    """
    query = (
        select(Insight)
        .join(Cluster, Insight.cluster_id == Cluster.id)
        .where(Cluster.user_id == user_id)
    )

    if cluster_id:
        query = query.where(Insight.cluster_id == cluster_id)

    count_query = (
        select(func.count(Insight.id))
        .join(Cluster, Insight.cluster_id == Cluster.id)
        .where(Cluster.user_id == user_id)
    )

    if cluster_id:
        count_query = count_query.where(Insight.cluster_id == cluster_id)

    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0

    data_query = query.order_by(Insight.generated_at.desc()).limit(limit).offset(offset)

    result = await db.execute(data_query)
    insights = result.scalars().all()

    logger.info(
        f"Retrieved {len(insights)} insights for user {user_id} "
        f"(offset: {offset}, limit: {limit})"
    )

    return insights, total
