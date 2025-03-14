from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, status, HTTPException, Response, Query
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



@router.post("/auth")
def login(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    plant: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # Rest of the function remains the same
    user = db.query(User).filter(
        User.username == username,
        User.password == password,
        User.role == role,
        User.plant == plant
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": user.username})
    user_role = user.role

    log_entry = orm_models.UserLogs(
        user_id=user.id,
        username=user.username,
    )
    db.add(log_entry)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user_role,
        "plant": user.plant
    }

@router.post('/register', status_code=status.HTTP_201_CREATED)
def register_user(user: CreateUser, db: Session = Depends(get_db)):

    existing_user_username = db.query(User).filter(User.username == user.username).first()

    if existing_user_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    # Create new user instance
    new_user = User(
        username=user.username,
        role=user.role,
        created_at=datetime.utcnow(),  # Optional: Set created_at explicitly if needed
        updated_at=datetime.utcnow()  # Optional: Set updated_at explicitly if needed
    )
    new_user.password = user.password

    # Add the new user to the database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered successfully",
            "user": {"username": new_user.username, "role": new_user.role}}


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
