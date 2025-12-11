from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    """Response model for user."""
    
    user_id: UUID = Field(..., description="User unique identifier")
    email: str = Field(..., description="User email address")
    name: str | None = Field(None, description="User name")
    
    model_config = {"from_attributes": True}

