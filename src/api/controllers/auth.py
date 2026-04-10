from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from src.schemas.user import UserCreate
from src.repositories import user as user_repo

def register_user(user_in: UserCreate, db: Session):
    
    new_user = user_repo.create_user(db, user_in=user_in)

    return new_user