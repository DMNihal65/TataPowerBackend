from datetime import datetime

from pydantic import BaseModel
from typing import Optional


class FolderResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    requires_validity: bool
    is_mandatory: bool
    created_at: str  # Ensure this is a string in ISO format
    updated_at: str  # Ensure this is a string in ISO format

    class Config:
        orm_mode = True
        anystr_strip_whitespace = True

class PartNumberResponse(BaseModel):
    id: int
    part_number: str
    description: Optional[str] = None
    is_active: bool
    inactive_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Use from_attributes instead of orm_mode in Pydantic V2