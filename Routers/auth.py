from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, status, HTTPException, Response, Query
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from Auth import oauth2, utils
from Auth.oauth2 import create_access_token
from Database.db_setup import get_db
from orm_class import orm_models
from orm_class.base_models import CreateUser
from orm_class.orm_models import User
from pydantic_schema.request_body import UserLogs

router = APIRouter(tags=['Signup/Login Handles'])


@router.post('/auth')
def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_credentials.username).first()
    if not user or not utils.verify(user_credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Invalid credentials')

    access_token = create_access_token(data={"sub": user.username})

    log_entry = orm_models.UserLogs(
        user_id=user.id,
        username=user.username,
        email=user.email
    )
    db.add(log_entry)
    db.commit()

    return {"access_token": access_token, "token_type": "bearer"}


@router.post('/register', status_code=status.HTTP_201_CREATED)
def register_user(user: CreateUser, db: Session = Depends(get_db)):
    # Check if email or username already exists
    existing_user_email = db.query(User).filter(User.email == user.email).first()
    existing_user_username = db.query(User).filter(User.username == user.username).first()

    if existing_user_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    if existing_user_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    # Create new user instance
    new_user = User(
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=datetime.utcnow(),  # Optional: Set created_at explicitly if needed
        updated_at=datetime.utcnow()  # Optional: Set updated_at explicitly if needed
    )
    hashed_password = utils.hash(user.password)
    new_user.password = hashed_password

    # Add the new user to the database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered successfully",
            "user": {"username": new_user.username, "email": new_user.email, "role": new_user.role}}


@router.get('/user-logs', response_model=List[UserLogs])
def get_user_logs(
        start_time: int = Query(..., example=1690982400),  # epoch timestamp for start time
        end_time: int = Query(..., example=1691664000),  # epoch timestamp for end time
        db: Session = Depends(get_db)
):
    try:
        # Convert epoch timestamps to datetime objects
        start_timestamp = datetime.fromtimestamp(start_time)
        end_timestamp = datetime.fromtimestamp(end_time)

        print(start_timestamp, end_timestamp)
        # Query the database
        logs = db.query(orm_models.UserLogs).filter(
            and_(
                orm_models.UserLogs.login_timestamp >= start_timestamp,
                orm_models.UserLogs.login_timestamp <= end_timestamp
            )
        ).all()

        if not logs:
            raise HTTPException(status_code=404, detail="No user logs found in the specified time range")

        return logs
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid epoch timestamp")
