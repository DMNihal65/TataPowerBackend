from typing import List

from fastapi import APIRouter, Depends, status, HTTPException, Response, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from Auth.oauth2 import get_current_user
from Database.db_setup import get_db
from orm_class.orm_models import FolderMaster, User
from pydantic_schema.request_body import FolderCreateRequest, FolderUpdateRequest
from pydantic_schema.respose_models import FolderResponse

router = APIRouter(tags=['Folder-Handles'])


def require_role(required_role: str, current_user: User):
    if current_user.role != required_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/folders/", response_model=FolderCreateRequest)
def create_folder(
        folder: FolderCreateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    require_role("admin", current_user)  # Check if the user has admin scope

    db_folder = FolderMaster(
        name=folder.name,
        description=folder.description,
        requires_validity=folder.requires_validity,
        is_mandatory=folder.is_mandatory
    )

    try:
        db.add(db_folder)
        db.commit()
        db.refresh(db_folder)
        return db_folder
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Folder with this name already exists.")


@router.put("/foldersupdate/folder_name", response_model=FolderUpdateRequest)
def update_folder(
        folder_name: str,
        folder_update: FolderUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    require_role("admin", current_user)  # Check if the user has admin scope

    # Query folder by name
    db_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_name).first()

    if db_folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Update folder fields if they are provided in the request
    if folder_update.name is not None:
        db_folder.name = folder_update.name
    if folder_update.description is not None:
        db_folder.description = folder_update.description
    if folder_update.requires_validity is not None:
        db_folder.requires_validity = folder_update.requires_validity
    if folder_update.is_mandatory is not None:
        db_folder.is_mandatory = folder_update.is_mandatory

    try:
        db.commit()
        db.refresh(db_folder)
        return db_folder
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error updating folder. Possibly a duplicate name.")


@router.delete("/foldersdelete/folder_name", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
        folder_name: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    require_role("admin", current_user)  # Check if the user has admin scope

    # Query folder by name
    db_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_name).first()

    if db_folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    try:
        db.delete(db_folder)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error deleting folder.")


@router.get("/getallfolders/", response_model=List[FolderResponse])
def get_all_folders(
        db: Session = Depends(get_db)
):
    folders = db.query(FolderMaster).all()

    # Convert datetime fields to ISO format strings
    for folder in folders:
        folder.created_at = folder.created_at.isoformat()
        folder.updated_at = folder.updated_at.isoformat()

    return folders