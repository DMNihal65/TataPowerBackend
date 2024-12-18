# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from Database.db_setup import engine
from Routers import auth, Folder_master, partnumber_master, document_master
from orm_class import orm_models

app = FastAPI()

# Enable debugging
app.debug = True

# Create all tables
orm_models.Base.metadata.create_all(bind=engine)

# Configure CORS settings
origins = ["*"]  # Replace "*" with the specific allowed origins


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(Folder_master.router)
app.include_router(partnumber_master.router)
app.include_router(document_master.router)

# uvicorn main:app --reload --host 172.18.100.88 --port 7001
