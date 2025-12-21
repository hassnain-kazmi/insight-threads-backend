import logging
from uuid import UUID

from sqlalchemy import select
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
        .where(
            Insight.id == insight_id,
            Cluster.user_id == user_id
        )
    )
    
    result = await db.execute(query)
    insight = result.scalar_one_or_none()
    
    if insight:
        logger.info(f"Retrieved insight {insight_id} for user {user_id}")
    else:
        logger.debug(f"Insight {insight_id} not found or cluster not owned by user {user_id}")
    
    return insight

