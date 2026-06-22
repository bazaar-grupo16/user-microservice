from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.user import UserCreate, UserLogin, GoogleLoginRequest
from src.repositories import user as user_repo
from src.core.security import verify_password, get_password_hash
from src.schemas.user import ForgotPasswordRequest, VerifyCodeRequest, ResetPasswordRequest
from src.models.user import User
import asyncio
import resend
import random
from datetime import datetime, timedelta
from src.core.config import get_settings
from src.services import auth_client, profile_client, google_client, catalog_client
import logging
import uuid

logger = logging.getLogger(__name__)

settings = get_settings()
resend.api_key = settings.RESEND_API_KEY

async def register_user(user_in: UserCreate, db: AsyncSession):

    existing_user = await user_repo.get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )
    new_user = await user_repo.create_user(db, user_in=user_in)

    await profile_client.create_profile(
        user_id=str(new_user.id),
        name=user_in.name
    )

    return new_user


async def login_user(user_in: UserLogin, db: AsyncSession):
    user = await user_repo.get_user_by_email(db, email=user_in.email)
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
    token_response = await auth_client.issue_token(user_id=user.id, is_admin=user.is_admin)

    return token_response

async def login_admin(user_in: UserLogin, db: AsyncSession):
    user = await user_repo.get_user_by_email(db, email=user_in.email)
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
    token_response = await auth_client.issue_token(user_id=user.id, is_admin=user.is_admin)

    return token_response

async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession):
    user = await user_repo.get_user_by_email(db=db, email=request.email)
    
    success_message = {"message": "Si el email está registrado, te enviaremos un código."}
    
    if not user:
        return success_message

    codigo = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    await user_repo.create_verification_code(
        db=db,
        user_id=user.id,
        code=codigo,
        expires_at=expires_at
    )

    try:
        # ``resend`` only exposes a blocking client, so run it in a worker
        # thread to avoid blocking the event loop.
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": "Bazaar App <no-reply@tomasbp.com>",
                "to": [user.email],
                "subject": "Código de recuperación de contraseña",
                "html": f"""
                <h2>Recuperación de contraseña</h2>
                <p>Tu código de seguridad de 6 dígitos es:</p>
                <h1 style="color: #ff6900;">{codigo}</h1>
                <p>Este código expira en 15 minutos.</p>
            """,
            },
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error al intentar enviar el correo de recuperación")

    return success_message

async def verify_code(request: VerifyCodeRequest, db: AsyncSession):
    user = await user_repo.get_user_by_email(db, email=request.email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db_code = await user_repo.get_verification_code(db, user_id=user.id, code=request.code)

    if not db_code:
        raise HTTPException(status_code=400, detail="Código inválido")

    if db_code.expires_at < datetime.utcnow():
        await user_repo.delete_verification_code(db, db_code)
        raise HTTPException(status_code=400, detail="El código ha expirado")

    return {"message": "Código verificado con éxito"}

async def reset_password(request: ResetPasswordRequest, db: AsyncSession):
    user = await user_repo.get_user_by_email(db, email=request.email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db_code = await user_repo.get_verification_code(db, user_id=user.id, code=request.code)
    if not db_code or db_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Sesión de recuperación inválida o expirada")

    hashed_pass = get_password_hash(request.new_password)
    await user_repo.update_user_password(db, user=user, hashed_pass=hashed_pass)

    await user_repo.delete_verification_code(db, db_code)

    return {"message": "Contraseña actualizada correctamente"}

async def list_users(db: AsyncSession, page: int, size: int, search: str | None):
    skip = (page - 1) * size
    total, users = await user_repo.get_users_paginated(db, skip=skip, limit=size, search=search)
    return {
        "items": users,
        "total": total,
        "page": page,
        "size": size
    }

async def block_user(db: AsyncSession, user_id: uuid.UUID, current_admin: User):
    if current_admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrador no puede bloquearse a sí mismo.",
        )

    target_user = await user_repo.get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    await user_repo.set_user_active_status(db, target_user, is_active=False)
    
    
    await catalog_client.block_seller_products(str(user_id), str(current_admin.id))
    
    return {"message": "Usuario y productos bloqueados correctamente"}

async def unblock_user(db: AsyncSession, user_id: uuid.UUID, current_admin: User):
    target_user = await user_repo.get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    await user_repo.set_user_active_status(db, target_user, is_active=True)
    
    await catalog_client.unblock_seller_products(str(user_id), str(current_admin.id))
    
    return {"message": "Usuario y productos desbloqueados correctamente"}


async def logout_user(user: object) -> None:
    """Logout a user by revoking their tokens at the auth service."""
    await auth_client.delete_token(user_id=user.id)


async def login_with_google(request: GoogleLoginRequest, db: AsyncSession):
    try:
        idinfo = await asyncio.to_thread(google_client.verify_id_token, request.google_id_token)
    except ValueError as exc:
        logger.warning(
            "Google ID token verification failed (expected aud=%s): %s",
            settings.GOOGLE_CLIENT_ID,
            exc,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google ID token")
    except Exception:
        logger.exception("Unexpected error verifying Google ID token")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error verifying Google ID token")

    # Verified ID token — take values from idinfo.
    google_id: str = idinfo.get("sub")
    email: str = idinfo.get("email")
    name: str | None = idinfo.get("name")
    email_verified = idinfo.get("email_verified")
    if not google_id or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google ID token missing required claims")
    if email_verified is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account email not verified")

    user = await user_repo.get_user_by_google_id(db, google_id=google_id)

    if user is None:
        user = await user_repo.get_user_by_email(db, email=email)
        if user is not None:
            await user_repo.link_google_account(db, user=user, google_id=google_id)
        else:
            user = await user_repo.create_oauth_user(db, email=email, name=name, google_id=google_id)
            await profile_client.create_profile(user_id=str(user.id), name=name or "")

    return await auth_client.issue_token(user_id=user.id, is_admin=user.is_admin)
