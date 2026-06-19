from sqlalchemy.orm import Session
from src.models.user import User, VerificationCode
from datetime import datetime
from src.schemas.user import UserCreate
from src.core.security import get_password_hash
from sqlalchemy import or_
import uuid


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user_in: UserCreate) -> User:
    hashed_pass = get_password_hash(user_in.password)
    new_user = User(id=uuid.uuid4(),email=user_in.email, password=hashed_pass, name=user_in.name)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

def create_verification_code(db: Session, user_id: uuid.UUID, code: str, expires_at: datetime) -> VerificationCode:
    new_code = VerificationCode(
        id=uuid.uuid4(),
        user_id=user_id,
        code=code,
        expires_at=expires_at
    )
    db.add(new_code)
    db.commit()
    db.refresh(new_code)
    return new_code

def get_verification_code(db: Session, user_id: uuid.UUID, code: str) -> VerificationCode | None:
    return db.query(VerificationCode).filter(
        VerificationCode.user_id == user_id,
        VerificationCode.code == code
    ).first()

def update_user_password(db: Session, user: User, hashed_pass: str):
    user.password = hashed_pass
    db.commit()
    db.refresh(user)

def delete_verification_code(db: Session, verification_code: VerificationCode):
    db.delete(verification_code)
    db.commit()


def get_user_by_google_id(db: Session, google_id: str) -> User | None:
    return db.query(User).filter(User.google_id == google_id).first()


def create_oauth_user(db: Session, email: str, name: str | None, google_id: str) -> User:
    new_user = User(id=uuid.uuid4(), email=email, name=name, google_id=google_id)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def link_google_account(db: Session, user: User, google_id: str) -> User:
    user.google_id = google_id
    db.commit()
    db.refresh(user)
    return user

def get_users_paginated(db: Session, skip: int, limit: int, search: str | None = None):
    query = db.query(User)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.email.ilike(search_term),
                User.name.ilike(search_term)
            )
        )
    
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    return total, users

def set_user_active_status(db: Session, user: User, is_active: bool) -> User:
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user

def delete_user(db: Session, user: User):
    db.delete(user)
    db.commit()