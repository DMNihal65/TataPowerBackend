from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os



# Construct the SQLAlchemy database URL using settings
# SQLALCHEMY_DATABASE_URL = "postgresql://postgres:siri2251105@172.18.100.88/Tata_Power"

# SQLALCHEMY_DATABASE_URL = "postgresql://postgres:postgres@172.18.7.91/Tata_Power"


# Get host, username, password, and database name from environment variables
DB_HOST = os.getenv("HOST", "localhost")  # Match the env var name in docker-compose
DB_USER = os.getenv("USER", "postgres")
DB_PASSWORD = os.getenv("PASSWORD", "admin")
DB_NAME = os.getenv("DATABASE", "Tata_Power")

# Construct the SQLAlchemy database URL dynamically
SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"


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


