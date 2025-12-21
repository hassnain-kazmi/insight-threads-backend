from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """Response model for document."""
    
    id: UUID = Field(..., description="Document unique identifier")
    user_id: UUID = Field(..., description="User unique identifier")
    ingest_event_id: UUID | None = Field(None, description="Ingest event unique identifier")
    source_path: str | None = Field(None, description="Document source path")
    title: str | None = Field(None, description="Document title")
    processed: bool = Field(..., description="Whether document has been processed")
    processed_at: datetime | None = Field(None, description="Document processing timestamp")
    created_at: datetime = Field(..., description="Document creation timestamp")
    updated_at: datetime = Field(..., description="Document last update timestamp")
    
    model_config = {"from_attributes": True}


class DocumentsListResponse(BaseModel):
    """Response model for documents list."""
    
    documents: list[DocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total number of documents")

