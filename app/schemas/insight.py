from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class InsightResponse(BaseModel):
    """Response model for insight."""

    id: UUID = Field(..., description="Insight unique identifier")
    cluster_id: UUID = Field(..., description="Cluster unique identifier")
    insight_text: str = Field(..., description="Insight text content")
    confidence: float | None = Field(None, description="Confidence score (0.0 to 1.0)")
    generated_at: datetime = Field(..., description="Insight generation timestamp")
    llm_metadata: str | None = Field(None, description="LLM metadata JSON string")

    model_config = {"from_attributes": True}


class InsightsListResponse(BaseModel):
    """Response model for insights list."""

    insights: list[InsightResponse] = Field(..., description="List of insights")
    total: int = Field(..., description="Total number of insights")
