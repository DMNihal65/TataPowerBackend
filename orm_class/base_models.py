from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings

from dotenv import load_dotenv
import os

# Specify the absolute path to the .env file
dotenv_path = r"D:\siri\codes\pycharm\projects\Tata\main\configs\.env"

# Load environment variables from the specified .env file
load_dotenv(dotenv_path)


class Settings(BaseSettings):
    """Data model for configuration settings."""

    # Database provider (postgres, sqlite, etc.)
    host_name: str

    # Database user
    user: str

    # Database password for user
    password: str

    # Database host identifier
    host: str

    # Database name (within postgresql)
    database: str


settings = Settings()


# # Print the settings to verify they are loaded correctly
# print(settings.host_name)  # Output: postgres
# print(settings.user)       # Output: postgres
# print(settings.password)   # Output: siri2251105
# print(settings.host)       # Output: 172.18.100.240
# print(settings.database)   # Output: sensor_data

# LOGIN
class CreateUser(BaseModel):
    email: EmailStr
    username: str
    role: str
    password: str


class TokenData(BaseModel):
    username: str
