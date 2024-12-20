from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


# Construct the SQLAlchemy database URL using settings
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:siri2251105@172.18.100.88/Tata_Power"

# Create the SQLAlchemy engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a Base class for our classes definitions
Base = declarative_base()

def get_db():
    try:
        db = SessionLocal()  # Create a database session
        yield db  # Use yield instead of return for context management in FastAPI
    finally:
        db.close()


