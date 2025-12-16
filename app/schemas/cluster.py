from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClusterResponse(BaseModel):
    """Response model for cluster."""
    
    id: UUID = Field(..., description="Cluster unique identifier")
    user_id: UUID = Field(..., description="User unique identifier")
    document_count: int = Field(..., description="Number of documents in cluster")
    avg_sentiment: float | None = Field(None, description="Average sentiment score")
    trending_score: float | None = Field(None, description="Trending score (0.0 to 1.0)")
    created_at: datetime = Field(..., description="Cluster creation timestamp")
    updated_at: datetime = Field(..., description="Cluster last update timestamp")
    
    model_config = {"from_attributes": True}


class ClustersListResponse(BaseModel):
    """Response model for clusters list."""
    
    clusters: list[ClusterResponse] = Field(..., description="List of clusters ordered by trending score")
    total: int = Field(..., description="Total number of clusters")

