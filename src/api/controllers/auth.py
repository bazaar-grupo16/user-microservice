from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from src.schemas.user import UserCreate, UserLogin
from src.repositories import user as user_repo
from src.core.security import verify_password, create_access_token
from src.schemas.user import ForgotPasswordRequest
import resend
import random
from datetime import datetime, timedelta
from src.core.config import get_settings

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

    return new_user


def login_user(user_in: UserLogin, db: Session):
    user = user_repo.get_user_by_email(db, email=user_in.email)
    if not user or not verify_password(user_in.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

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
            "from": "Bazaar App <onboarding@resend.dev>",
            "to": [user.email], 
            "subject": "Código de recuperación de contraseña",
            "html": f"""
                <h2>Recuperación de contraseña</h2>
                <p>Tu código de seguridad de 6 dígitos es:</p>
                <h1 style="color: #ff6900;">{codigo}</h1>
                <p>Este código expira en 15 minutos.</p>
            """
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error al intentar enviar el correo.")

    return success_message
