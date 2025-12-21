from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentSearchResult(BaseModel):
    """Response model for a document search result."""
    
    id: UUID = Field(..., description="Document unique identifier")
    title: str | None = Field(None, description="Document title")
    source_path: str | None = Field(None, description="Document source path")
    similarity_score: float = Field(..., description="Similarity score (lower is more similar)")
    created_at: datetime = Field(..., description="Document creation timestamp")
    
    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    """Response model for search results."""
    
    results: list[DocumentSearchResult] = Field(..., description="List of search results")
    total: int = Field(..., description="Total number of results returned")
    query: str = Field(..., description="Search query text")
