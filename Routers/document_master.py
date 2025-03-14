from datetime import datetime

from fastapi import APIRouter, FastAPI, File, UploadFile, Form, HTTPException, Depends, Query , BackgroundTasks
from sqlalchemy import extract
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import shutil
from Database.db_setup import get_db
from orm_class.orm_models import Document, DocumentApproval, FolderMaster, PartNumber
from pydantic_schema.request_body import DocumentCreateRequest, PartNumberRequest, UpdateValidityRequest
from pydantic_schema.respose_models import DocumentResponse, DocumentStatusRequest
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


from minio import Minio
from minio.error import S3Error

from io import BytesIO

from fastapi import BackgroundTasks
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib


# import pyclamd

import logging

scheduler = AsyncIOScheduler()



router = APIRouter(tags=['Document-Handles'])

# MINIO_URL = "172.18.7.91:9000" 
MINIO_URL = "127.0.0.1:9000" 
# MINIO_URL = "minio:9000"
# MINIO_URL = os.getenv("MINIO_URL", "minio:9000")
MINIO_ACCESS_KEY = "minioadmin" 
MINIO_SECRET_KEY = "minioadmin"  

def get_bucket_name(plant: str) -> str:
    """Map plant code to corresponding bucket name"""
    bucket_mapping = {
        "tps": "tatapower",
        "tprel": "tprel"
    }
    return bucket_mapping.get(plant, "tatapower")  # Default to tatapower if plant not found

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MinIO client with proper error handling
try:
    minio_client = Minio(
        MINIO_URL,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
except Exception as e:
    logger.error(f"Error initializing MinIO client: {str(e)}")
    raise


def send_email_notification(supervisor_email: str, file_name: str, file_url: str):
    # Use Gmail SMTP or your organization's SMTP server
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = "shashankshashank84375@gmail.com"
    APP_PASSWORD = "tgpo tpxs uvpq etjs"
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = supervisor_email
        msg["Subject"] = "New File Upload Notification"
        
        body = f"""
        Dear Supervisor,

        A new file has been uploaded:
        File Name: {file_name}
        Download Link: {file_url}

        Please review it at your earliest convenience.

        Best regards,
        Document Management System
        """
        
        msg.attach(MIMEText(body, "plain"))
        server.send_message(msg)
        server.quit()
        logger.info(f"Email notification sent successfully to {supervisor_email}")
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")


@router.post("/upload-file/", response_model=List[DocumentResponse])
async def upload_file(
    background_tasks: BackgroundTasks,
    folder_id: int,
    plant: str,
    files: List[UploadFile] = File(...),
    validity_date: str = Query(..., description="Comma-separated list of validity dates, one for each file"),
    file_name: str = Query(..., description="Comma-separated list of file names, one for each file"),
    part_numbers: Optional[str] = None,
    db: Session = Depends(get_db),
):  
    supervisor_email = "shashankshashank2727@gmail.com"  # Fetch from database if dynamic

    logger.info(f"Starting upload process for folder_id: {folder_id}, part_numbers: {part_numbers}")
    
    # Get the appropriate bucket name based on plant
    bucket_name = get_bucket_name(plant)
    
    # Validate folder ID
    folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id, FolderMaster.plant == plant).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Create folder path
    folder_path = build_full_path(folder_id, plant, db)
    logger.info(f"Built folder path: {folder_path}")
    
    # Process part numbers if provided, else set to None
    part_number_list = [pn.strip() for pn in part_numbers.split(",")] if part_numbers else [None]
    
    # Process validity dates and file names
    validity_date_list = [date.strip() for date in validity_date.split(",")]
    file_name_list = [name.strip() for name in file_name.split(",")]
    
    # Validate number of validity dates and file names matches number of files
    if len(validity_date_list) != len(files) or len(file_name_list) != len(files):
        raise HTTPException(
            status_code=400,
            detail=f"Number of validity dates ({len(validity_date_list)}) and file names ({len(file_name_list)}) must match number of files ({len(files)})"
        )
    
    responses = []
    
    # Process each uploaded file with its corresponding validity date and file name
    for file, validity_date, file_name in zip(files, validity_date_list, file_name_list):
        try:
            logger.info(f"Processing file: {file.filename} with validity date: {validity_date} and file name: {file_name}")
            
            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            logger.info(f"File size: {file_size} bytes")

            # Generate unique file name with sanitized path
            safe_filename = file_name
            file_path = f"{folder_path}/{safe_filename}".replace("\\", "/")
            logger.info(f"Generated file path: {file_path}")

            try:
                # Ensure bucket exists
                if not minio_client.bucket_exists(bucket_name):
                    minio_client.make_bucket(bucket_name)
                    logger.info(f"Created bucket: {bucket_name}")

                # Upload to MinIO
                logger.info("Attempting MinIO upload...")
                minio_client.put_object(
                    bucket_name=bucket_name,
                    object_name=file_path,
                    data=BytesIO(file_content),
                    length=file_size,
                    content_type=file.content_type or 'application/octet-stream'
                )
                logger.info("MinIO upload successful")

                # Generate file URL
                file_url = f"http://{MINIO_URL}/{bucket_name}/{file_path}"
                logger.info(f"Generated file URL: {file_url}")

                # Process each part number for this file
                file_responses = []
                for part_number in part_number_list:
                    logger.info(f"Processing part number: {part_number}")
                    
                    db_part_number = None
                    if part_number:
                        # Get or create part number
                        db_part_number = db.query(PartNumber).filter(
                            PartNumber.part_number == part_number, PartNumber.plant == plant
                        ).first()
                        
                        if not db_part_number:
                            logger.info(f"Creating new part number: {part_number}")
                            db_part_number = PartNumber(
                                part_number=part_number,
                                is_active=True,
                                created_at=datetime.now(),
                                updated_at=datetime.now(),
                                plant=plant
                            )
                            db.add(db_part_number)
                            db.commit()
                            db.refresh(db_part_number)

                    # Create document record
                    logger.info("Creating document record")
                    new_document = Document(
                        folder_id=folder_id,
                        file_name=safe_filename,
                        file_path=file_url,
                        version=1,
                        validity_date=validity_date,
                        status="uploaded",
                        part_number_id=db_part_number.id if db_part_number else None,
                        plant=plant
                    )

                    db.add(new_document)
                    db.commit()
                    db.refresh(new_document)

                    file_responses.append(DocumentResponse(
                        file_path=file_url,
                        part_number_ids=[db_part_number.id] if db_part_number else [],
                        document_id=new_document.id,
                        folder_id=folder_id,
                        part_numbers=[part_number] if part_number else [],
                        plant=plant,
                        validity_date=validity_date
                    ))

                    background_tasks.add_task(send_email_notification, supervisor_email, file_name, file_url)

                responses.extend(file_responses)
                logger.info(f"Successfully processed file: {file_name}")

            except S3Error as e:
                logger.error(f"MinIO error for file {file_name}: {str(e)}")
                continue

        except Exception as e:
            logger.error(f"Error processing file {file_name}: {str(e)}")
            logger.exception("Full traceback:")
            continue

        finally:
            await file.seek(0)

    if not responses:
        logger.error("No files were successfully processed")
        raise HTTPException(
            status_code=500,
            detail="Failed to process any of the uploaded files. Check server logs for details."
        )

    logger.info(f"Successfully processed {len(responses)} files")
    return responses

def build_full_path(folder_id: int, plant: str, db: Session) -> str:
    # Recursively build the full path for the folder
    folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id , FolderMaster.plant == plant).first()
    if folder is None:
        return ""
    parent_path = build_full_path(folder.parent_id, folder.plant , db) if folder.parent_id else ""
    return os.path.join(parent_path, folder.name)


@router.post("/get-files/")
def get_documents_by_part_numbers(
    request: PartNumberRequest, 
    plant: str, 
    db: Session = Depends(get_db)
):
    part_numbers = request.part_numbers

    # Query for all the specified part numbers
    parts = (
        db.query(PartNumber)
        .filter(PartNumber.part_number.in_(part_numbers), PartNumber.plant == plant)
        .all()
    )

    if not parts:
        raise HTTPException(status_code=404, detail="No part numbers found")

    response = {}

    for part in parts:
        documents = (
            db.query(Document)
            .filter(
                Document.part_number_id == part.id,
                Document.plant == plant,
                Document.status == "approved"
            )
            .all()
        )

        if documents:
            response[part.part_number] = [
                {"file_name": doc.file_name, "file_path": doc.file_path}
                for doc in documents
            ]

    if not response:
        raise HTTPException(status_code=404, detail="No documents found for these part numbers")

    return response


@router.post("/get-fileswithoutplant/")
def get_documents_by_part_numbers(
    request: PartNumberRequest, 
    db: Session = Depends(get_db)
):
    part_numbers = request.part_numbers

    # Query for all the specified part numbers
    parts = (
        db.query(PartNumber)
        .filter(PartNumber.part_number.in_(part_numbers))
        .all()
    )

    if not parts:
        raise HTTPException(status_code=404, detail="No part numbers found")

    response = {}

    for part in parts:
        documents = (
            db.query(Document)
            .filter(
                Document.part_number_id == part.id,
                Document.status == "approved"
            )
            .all()
        )

        if documents:
            response[part.part_number] = [
                {"file_name": doc.file_name, "file_path": doc.file_path}
                for doc in documents
            ]

    if not response:
        raise HTTPException(status_code=404, detail="No documents found for these part numbers")

    return response

@router.get("/documents")
def get_documents(plant:str , db: Session = Depends(get_db)):
    # Fetch documents
    docs = db.query(Document).filter(Document.plant == plant).all()
    
    # Fetch part numbers
    part_numbers = db.query(PartNumber).filter(PartNumber.plant == plant).all()
    
    # Create a mapping of part_number_id to actual part_number
    part_number_map = {part.id: part.part_number for part in part_numbers}
    
    # Add part_number to each document
    result = []
    for doc in docs:
        result.append({
            "id": doc.id,
            "version": doc.version,
            "status": doc.status,
            "updated_at": doc.updated_at,
            "part_number_id": doc.part_number_id,
            "folder_id": doc.folder_id,
            "file_name": doc.file_name,
            "file_path": doc.file_path,
            "validity_date": doc.validity_date,
            "created_at": doc.created_at,
            "part_number": part_number_map.get(doc.part_number_id),  # Map part_number
            "plant": doc.plant
        })
    
    return result




@router.put("/documents")
def update_document_status(plant: str ,request: DocumentStatusRequest, db: Session = Depends(get_db)):
    # Validate the status
    if request.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'approved' or 'rejected'.")

    # Fetch the document from the database
    document = db.query(Document).filter(Document.id == request.document_id , Document.plant == plant).first()
    
    # Check if the document exists
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    # Update the status
    document.status = request.status
    db.commit()
    db.refresh(document)

    # Insert data into document_approval table
    document_approval_entry = DocumentApproval(
        document_id=document.id,
        status=request.status,
        approval_date=document.updated_at
    )
    db.add(document_approval_entry)
    db.commit()

    return {"message": "Document status updated successfully.", "document": {
        "id": document.id,
        "status": document.status,
        "updated_at": document.updated_at
    }}

@router.get("/get_dashboard")
def get_dashboard(plant:str, db: Session = Depends(get_db)):
    total_documents = db.query(Document).filter(Document.plant == plant).count()
    uploaded_documents_count = db.query(Document).filter(Document.plant == plant ,Document.status == "uploaded").count()

    current_month = datetime.now().month
    current_year = datetime.now().year

    approved_this_month = db.query(Document).filter(
        Document.plant == plant ,
        extract('month', Document.updated_at) == current_month,
        extract('year', Document.updated_at) == current_year
    ).count()
    return {"total_documents": total_documents , "pending_approval" : uploaded_documents_count , "approved_this_month": approved_this_month}

@router.post("/associate-existing-files/")
async def associate_existing_files(
    request: dict,
    db: Session = Depends(get_db)
):
    supervisor_email = "shashankshashank2727@gmail.com"  # Fetch from database if dynamic
    
    try:
        folder_id = request.get('folder_id')
        part_numbers = request.get('part_numbers', '').split(',') if request.get('part_numbers') else []
        files = request.get('files', [])
        plant = request.get('plant')
        validity_date = request.get('validity_date')

        # Validate folder exists
        folder = db.query(FolderMaster).filter(FolderMaster.id == folder_id, FolderMaster.plant == plant).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Process each file
        for file in files:
            # Create document record without part number if no part numbers provided
            if not part_numbers or all(not pn.strip() for pn in part_numbers):
                new_document = Document(
                    file_name=file['file_name'],
                    file_path=file['file_path'],
                    folder_id=folder_id,
                    part_number_id=None,  # No part number
                    status="uploaded",
                    version=1,
                    validity_date=datetime.strptime(validity_date, '%Y-%m-%d'),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    plant=plant
                )
                db.add(new_document)
            else:
                # Process each part number for the file
                for part_number in part_numbers:
                    part_number = part_number.strip()
                    if not part_number:
                        continue

                    # Get or create part number
                    db_part_number = db.query(PartNumber).filter(
                        PartNumber.part_number == part_number, 
                        PartNumber.plant == plant
                    ).first()

                    if not db_part_number:
                        db_part_number = PartNumber(
                            part_number=part_number,
                            is_active=True,
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                            plant=plant
                        )
                        db.add(db_part_number)
                        db.commit()
                        db.refresh(db_part_number)

                    # Create document record with part number
                    new_document = Document(
                        file_name=file['file_name'],
                        file_path=file['file_path'],
                        folder_id=folder_id,
                        part_number_id=db_part_number.id,
                        status="uploaded",
                        version=1,
                        validity_date=datetime.strptime(validity_date, '%Y-%m-%d'),
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                        plant=plant
                    )
                    db.add(new_document)

        db.commit()
        return {"message": "Files associated successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error in associate_existing_files: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/expiring-documents")
def get_expiring_documents(plant: str , db: Session = Depends(get_db)):
    # Fetch documents with their part numbers
    docs = db.query(Document).filter(Document.plant == plant).all()
    part_numbers = db.query(PartNumber).filter(PartNumber.plant == plant).all()
    
    # Create a mapping of part_number_id to part number info
    part_number_map = {
        part.id: {
            "part_number": part.part_number,
        } for part in part_numbers
    }
    
    # Add part_number and inactive_date to each document
    result = []
    for doc in docs:
        part_info = part_number_map.get(doc.part_number_id, {})
        result.append({
            "id": doc.id,
            "version": doc.version,
            "status": doc.status,
            "updated_at": doc.updated_at,
            "part_number_id": doc.part_number_id,
            "folder_id": doc.folder_id,
            "file_name": doc.file_name,
            "file_path": doc.file_path,
            "validity_date": doc.validity_date,
            "created_at": doc.created_at,
            "part_number": part_info.get("part_number"),
            "inactive_date": doc.validity_date.isoformat() if doc.validity_date else None,
            "plant" : doc.plant
        })
    
    return result


def send_expiration_notification(document_info: dict):
    """Send email notification about document expiration"""
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = "shashankshashank84375@gmail.com"
    APP_PASSWORD = "tgpo tpxs uvpq etjs"
    RECIPIENT_EMAIL = "shashankshashank2727@gmail.com"
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECIPIENT_EMAIL
        
        if document_info["days_remaining"] > 0:
            msg["Subject"] = f"Document Expiring Soon: {document_info['file_name']}"
            body = f"""
            Dear User,

            The following document will expire in {document_info['days_remaining']} days:
            
            File Name: {document_info['file_name']}
            Part Number: {document_info['part_number'] or 'N/A'}
            Expiration Date: {document_info['expiry_date']}
            Document Link: {document_info['file_path']}

            Please take necessary action before the document expires.

            Best regards,
            Document Management System
            """
        else:
            msg["Subject"] = f"Document Expired: {document_info['file_name']}"
            body = f"""
            Dear User,

            The following document has expired:
            
            File Name: {document_info['file_name']}
            Part Number: {document_info['part_number'] or 'N/A'}
            Expiration Date: {document_info['expiry_date']}
            Document Link: {document_info['file_path']}

            Please update the document as soon as possible.

            Best regards,
            Document Management System
            """
        
        msg.attach(MIMEText(body, "plain"))
        server.send_message(msg)
        server.quit()
        logger.info(f"Expiration notification sent for document: {document_info['file_name']}")
        
    except Exception as e:
        logger.error(f"Failed to send expiration notification: {str(e)}")



async def check_expiring_documents_scheduled(plant: str, db: Session):
    """
    Scheduled task to check for expiring documents and send notifications
    """
    try:
        current_date = datetime.now().date()
        
        # Fetch all documents with their part numbers
        query = (
            db.query(Document, PartNumber)
            .outerjoin(PartNumber, Document.part_number_id == PartNumber.id)
            .filter(Document.plant == plant)
            .filter(Document.validity_date.isnot(None))
        )
        
        documents = query.all()
        notifications_sent = 0
        
        for doc, part in documents:
            if doc.validity_date:
                days_remaining = (doc.validity_date.date() - current_date).days
                
                # Check if document is expiring in 15 days or has expired
                if days_remaining <= 15 or days_remaining < 0:
                    document_info = {
                        "file_name": doc.file_name,
                        "part_number": part.part_number if part else None,
                        "expiry_date": doc.validity_date.strftime("%Y-%m-%d"),
                        "days_remaining": days_remaining,
                        "file_path": doc.file_path
                    }
                    
                    await send_expiration_notification(document_info)
                    notifications_sent += 1
        
        logger.info(f"Scheduled check completed. {notifications_sent} notification(s) sent.")
        
    except Exception as e:
        logger.error(f"Error in scheduled check_expiring_documents: {str(e)}")


def setup_scheduler(app: FastAPI, db: Session):
    """
    Set up the scheduler to run the document check daily for each plant
    """
    async def check_all_plants():
        # Get list of all plants from your configuration or database
        plants = ["tps", "tprel"]  # Replace with your plant list
        for plant in plants:
            await check_expiring_documents_scheduled(plant, db)

    # Schedule the task to run daily at 9:00 AM
    scheduler.add_job(
        check_all_plants,
        trigger=CronTrigger(hour=9, minute=0),
        id="document_check",
        name="Check expiring documents",
        replace_existing=True
    )

    # Start the scheduler when the application starts
    @app.on_event("startup")
    async def start_scheduler():
        scheduler.start()

    # Shut down the scheduler when the application stops
    @app.on_event("shutdown")
    async def shutdown_scheduler():
        scheduler.shutdown()




@router.put("/update-documents-validity/")
async def update_documents_validity(
    request: UpdateValidityRequest,
    db: Session = Depends(get_db)
):
    try:
        # Convert validity_date string to datetime
        new_validity_date = datetime.strptime(request.validity_date, "%Y-%m-%d")
        
        # Get part number IDs
        part_number_records = db.query(PartNumber).filter(
            PartNumber.part_number.in_(request.part_numbers),
            PartNumber.plant == request.plant
        ).all()
        
        if not part_number_records:
            raise HTTPException(status_code=404, detail="No matching part numbers found")
            
        part_number_ids = [record.id for record in part_number_records]
        
        # Update documents matching the file name and part numbers
        updated_docs = db.query(Document).filter(
            Document.file_name == request.file_name,
            Document.part_number_id.in_(part_number_ids),
            Document.plant == request.plant
        ).all()
        
        if not updated_docs:
            raise HTTPException(
                status_code=404, 
                detail="No documents found with the specified file name and part numbers"
            )
        
        # Update validity date for all matching documents
        for doc in updated_docs:
            doc.validity_date = new_validity_date
        
        # Commit changes
        db.commit()
        
        return {
            "message": f"Successfully updated validity date for {len(updated_docs)} documents",
            "updated_documents": [
                {
                    "id": doc.id,
                    "file_name": doc.file_name,
                    "part_number_id": doc.part_number_id,
                    "new_validity_date": doc.validity_date.strftime("%Y-%m-%d")
                }
                for doc in updated_docs
            ]
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/check-expiring-documents")
# async def check_expiring_documents(
#     background_tasks: BackgroundTasks,
#     plant: str,
#     db: Session = Depends(get_db)
# ):
#     try:
#         current_date = datetime.now().date()
        
#         # Fetch all documents with their part numbers
#         query = (
#             db.query(Document, PartNumber)
#             .outerjoin(PartNumber, Document.part_number_id == PartNumber.id)
#             .filter(Document.plant == plant)
#             .filter(Document.validity_date.isnot(None))
#         )
        
#         documents = query.all()
#         notifications_sent = 0
        
#         for doc, part in documents:
#             if doc.validity_date:
#                 days_remaining = (doc.validity_date.date() - current_date).days
                
#                 # Check if document is expiring in 15 days or has expired
#                 if days_remaining <= 15 or days_remaining < 0:
#                     document_info = {
#                         "file_name": doc.file_name,
#                         "part_number": part.part_number if part else None,
#                         "expiry_date": doc.validity_date.strftime("%Y-%m-%d"),
#                         "days_remaining": days_remaining,
#                         "file_path": doc.file_path
#                     }
                    
#                     background_tasks.add_task(send_expiration_notification, document_info)
#                     notifications_sent += 1
        
#         return {
#             "message": f"Checking completed. {notifications_sent} notification(s) queued for sending.",
#             "notifications_sent": notifications_sent
#         }
        
#     except Exception as e:
#         logger.error(f"Error in check_expiring_documents: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))
