from typing import List

from fastapi import APIRouter, Depends, status, HTTPException, Response, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from Auth.oauth2 import get_current_user
from Database.db_setup import get_db
from orm_class.orm_models import FolderMaster, User, PartNumber
from pydantic_schema.request_body import FolderCreateRequest, FolderUpdateRequest, PartNumberCreate, PartNumberUpdate
from pydantic_schema.respose_models import FolderResponse, PartNumberResponse

router = APIRouter(tags=['PartNumber-Handles'])


def require_role(required_role: str, current_user: User):
    if current_user.role != required_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/createpartnumbers/", response_model=PartNumberResponse)
def create_part_number(
        part_number: PartNumberCreate,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user)
):
    # require_role("admin", current_user)  # Check if the user has admin scope
    inactive_date = part_number.convert_inactive_date()

    db_part_number = PartNumber(
        part_number=part_number.part_number,
        description=part_number.description,
        is_active=part_number.is_active,
        inactive_date=inactive_date
    )

    db.add(db_part_number)
    db.commit()
    db.refresh(db_part_number)
    return db_part_number


@router.put("/updatepartnumbers/part_number", response_model=PartNumberResponse)
def update_part_number(
        part_number: str,
        part_number_update: PartNumberUpdate,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user),

):
    # require_role("admin", current_user)  # Check if the user has admin scope
    # Fetch the existing record
    db_part_number = db.query(PartNumber).filter(PartNumber.part_number == part_number).first()

    if db_part_number is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part number not found")

    # Update the record with new data
    if part_number_update.part_number is not None:
        db_part_number.part_number = part_number_update.part_number
    if part_number_update.description is not None:
        db_part_number.description = part_number_update.description
    if part_number_update.is_active is not None:
        db_part_number.is_active = part_number_update.is_active
    if part_number_update.inactive_date is not None:
        db_part_number.inactive_date = part_number_update.convert_inactive_date()

    db.commit()
    db.refresh(db_part_number)
    return db_part_number


@router.delete("/deletepartnumbers/part_number", status_code=status.HTTP_204_NO_CONTENT)
def delete_part_number(
        part_number: str,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user)
):
    # require_role("admin", current_user)  # Check if the user has admin scope

    # Query folder by name
    db_folder = db.query(PartNumber).filter(PartNumber.part_number == part_number).first()

    if db_folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    try:
        db.delete(db_folder)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error deleting folder.")


@router.get("/getallpartnumbers/", response_model=List[PartNumberResponse])
def get_all_part_numbers(
        db: Session = Depends(get_db)
):
    folders = db.query(PartNumber).all()

    # Convert datetime fields to ISO format strings
    for folder in folders:
        folder.created_at = folder.created_at.isoformat()
        folder.updated_at = folder.updated_at.isoformat()

    return folders
