from datetime import datetime

from fastapi import APIRouter, Depends, status, HTTPException, Response
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from Auth import oauth2, utils
from Database.db_setup import get_db
from orm_class import orm_models
from orm_class.base_models import CreateUser
from orm_class.orm_models import User

router = APIRouter(tags=['Authentication'])


@router.post('/auth')
def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(orm_models.User).filter(orm_models.User.username == user_credentials.username).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'invalid credentials')

    if not utils.verify(user_credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'invalid credentials')

    # create token
    # return token
    access_token = oauth2.create_access_token(data={"user_id": user.id})

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