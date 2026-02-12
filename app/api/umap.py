import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.umap import ClusterUMAPResponse, DocumentUMAPResponse
from app.services.umap_service import (
    get_cluster_umap_projections,
    get_user_umap_projections,
)
from app.utils.auth import get_current_user
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/umap", tags=["umap"])


@router.get(
    "/clusters/{cluster_id}",
    status_code=status.HTTP_200_OK,
    response_model=ClusterUMAPResponse,
)
async def get_cluster_umap_endpoint(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    model_name: str = Query(settings.OLLAMA_MODEL, description="UMAP model name"),
) -> ClusterUMAPResponse:
    """
    Get UMAP projections for all documents in a cluster.

    Returns document positions in UMAP space for visualization.
    Only returns projections for clusters owned by the authenticated user.

    Args:
        cluster_id: Cluster unique identifier (UUID)
        current_user: Authenticated user from JWT token
        db: Database session
        model_name: UMAP model name to filter by (default: DEFAULT_MODEL_NAME)

    Returns:
        ClusterUMAPResponse with document projections

    Raises:
        HTTPException: 404 if cluster not found or not owned by user
    """
    try:
        try:
            cluster_uuid = UUID(cluster_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cluster ID format",
            )

        projections = await get_cluster_umap_projections(
            cluster_id=cluster_uuid,
            user_id=current_user.id,
            db=db,
            model_name=model_name,
        )

        if not projections:
            return ClusterUMAPResponse(
                documents=[],
                total=0,
            )

        document_responses = [
            DocumentUMAPResponse(
                document_id=document.id,
                title=document.title,
                source_path=document.source_path,
                cluster_id=primary_cluster_id,
                x=projection.x,
                y=projection.y,
            )
            for document, projection, primary_cluster_id in projections
        ]

        return ClusterUMAPResponse(
            documents=document_responses,
            total=len(document_responses),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving UMAP projections for cluster {cluster_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve UMAP projections",
        )


@router.get(
    "/documents", status_code=status.HTTP_200_OK, response_model=ClusterUMAPResponse
)
async def get_user_umap_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    model_name: str = Query(settings.OLLAMA_MODEL, description="UMAP model name"),
    limit: int = Query(
        1000, description="Maximum number of projections to return", ge=1, le=5000
    ),
) -> ClusterUMAPResponse:
    """
    Get UMAP projections for all documents belonging to the authenticated user.

    Returns document positions in UMAP space for visualization.

    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        model_name: UMAP model name to filter by (default: DEFAULT_MODEL_NAME)
        limit: Maximum number of projections to return (default: 1000, max: 5000)

    Returns:
        ClusterUMAPResponse with document projections
    """
    try:
        projections = await get_user_umap_projections(
            user_id=current_user.id,
            db=db,
            model_name=model_name,
            limit=limit,
        )

        if not projections:
            return ClusterUMAPResponse(
                documents=[],
                total=0,
            )

        document_responses = [
            DocumentUMAPResponse(
                document_id=document.id,
                title=document.title,
                source_path=document.source_path,
                cluster_id=primary_cluster_id,
                x=projection.x,
                y=projection.y,
            )
            for document, projection, primary_cluster_id in projections
        ]

        return ClusterUMAPResponse(
            documents=document_responses,
            total=len(document_responses),
        )

    except Exception as e:
        logger.error(
            f"Error retrieving UMAP projections for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve UMAP projections",
        )
