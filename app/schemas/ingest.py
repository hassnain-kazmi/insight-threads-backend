from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TriggerIngestionRequest(BaseModel):
    """Request model for triggering ingestion."""
    
    source: str = Field(..., description="Data source type (e.g., 'rss')")
    source_params: dict = Field(default_factory=dict, description="Source-specific parameters")


class TriggerIngestionResponse(BaseModel):
    """Response model for ingestion trigger."""
    
    ingest_event_id: str = Field(..., description="UUID of the created ingestion event")
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Initial status of the ingestion event")


class IngestEventResponse(BaseModel):
    """Response model for ingest event."""
    
    id: UUID = Field(..., description="Ingest event unique identifier")
    user_id: UUID = Field(..., description="User unique identifier")
    started_at: datetime = Field(..., description="Ingestion start timestamp")
    completed_at: datetime | None = Field(None, description="Ingestion completion timestamp")
    status: str = Field(..., description="Ingestion status")
    error_message: str | None = Field(None, description="Error message if ingestion failed")
    updated_at: datetime = Field(..., description="Ingest event last update timestamp")
    
    model_config = {"from_attributes": True}


class IngestEventsListResponse(BaseModel):
    """Response model for ingest events list."""
    
    events: list[IngestEventResponse] = Field(..., description="List of ingest events")
    total: int = Field(..., description="Total number of ingest events")

