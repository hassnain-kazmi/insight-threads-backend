import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Cluster

logger = logging.getLogger(__name__)


async def get_clusters(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Cluster], int]:
    """
    Get clusters for a user, ordered by trending score (descending).
    
    Args:
        user_id: User unique identifier
        db: Database session
        limit: Maximum number of clusters to return (default: 100)
        offset: Number of clusters to skip (default: 0)
        
    Returns:
        Tuple of (list of clusters, total count)
    """
    query = (
        select(Cluster)
        .where(Cluster.user_id == user_id)
        .order_by(Cluster.trending_score.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    
    result = await db.execute(query)
    clusters = result.scalars().all()
    
    count_query = select(func.count(Cluster.id)).where(Cluster.user_id == user_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0
    
    logger.info(f"Retrieved {len(clusters)} clusters for user {user_id} (offset: {offset}, limit: {limit})")
    
    return clusters, total


async def get_cluster_detail(
    cluster_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Cluster | None:
    """
    Get detailed information about a specific cluster.
    
    Returns cluster details including keywords and timeseries summaries.
    Only returns clusters owned by the specified user.
    
    Args:
        cluster_id: Cluster unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session
        
    Returns:
        Cluster object with relationships loaded, or None if not found/not owned by user
    """
    query = (
        select(Cluster)
        .options(
            selectinload(Cluster.keywords),
            selectinload(Cluster.timeseries)
        )
        .where(
            Cluster.id == cluster_id,
            Cluster.user_id == user_id
        )
    )
    
    result = await db.execute(query)
    cluster = result.scalar_one_or_none()
    
    if cluster:
        logger.info(f"Retrieved cluster detail {cluster_id} for user {user_id}")
    else:
        logger.debug(f"Cluster {cluster_id} not found or not owned by user {user_id}")
    
    return cluster

