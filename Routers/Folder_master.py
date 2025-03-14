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
from orm_class.orm_models import FolderMaster, PartNumber, User, Document
from pydantic_schema.request_body import FolderCreateRequest, FolderUpdateRequest
from pydantic_schema.respose_models import FolderResponse, FolderDetailResponse, FilePathResponse

from minio import Minio
from minio.error import S3Error
from minio.commonconfig import CopySource


import io


router = APIRouter(tags=['Folder-Handles'])

# def require_role(required_role: str, current_user: User):
#     if current_user.role != required_role:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

# MINIO_URL = "172.18.7.91:9000" 
MINIO_URL = "127.0.0.1:9000" 
# MINIO_URL = "minio:9000" 
# MINIO_URL = os.getenv("MINIO_URL", "minio:9000")
MINIO_ACCESS_KEY = "minioadmin" 
MINIO_SECRET_KEY = "minioadmin"  

minio_client = Minio(
    MINIO_URL,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False,  # Set to True if using HTTPS
)

# Add this function after the router definition and before the create_folder endpoint
def get_bucket_name(plant: str) -> str:
    """Map plant code to corresponding bucket name"""
    bucket_mapping = {
        "tps": "tatapower",
        "tprel": "tprel"
    }
    return bucket_mapping.get(plant, "tatapower")  # Default to tatapower if plant not found

@router.post("/folders/", response_model=FolderCreateRequest)
def create_folder(
        folder: FolderCreateRequest,
        db: Session = Depends(get_db),
):
    # Convert 0 to None for parent_id
    parent_id = folder.parent_id if folder.parent_id != 0 else None

    try:
        # Get the appropriate bucket name based on plant
        bucket_name = get_bucket_name(folder.plant)

        # Retrieve the parent folder from the database
        parent_folder = db.query(FolderMaster).filter(FolderMaster.id == parent_id).first()
        if parent_id and not parent_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found.")

        # Build the full path by traversing the hierarchy
        def build_full_path(folder_id: int, current_path: str) -> str:
            folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id).first()
            if folder is None:
                return current_path
            parent_path = build_full_path(folder.parent_id, current_path)
            return os.path.join(parent_path, folder.name)

        # Construct the folder path
        if parent_id:
            folder_path = build_full_path(parent_id, "").replace("\\", "/")
        else:
            folder_path = ""

        new_folder_path = os.path.join(folder_path, folder.name).replace("\\", "/")

        data = io.BytesIO(b"")  # Empty content, as you are creating an empty object for the folder

        # Ensure the bucket exists, create it if not
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        # Create a "folder" in MinIO (empty object with a trailing slash)
        minio_client.put_object(
            bucket_name,
            f"{new_folder_path}/",  # Nested folder path
            data, 
            length=0,
        )

        # Create the folder in the database
        db_folder = FolderMaster(
            name=folder.name,
            description=folder.description,
            parent_id=parent_id,
            plant = folder.plant
        )

        db.add(db_folder)
        db.commit()
        db.refresh(db_folder)

        return db_folder
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"MinIO error: {str(e)}")
    except IntegrityError as e:
        db.rollback()
        if "unique constraint" in str(e.orig):
            raise HTTPException(status_code=400, detail="Folder with this name already exists.")
        raise HTTPException(status_code=500, detail="An error occurred while creating the folder.")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="A database error occurred.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.delete("/folders/")
def delete_folder(
    folder_name: str,
    plant: str,
    parent_id: int = None,
    db: Session = Depends(get_db),
):
    try:
        # Get the appropriate bucket name based on plant
        bucket_name = get_bucket_name(plant)

        # Build the folder query
        folder_query = db.query(FolderMaster).filter(
            FolderMaster.name == folder_name,
            FolderMaster.plant == plant
        )
        
        # Add parent_id filter only if it's provided
        if parent_id is not None:
            folder_query = folder_query.filter(FolderMaster.parent_id == parent_id)
        
        folder = folder_query.first()

        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found.")

        def build_full_path(folder_id: int, plant: str, current_path: str = "") -> str:
            if folder_id is None:
                return current_path
            folder = db.query(FolderMaster).filter(
                FolderMaster.id == folder_id,
                FolderMaster.plant == plant
            ).first()
            if folder is None:
                return current_path
            parent_path = build_full_path(folder.parent_id, plant, current_path)
            return os.path.join(parent_path, folder.name)

        def delete_folder_recursively(folder_id: int, plant: str):
            folder_to_delete = db.query(FolderMaster).filter(
                FolderMaster.id == folder_id,
                FolderMaster.plant == plant
            ).first()
            
            if folder_to_delete:
                # Get the full path for MinIO operations
                folder_path = build_full_path(folder_to_delete.parent_id, plant).replace("\\", "/")
                folder_full_path = os.path.join(folder_path, folder_to_delete.name).replace("\\", "/")
                
                try:
                    # List all objects in this folder from MinIO
                    objects = minio_client.list_objects(bucket_name, prefix=f"{folder_full_path}/", recursive=True)
                    
                    # Delete all objects in the folder from MinIO
                    for obj in objects:
                        try:
                            minio_client.remove_object(bucket_name, obj.object_name)
                        except S3Error as e:
                            logging.error(f"Failed to delete object {obj.object_name}: {str(e)}")
                            raise

                    # Delete the folder object itself from MinIO
                    try:
                        minio_client.remove_object(bucket_name, f"{folder_full_path}/")
                    except S3Error as e:
                        if "NoSuchKey" not in str(e):  # Ignore if folder doesn't exist in MinIO
                            logging.error(f"Failed to delete folder {folder_full_path}/: {str(e)}")
                            raise
                except Exception as e:
                    logging.error(f"MinIO operation failed: {str(e)}")
                    raise

                # Delete any document   s in the database associated with this folder
                documents = db.query(Document).filter(
                    Document.folder_id == folder_to_delete.id,
                    Document.plant == folder_to_delete.plant
                ).all()
                for doc in documents:
                    db.delete(doc)

                # Delete all nested subfolders recursively
                subfolders = db.query(FolderMaster).filter(
                    FolderMaster.parent_id == folder_to_delete.id,
                    FolderMaster.plant == folder_to_delete.plant
                ).all()
                for subfolder in subfolders:
                    delete_folder_recursively(subfolder.id, subfolder.plant)

                # Finally delete the folder itself from the database
                db.delete(folder_to_delete)

        # Start the recursive deletion process
        delete_folder_recursively(folder.id, folder.plant)
        
        # Commit all database changes
        db.commit()

        return {"message": "Folder and all its contents deleted successfully"}

    except S3Error as e:
        db.rollback()
        logging.error(f"MinIO error during folder deletion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"MinIO error: {str(e)}")
    except SQLAlchemyError as e:
        db.rollback()
        logging.error(f"Database error during folder deletion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logging.error(f"Unexpected error during folder deletion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/getallfolders/", response_model=List[FolderResponse])
def get_all_folders(
        plant = str,
        db: Session = Depends(get_db)
):
    folders = db.query(FolderMaster).filter(FolderMaster.plant == plant).all()

    # Convert datetime fields to ISO format strings
    for folder in folders:
        folder.created_at = folder.created_at.isoformat()
        folder.updated_at = folder.updated_at.isoformat()

    return folders


@router.get("/getallfolderswithfiles/", response_model=List[FolderDetailResponse])
def get_all_folders_with_files(
        plant = str,
        db: Session = Depends(get_db)
):
    # Query all folders
    folders = db.query(FolderMaster).filter(FolderMaster.plant == plant).all()

    folder_details = []

    for folder in folders:
        # Get all documents for this folder
        documents = db.query(Document).filter(Document.folder_id == folder.id , Document.plant == folder.plant).all()

        file_details = {}
        for doc in documents:
            # Fetch all part numbers linked to the document
            part_numbers = db.query(PartNumber).filter(PartNumber.id == doc.part_number_id , PartNumber.plant == doc.plant).all()

            # Extract part number strings
            part_number_strings = [pn.part_number for pn in part_numbers]

            # Prepare file details with concatenated part numbers
            key = (doc.file_name, doc.file_path , doc.validity_date , doc.status)
            if key not in file_details:
                file_details[key] = set()

            # Add part numbers to the file's set
            file_details[key].update(part_number_strings)

        # Convert the file details to a list of FilePathResponse
        file_name_responses = [
            FilePathResponse(
                file_name=file_name,
                file_path=file_path,
                part_numbers=", ".join(sorted(part_number_list)),
                validity_date=validity_date.isoformat() if validity_date else "",
                status=status

            )
            for (file_name, file_path , validity_date , status), part_number_list in file_details.items()
        ]

        # Append folder details with file paths
        folder_details.append(FolderDetailResponse(
            id=folder.id,
            parent_id=folder.parent_id,
            name=folder.name,
            created_at=folder.created_at.isoformat(),
            updated_at=folder.updated_at.isoformat(),
            file_name=file_name_responses,
            plant=folder.plant
        ))

    return folder_details



@router.get("/getallfolderswithfilesapproved/", response_model=List[FolderDetailResponse])
def get_all_folders_with_files_approved(
        plant = str,
        db: Session = Depends(get_db)
):
    # Query all folders
    folders = db.query(FolderMaster).filter(FolderMaster.plant == plant).all()

    folder_details = []

    for folder in folders:
        # Get all documents for this folder
        documents = db.query(Document).filter(Document.folder_id == folder.id , Document.plant == folder.plant , Document.status == "approved").all()

        file_details = {}
        for doc in documents:
            # Fetch all part numbers linked to the document
            part_numbers = db.query(PartNumber).filter(PartNumber.id == doc.part_number_id , PartNumber.plant == doc.plant).all()

            # Extract part number strings
            part_number_strings = [pn.part_number for pn in part_numbers]

            # Prepare file details with concatenated part numbers
            key = (doc.file_name, doc.file_path , doc.validity_date , doc.status)
            if key not in file_details:
                file_details[key] = set()

            # Add part numbers to the file's set
            file_details[key].update(part_number_strings)

        # Convert the file details to a list of FilePathResponse
        file_name_responses = [
            FilePathResponse(
                file_name=file_name,
                file_path=file_path,
                part_numbers=", ".join(sorted(part_number_list)),
                validity_date=validity_date.isoformat() if validity_date else "",
                status= status

            )
            for (file_name, file_path , validity_date,status), part_number_list in file_details.items()
        ]

        # Append folder details with file paths
        folder_details.append(FolderDetailResponse(
            id=folder.id,
            parent_id=folder.parent_id,
            name=folder.name,
            created_at=folder.created_at.isoformat(),
            updated_at=folder.updated_at.isoformat(),
            file_name=file_name_responses,
            plant=folder.plant
        ))

    return folder_details



# @router.put("/folders/{folder_name}", response_model=FolderUpdateRequest)
# def update_folder(
#         folder_name: str,
#         folder_update: FolderUpdateRequest,
#         db: Session = Depends(get_db),
#         # current_user: User = Depends(get_current_user)
# ):
#     # require_role("admin", current_user)  # Check if the user has admin scope

#     # Query folder by old name
#     db_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_name).first()

#     if db_folder is None:
#         raise HTTPException(status_code=404, detail="Folder not found")

#     # Check if new name is provided and if it is different from the old name
#     if folder_update.name and folder_update.name != folder_name:
#         # Check for existing folder with the new name
#         existing_folder = db.query(FolderMaster).filter(FolderMaster.name == folder_update.name).first()
#         if existing_folder:
#             raise HTTPException(status_code=400, detail="A folder with this name already exists.")

#         # Determine the current folder path
#         def build_folder_path(folder: FolderMaster) -> str:
#             path = folder.name
#             while folder.parent_id:
#                 parent_folder = db.query(FolderMaster).filter(FolderMaster.id == folder.parent_id).first()
#                 if not parent_folder:
#                     break
#                 path = f"{parent_folder.name}/{path}"
#                 folder = parent_folder
#             return path

#         old_folder_path = build_folder_path(db_folder)
#         new_folder_path = old_folder_path.rsplit("/", 1)[0] + f"/{folder_update.name}"

#         # Log paths for debugging
#         print(f"Old folder path: {old_folder_path}")
#         print(f"New folder path: {new_folder_path}")

#         bucket_name = "tatapower"
#         folder_path = folder_name.strip("/")
#         new_folder_path = folder_update.name.strip("/")

#         try:
#             # List all objects in the old folder
#             objects_to_rename = minio_client.list_objects(bucket_name, prefix=f"{old_folder_path}/", recursive=True)

#             for obj in objects_to_rename:
#                 # Construct the new object name
#                 if obj.object_name.startswith(f"{old_folder_path}/"):
#                     new_object_name = obj.object_name.replace(f"{old_folder_path}/", f"{new_folder_path}/", 1)
#                 else:
#                     continue

#                 print(f"Renaming object: {obj.object_name} -> {new_object_name}")

#                 # Copy the object to the new path
#                 minio_client.copy_object(
#                     bucket_name=bucket_name,
#                     object_name=new_object_name,
#                     source=CopySource(bucket_name, obj.object_name)
#                 )

#                 # Delete the old object
#                 # minio_client.remove_object(bucket_name, obj.object_name)

#                     # Update folder name in the database
#             db_folder.name = folder_update.name

#         except S3Error as e:
#             raise HTTPException(status_code=500, detail=f"MinIO error during folder renaming: {str(e)}")

#     # Update other folder fields
#     if folder_update.description is not None:
#         db_folder.description = folder_update.description

#     if folder_update.requires_validity is not None:
#         db_folder.requires_validity = folder_update.requires_validity

#     if folder_update.is_mandatory is not None:
#         db_folder.is_mandatory = folder_update.is_mandatory

#     try:
#         db.commit()
#         db.refresh(db_folder)
#         return db_folder
#     except IntegrityError as e:
#         db.rollback()
#         # Specific handling for unique constraint violation
#         if "unique constraint" in str(e.orig):
#             raise HTTPException(status_code=400, detail="Error updating folder. Possibly a duplicate name.")
#         raise HTTPException(status_code=500, detail="An error occurred while updating the folder.")
#     except SQLAlchemyError as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail="A database error occurred.")
#     except Exception as e:
#         db.rollback()
#         # Optional: log the error e for debugging
#         raise HTTPException(status_code=500, detail="An unexpected error occurred.")


