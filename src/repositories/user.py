from sqlalchemy.orm import Session
from src.models.user import User
from src.schemas.user import UserCreate
from src.core.security import get_password_hash

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user_in: UserCreate) -> User:
    hashed_pass = get_password_hash(user_in.password)
    new_user = User(email=user_in.email, password=hashed_pass, name=user_in.name)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user