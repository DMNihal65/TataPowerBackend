from datetime import datetime

from pydantic import BaseModel
from typing import Optional, List


class FolderResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    created_at: str  # Ensure this is a string in ISO format
    updated_at: str  # Ensure this is a string in ISO format
    plant: Optional[str] = None

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
    plant: Optional[str] = None

    class Config:
        from_attributes = True  # Use from_attributes instead of orm_mode in Pydantic V2


class DocumentResponse(BaseModel):
    file_path: str
    part_number_ids: List[int]
    document_id: int
    folder_id: int  # Add folder_id to the response model
    part_numbers: List[str]  # Add part_numbers to the response model
    validity_date: str

class FilePathResponse(BaseModel):
    file_name: str
    file_path: str
    part_numbers: str
    validity_date: Optional[str]
    status:str

    class Config:
        orm_mode = True

class FolderDetailResponse(BaseModel):
    id: int
    parent_id: Optional[int] 
    name: str
    created_at: str
    updated_at: str
    file_name: List[FilePathResponse]
    plant: Optional[str] = None

    class Config:
        orm_mode = True

class DocumentStatusRequest(BaseModel):
    document_id: int
    status: str  # Expected values: "approved" or "rejected"