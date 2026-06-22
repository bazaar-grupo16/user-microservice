from datetime import datetime, timezone
from sqlalchemy import Uuid, Column, ForeignKey, String, Boolean, DateTime, text
from src.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Uuid, primary_key=True, index=True)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
