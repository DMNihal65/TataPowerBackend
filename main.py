# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from Database.db_setup import engine
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

# uvicorn main:app --reload --host 172.18.100.50 --port 7979
