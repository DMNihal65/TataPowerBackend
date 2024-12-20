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
    host_name: str = "default_host"
    user: str = "postgres"
    password: str = "siri2251105"
    host: str = "172.18.100.88"
    database: str = "Tata_Power"


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
