from typing import List
from datetime import datetime
from pydantic import BaseModel

from fastapi import APIRouter, Depends, status, HTTPException, Response, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from Auth.oauth2 import get_current_user
from Database.db_setup import get_db
from orm_class.orm_models import FolderMaster, User, PartNumber
from pydantic_schema.request_body import FolderCreateRequest, FolderUpdateRequest, PartNumberCreate, PartNumberUpdate
from pydantic_schema.respose_models import FolderResponse, PartNumberResponse

router = APIRouter(tags=['PartNumber-Handles'])

# Add new Pydantic models for bulk upload
class PartNumberExcel(BaseModel):
    part_number: str
    description: str
    is_active: bool = True

class BulkPartNumberCreate(BaseModel):
    part_numbers: List[PartNumberExcel]
    plant: str


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
        inactive_date=inactive_date,
        plant=part_number.plant
    )

    # Check if it should be inactive based on the inactive date
    if inactive_date:
        current_date = datetime.now().date()
        if current_date > inactive_date.date():
            db_part_number.is_active = False

    db.add(db_part_number)
    db.commit()
    db.refresh(db_part_number)
    return db_part_number


@router.put("/updatepartnumbers/part_number", response_model=PartNumberResponse)
def update_part_number(
        part_number: str,
        plant: str,
        part_number_update: PartNumberUpdate,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user),
):
    # require_role("admin", current_user)  # Check if the user has admin scope
    # Fetch the existing record
    db_part_number = db.query(PartNumber).filter(PartNumber.part_number == part_number , PartNumber.plant == plant).first()

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
        new_inactive_date = part_number_update.convert_inactive_date()
        db_part_number.inactive_date = new_inactive_date
        # Check if it should be inactive based on the new inactive date
        current_date = datetime.now().date()
        if current_date > new_inactive_date.date():
            db_part_number.is_active = False
    

    db.commit()
    db.refresh(db_part_number)
    return db_part_number


@router.delete("/deletepartnumbers/part_number", status_code=status.HTTP_204_NO_CONTENT)
def delete_part_number(
        part_number: str,
        plant: str,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user)
):
    # require_role("admin", current_user)  # Check if the user has admin scope

    # Query folder by name
    db_folder = db.query(PartNumber).filter(PartNumber.part_number == part_number , PartNumber.plant == plant).first()

    if db_folder is None:
        raise HTTPException(status_code=404, detail="PartNumber not found")

    try:
        db.delete(db_folder)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error deleting folder.")


def update_active_status(db: Session, part_number: PartNumber) -> bool:
    """Update is_active status based on inactive_date"""
    if part_number.inactive_date:
        current_date = datetime.now().date()
        if current_date > part_number.inactive_date.date():
            if part_number.is_active:  # Only update if it's currently active
                part_number.is_active = False
                return True
    return False


def bulk_update_active_status(db: Session):
    """Update is_active status for all part numbers"""
    part_numbers = db.query(PartNumber).all()
    updates_made = False
    
    for part_number in part_numbers:
        if update_active_status(db, part_number):
            updates_made = True
    
    if updates_made:
        db.commit()


@router.get("/getallpartnumbers/", response_model=List[PartNumberResponse])
def get_all_part_numbers(
        plant: str,
        db: Session = Depends(get_db)
):
    # First update active status for all part numbers
    bulk_update_active_status(db)
    
    # Then fetch all part numbers
    part_numbers = db.query(PartNumber).filter(PartNumber.plant == plant).all()

    # Convert datetime fields to ISO format strings
    for part in part_numbers:
        part.created_at = part.created_at.isoformat()
        part.updated_at = part.updated_at.isoformat()
        if part.inactive_date:
            part.inactive_date = part.inactive_date.isoformat()

    return part_numbers


@router.get("/getallpartnumberswithoutplant/", response_model=List[PartNumberResponse])
def get_all_part_numbers(
        db: Session = Depends(get_db)
):
    # First update active status for all part numbers
    bulk_update_active_status(db)
    
    # Then fetch all part numbers
    part_numbers = db.query(PartNumber).all()

    # Convert datetime fields to ISO format strings
    for part in part_numbers:
        part.created_at = part.created_at.isoformat()
        part.updated_at = part.updated_at.isoformat()
        if part.inactive_date:
            part.inactive_date = part.inactive_date.isoformat()

    return part_numbers



@router.post("/bulk-create-partnumbers/", response_model=List[PartNumberResponse])
def create_bulk_part_numbers(
    request: BulkPartNumberCreate,
    db: Session = Depends(get_db),
):
    """Create multiple part numbers from Excel upload"""
    created_part_numbers = []
    skipped_part_numbers = []
    errors = []

    for part_data in request.part_numbers:
        try:
            # Check if part number already exists for this plant
            existing = db.query(PartNumber).filter(
                PartNumber.part_number == part_data.part_number,
                PartNumber.plant == request.plant
            ).first()

            if existing:
                skipped_part_numbers.append(part_data.part_number)
                continue  # Skip existing part numbers

            # Create new part number
            db_part_number = PartNumber(
                part_number=part_data.part_number,
                description=part_data.description,
                is_active=part_data.is_active,
                plant=request.plant
            )

            db.add(db_part_number)
            created_part_numbers.append(db_part_number)

        except Exception as e:
            errors.append(f"Error creating part number {part_data.part_number}: {str(e)}")

    # Commit successful inserts
    try:
        db.commit()
        for part_number in created_part_numbers:
            db.refresh(part_number)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error committing transaction: {str(e)}"
        )

    return created_part_numbers


# @router.post("/bulk-create-partnumbers/", response_model=List[PartNumberResponse])
# def create_bulk_part_numbers(
#     request: BulkPartNumberCreate,
#     db: Session = Depends(get_db),
# ):
#     """Create multiple part numbers from Excel upload"""
#     created_part_numbers = []
#     errors = []

#     for part_data in request.part_numbers:
#         try:
#             # Check if part number already exists for this plant
#             existing = db.query(PartNumber).filter(
#                 PartNumber.part_number == part_data.part_number,
#                 PartNumber.plant == request.plant
#             ).first()

#             if existing:
#                 errors.append(f"Part number {part_data.part_number} already exists for plant {request.plant}")
#                 continue

#             # Create new part number
#             db_part_number = PartNumber(
#                 part_number=part_data.part_number,
#                 description=part_data.description,
#                 is_active=part_data.is_active,
#                 plant=request.plant
#             )

#             db.add(db_part_number)
#             created_part_numbers.append(db_part_number)

#         except Exception as e:
#             errors.append(f"Error creating part number {part_data.part_number}: {str(e)}")

#     if errors:
#         # If there were any errors, rollback and return the error messages
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail={"message": "Some part numbers could not be created", "errors": errors}
#         )

#     # If all successful, commit the transaction
#     try:
#         db.commit()
#         for part_number in created_part_numbers:
#             db.refresh(part_number)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error committing transaction: {str(e)}"
#         )

#     return created_part_numbers
