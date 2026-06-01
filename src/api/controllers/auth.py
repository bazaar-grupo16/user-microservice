from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from src.schemas.user import UserCreate, UserLogin
from src.repositories import user as user_repo
from src.core.security import verify_password, get_password_hash
from src.schemas.user import ForgotPasswordRequest, VerifyCodeRequest, ResetPasswordRequest
from src.models.user import User
import resend
import random
from datetime import datetime, timedelta
from src.core.config import get_settings
from src.services import auth_client, profile_client
import uuid

settings = get_settings()
resend.api_key = settings.RESEND_API_KEY

def register_user(user_in: UserCreate, db: Session):

    existing_user = user_repo.get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )
    new_user = user_repo.create_user(db, user_in=user_in)

    profile_client.create_profile(
        user_id=str(new_user.id),
        name=user_in.name
    )

    return new_user


def login_user(user_in: UserLogin, db: Session):
    user = user_repo.get_user_by_email(db, email=user_in.email)
    if not user or not verify_password(user_in.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está suspendida. Por favor, contacta a soporte.",
        )
    token_response = auth_client.issue_token(user_id=user.id, is_admin=user.is_admin)

    return token_response

def login_admin(user_in: UserLogin, db: Session):
    user = user_repo.get_user_by_email(db, email=user_in.email)
    if (
        not user
        or not verify_password(user_in.password, user.password)
        or not user.is_active
        or not user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token_response = auth_client.issue_token(user_id=user.id, is_admin=user.is_admin)

    return token_response

def forgot_password(request: ForgotPasswordRequest, db: Session):
    user = user_repo.get_user_by_email(db=db, email=request.email)
    
    success_message = {"message": "Si el email está registrado, te enviaremos un código."}
    
    if not user:
        return success_message

    codigo = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    user_repo.create_verification_code(
        db=db,
        user_id=user.id, 
        code=codigo, 
        expires_at=expires_at
    )

    try:
        resend.Emails.send({
            "from": "Bazaar App <no-reply@tomasbp.com>",
            "to": [user.email], 
            "subject": "Código de recuperación de contraseña",
            "html": f"""
                <h2>Recuperación de contraseña</h2>
                <p>Tu código de seguridad de 6 dígitos es:</p>
                <h1 style="color: #ff6900;">{codigo}</h1>
                <p>Este código expira en 15 minutos.</p>
            """
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Error al intentar enviar el correo de recuperación")

    return success_message

def verify_code(request: VerifyCodeRequest, db: Session):
    user = user_repo.get_user_by_email(db, email=request.email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db_code = user_repo.get_verification_code(db, user_id=user.id, code=request.code)
    
    if not db_code:
        raise HTTPException(status_code=400, detail="Código inválido")
    
    if db_code.expires_at < datetime.utcnow():
        user_repo.delete_verification_code(db, db_code)
        raise HTTPException(status_code=400, detail="El código ha expirado")

    return {"message": "Código verificado con éxito"}

def reset_password(request: ResetPasswordRequest, db: Session):
    user = user_repo.get_user_by_email(db, email=request.email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db_code = user_repo.get_verification_code(db, user_id=user.id, code=request.code)
    if not db_code or db_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Sesión de recuperación inválida o expirada")

    hashed_pass = get_password_hash(request.new_password)
    user_repo.update_user_password(db, user=user, hashed_pass=hashed_pass)
    
    user_repo.delete_verification_code(db, db_code)

    return {"message": "Contraseña actualizada correctamente"}

def list_users(db: Session, page: int, size: int, search: str | None):
    skip = (page - 1) * size
    total, users = user_repo.get_users_paginated(db, skip=skip, limit=size, search=search)
    return {
        "items": users,
        "total": total,
        "page": page,
        "size": size
    }

def block_user(db: Session, user_id: uuid.UUID, current_admin: User):
    if current_admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrador no puede bloquearse a sí mismo.",
        )
    
    target_user = user_repo.get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    
    user_repo.set_user_active_status(db, target_user, is_active=False)
    return {"message": "Usuario bloqueado correctamente"}

def unblock_user(db: Session, user_id: uuid.UUID):
    target_user = user_repo.get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    
    user_repo.set_user_active_status(db, target_user, is_active=True)
    return {"message": "Usuario desbloqueado correctamente"}


def logout_user(user: object) -> None:
    """Logout a user by revoking their tokens at the auth service."""
    auth_client.delete_token(user_id=user.id)
