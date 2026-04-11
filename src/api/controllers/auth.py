from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from src.schemas.user import UserCreate, UserLogin
from src.repositories import user as user_repo


def register_user(user_in: UserCreate, db: Session):

    existing_user = user_repo.get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )
    new_user = user_repo.create_user(db, user_in=user_in)

    return new_user


def login_user(user_in: UserLogin, db: Session):
    user = user_repo.get_user_by_email(db, email=user_in.email)
    if not user or user.password != user_in.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return {"message": "Login successful"}
