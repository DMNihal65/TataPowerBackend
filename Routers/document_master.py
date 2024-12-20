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

from minio import Minio
from minio.error import S3Error

from io import BytesIO

import pyclamd


router = APIRouter(tags=['Document-Handles'])

MINIO_URL = "127.0.0.1:9000" 
MINIO_ACCESS_KEY = "minioadmin" 
MINIO_SECRET_KEY = "minioadmin"  
BUCKET_NAME = "tatapower"

minio_client = Minio(
    MINIO_URL,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False,  # Set to True if using HTTPS
)

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
    folder_path = build_full_path(folder_id, db)

    file_content = await file.read()  # Read the file content into memory
    file_size = len(file_content)  # Get the size of the file

    # Initialize ClamAV
    # try:
    #     clam = pyclamd.ClamdNetworkSocket(host='127.0.0.1', port=3310)
    #     if not clam.ping():
    #         raise HTTPException(status_code=500, detail="ClamAV service is not running.")
    # except pyclamd.ConnectionError:
    #     raise HTTPException(status_code=500, detail="Unable to connect to ClamAV.")

    # # Scan the file for viruses
    # scan_result = clam.scan_stream(file_content)

    # if scan_result:
    #     raise HTTPException(status_code=400, detail="The file is infected with a virus: " + str(scan_result))

    try:
        # Generate a unique file name (you can use timestamp or UUID to avoid conflicts)
        file_name = f"{folder_path}/{file.filename}".replace("\\", "/")

        # Upload the file to the MinIO bucket
        minio_client.put_object(
            BUCKET_NAME, 
            file_name, 
            BytesIO(file_content),  # Wrap the file content in a BytesIO stream
            file_size,  # Pass the length of the file
            content_type=file.content_type , # Pass the content type (MIME type)
            metadata={"x-amz-meta-partnumber": (part_numbers)}  # Add custom metadata for multiple part numbers
        )

        # Generate the URL to the uploaded file (in MinIO, this would be the access point to the file)
        file_url = f"http://{MINIO_URL}/{BUCKET_NAME}/{file_name}"
        
    except S3Error as e:
        raise HTTPException(status_code=500, detail="Error uploading file: " + str(e))

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
            file_path=file_url,
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
            file_path=file_url,
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
    
    response = {}

    for part_id in part_ids:
        documents = (
            db.query(Document)
            .filter(Document.part_number_id == part_id)
            .all()
        )

        if documents:
            # Add part_id as a key in the response and map its associated documents
            response[part_id] = [
                {"file_name": doc.file_name, "file_path": doc.file_path}
                for doc in documents
            ]

    if not response:
        raise HTTPException(status_code=404, detail="No documents found for these part numbers")

    return response
