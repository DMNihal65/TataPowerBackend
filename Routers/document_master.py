from datetime import datetime

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import shutil
from Database.db_setup import get_db
from orm_class.orm_models import Document, FolderMaster, PartNumber
from pydantic_schema.request_body import DocumentCreateRequest, PartNumberRequest
from pydantic_schema.respose_models import DocumentResponse

router = APIRouter(tags=['Document-Handles'])


@router.post("/upload-file/", response_model=List[DocumentResponse])
async def upload_file(
        folder_id: int,
        part_numbers: str,  # Expecting a comma-separated string of part numbers
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
):
    # Validate folder ID
    folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Create folder path
    base_path = "D:\\siri\\codes\\pycharm\\projects\\Tata\\main\\Folders"
    folder_path = os.path.join(base_path, build_full_path(folder_id, db))

    # Ensure folder exists
    os.makedirs(folder_path, exist_ok=True)

    # Save the uploaded file
    file_path = os.path.join(folder_path, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Split part numbers string into list
    part_number_list = [pn.strip() for pn in part_numbers.split(",")]

    # Prepare to collect document responses
    responses = []

    # Process each part number
    for part_number in part_number_list:
        db_part_number = db.query(PartNumber).filter(PartNumber.part_number == part_number).first()
        if db_part_number:
            # Existing part number
            part_number_id = db_part_number.id
        else:
            # New part number
            new_part_number = PartNumber(
                part_number=part_number,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(new_part_number)
            db.commit()
            db.refresh(new_part_number)
            part_number_id = new_part_number.id

        # Create a new Document for each part number
        new_document = Document(
            folder_id=folder_id,
            file_name=file.filename,
            file_path=file_path,
            version=1,
            validity_date=None,  # Set as needed
            status="uploaded",  # Set as needed
            part_number_id=part_number_id  # Ensure this field is correctly populated
        )

        db.add(new_document)
        db.commit()
        db.refresh(new_document)

        # Collect the response for each document
        responses.append(DocumentResponse(
            file_path=file_path,
            part_number_ids=[part_number_id],
            document_id=new_document.id,
            folder_id=folder_id,
            part_numbers=[part_number]
        ))

    # Return responses
    return responses


def build_full_path(folder_id: int, db: Session) -> str:
    # Recursively build the full path for the folder
    folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id).first()
    if folder is None:
        return ""
    parent_path = build_full_path(folder.parent_id, db) if folder.parent_id else ""
    return os.path.join(parent_path, folder.name)


@router.post("/get-files/")
def get_documents_by_part_numbers(request: PartNumberRequest, db: Session = Depends(get_db)):
    part_numbers = request.part_numbers

    # Query for all the specified part numbers
    parts = db.query(PartNumber).filter(PartNumber.part_number.in_(part_numbers)).all()

    if not parts:
        raise HTTPException(status_code=404, detail="No part numbers found")

    # Get all part IDs
    part_ids = [part.id for part in parts]

    # Get the documents associated with all the part_number_ids
    documents = db.query(Document, FolderMaster.name, PartNumber.part_number) \
        .join(FolderMaster, Document.folder_id == FolderMaster.id) \
        .join(PartNumber, Document.part_number_id == PartNumber.id) \
        .filter(Document.part_number_id.in_(part_ids)) \
        .all()

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found for these part numbers")

    # Prepare the response
    response = [
        {
            "folder_name": folder_name,
            "part_number": part_number,
            "file_name": document.file_name,
            "file_path": os.path.normpath(r"\SDC-2\Tata" + document.file_path.split("Tata")[1])
        }
        for document, folder_name, part_number in documents
    ]

    return response
