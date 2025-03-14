from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserLogs(BaseModel):
    id: int
    user_id: int
    username: str
    login_timestamp: datetime

    # Include other fields as needed

    class Config:
        orm_mode = True


class FolderCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    plant: str


class FolderUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requires_validity: bool
    is_mandatory: bool

    class Config:
        from_attributes = True


class PartNumberCreate(BaseModel):
    part_number: str
    description: Optional[str] = None
    is_active: bool
    inactive_date: Optional[int] = None  # Epoch timestamp
    plant: str

    def convert_inactive_date(self):
        if self.inactive_date is not None:
            return datetime.fromtimestamp(self.inactive_date)
        return None


class PartNumberUpdate(BaseModel):
    part_number: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    inactive_date: Optional[int] = None  # Epoch timestamp

    def convert_inactive_date(self):
        if self.inactive_date is not None:
            return datetime.fromtimestamp(self.inactive_date)
        return None

    class Config:
        from_attributes = True  # Use from_attributes instead of orm_mode in Pydantic V2


from typing import List


# Schema for the request body
class DocumentCreateRequest(BaseModel):
    part_numbers: List[str]
    folder_id: int


class PartNumberRequest(BaseModel):
    part_numbers: List[str]

class UpdateValidityRequest(BaseModel):
    file_name: str
    part_numbers: List[str]
    validity_date: str  # Keeping as string for now
    plant: str

