import logging
import os
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, status, HTTPException, Response, Query
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from Auth.oauth2 import get_current_user
from Database.db_setup import get_db
from orm_class.orm_models import FolderMaster, User, Document
from pydantic_schema.request_body import FolderCreateRequest, FolderUpdateRequest
from pydantic_schema.respose_models import FolderResponse, FolderDetailResponse, FilePathResponse

router = APIRouter(tags=['Folder-Handles'])


# def require_role(required_role: str, current_user: User):
#     if current_user.role != required_role:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/folders/", response_model=FolderCreateRequest)
def create_folder(
        folder: FolderCreateRequest,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user)
):
    # require_role("admin", current_user)  # Check if the user has admin scope

    # Convert 0 to None for parent_id
    parent_id = folder.parent_id if folder.parent_id != 0 else None

    try:
        # Retrieve the parent folder from the database
        parent_folder = db.query(FolderMaster).filter(FolderMaster.id == parent_id).first()
        if parent_id and not parent_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found.")

        # Determine the path where the new folder will be created
        base_path = "D:\\siri\\codes\\pycharm\\projects\\Tata\\main\\Folders"

        # Build the full path by traversing up the hierarchy
        def build_full_path(folder_id: int, current_path: str) -> str:
            folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id).first()
            if folder is None:
                return current_path
            parent_path = build_full_path(folder.parent_id, current_path)
            return os.path.join(parent_path, folder.name)

        # Determine the full path for the new folder
        if parent_id:
            folder_path = build_full_path(parent_id, base_path)
        else:
            folder_path = base_path

        # Create the new folder on the filesystem
        new_folder_path = os.path.join(folder_path, folder.name)
        os.makedirs(new_folder_path, exist_ok=True)

        # Create the folder in the database
        db_folder = FolderMaster(
            name=folder.name,
            description=folder.description,
            requires_validity=folder.requires_validity,
            is_mandatory=folder.is_mandatory,
            parent_id=parent_id
        )

        db.add(db_folder)
        db.commit()
        db.refresh(db_folder)

        return db_folder
    except IntegrityError as e:
        db.rollback()
        # Specific handling for unique constraint violation
        if "unique constraint" in str(e.orig):
            raise HTTPException(status_code=400, detail="Folder with this name already exists.")
        raise HTTPException(status_code=500, detail="An error occurred while creating the folder.")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="A database error occurred.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.put("/folders/{folder_name}", response_model=FolderUpdateRequest)
def update_folder(
        folder_name: str,
        folder_update: FolderUpdateRequest,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user)
):
    # require_role("admin", current_user)  # Check if the user has admin scope

    # Query folder by old name
    db_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_name).first()

    if db_folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Check if new name is provided and if it is different from the old name
    if folder_update.name and folder_update.name != folder_name:
        # Check for existing folder with the new name
        existing_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_update.name).first()
        if existing_folder:
            raise HTTPException(status_code=400, detail="A folder with this name already exists.")

        # Determine the old folder path
        base_path = Path("D:/siri/codes/pycharm/projects/Tata/main/Folders")

        # Find the full path for the current folder
        def find_full_path(folder_id: int, current_path: Path) -> Path:
            folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id).first()
            if folder is None:
                return current_path
            parent_path = find_full_path(folder.parent_id, current_path)
            return parent_path / folder.name

        folder_path = find_full_path(db_folder.id, base_path)

        # Log the paths for debugging
        print(f"Current folder path: {folder_path}")
        new_folder_path = folder_path.parent / folder_update.name
        print(f"New folder path: {new_folder_path}")

        # Check if the folder exists before renaming
        if not folder_path.exists():
            raise HTTPException(status_code=404, detail="The folder to rename does not exist.")

        # Rename the folder on the filesystem
        try:
            os.rename(folder_path, new_folder_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Error renaming folder: {str(e)}")

        # Update folder name in the database
        db_folder.name = folder_update.name

    # Update other folder fields
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
    except IntegrityError as e:
        db.rollback()
        # Specific handling for unique constraint violation
        if "unique constraint" in str(e.orig):
            raise HTTPException(status_code=400, detail="Error updating folder. Possibly a duplicate name.")
        raise HTTPException(status_code=500, detail="An error occurred while updating the folder.")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="A database error occurred.")
    except Exception as e:
        db.rollback()
        # Optional: log the error e for debugging
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.delete("/foldersdelete/{folder_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
        folder_name: str,
        db: Session = Depends(get_db),
        # current_user: User = Depends(get_current_user)
):
    # require_role("admin", current_user)  # Check if the user has admin scope

    # Query folder by name
    db_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_name).first()

    if db_folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Determine the path of the folder to be deleted
    base_path = "D:\\siri\\codes\\pycharm\\projects\\Tata\\main\\Folders"
    folder_path = os.path.join(base_path, folder_name)
    logging.debug(f"Attempting to delete folder at path: {folder_path}")

    try:
        # Delete the folder from the database
        db.delete(db_folder)
        db.commit()

        # Delete the folder from the filesystem
        if os.path.exists(folder_path):
            logging.debug(f"Deleting folder and contents at path: {folder_path}")
            shutil.rmtree(folder_path, ignore_errors=False,
                          onerror=None)  # Recursively delete the folder and its contents

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error deleting folder. Possibly due to foreign key constraints.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="A database error occurred.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

    return None


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


@router.get("/getallfolderswithfiles/", response_model=List[FolderDetailResponse])
def get_all_folders_with_files(
        db: Session = Depends(get_db)
):
    # Query all folders
    folders = db.query(FolderMaster).all()

    folder_details = []

    for folder in folders:
        # Get all documents for this folder
        documents = db.query(Document).filter(Document.folder_id == folder.id).all()

        # Extract file paths
        file_paths = [FilePathResponse(file_path=doc.file_path) for doc in documents]

        # Append folder details with file paths
        folder_details.append(FolderDetailResponse(
            id=folder.id,
            name=folder.name,
            created_at=folder.created_at.isoformat(),
            updated_at=folder.updated_at.isoformat(),
            file_paths=file_paths
        ))

    return folder_details