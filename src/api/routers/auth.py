from fastapi import APIRouter, status, Query

from src.core.dependencies import AdminUser, DbSession, AuthenticatedUser
from src.schemas.user import AdminMeResponse, LoginResponse, UserCreate, UserLogin, UserResponse, ForgotPasswordRequest, MessageResponse, VerifyCodeRequest, ResetPasswordRequest, PaginatedUserResponse, GoogleLoginRequest
from src.api.controllers import auth as auth_controller
import uuid

router = APIRouter(tags=["Auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_in: UserCreate, db: DbSession):
    return await auth_controller.register_user(user_in=user_in, db=db)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(user_in: UserLogin, db: DbSession):
    return await auth_controller.login_user(user_in=user_in, db=db)


@router.post("/admin/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def admin_login(user_in: UserLogin, db: DbSession):
    return await auth_controller.login_admin(user_in=user_in, db=db)


@router.get("/admin/me", response_model=AdminMeResponse, status_code=status.HTTP_200_OK)
async def admin_me(admin_user: AdminUser):
    return admin_user


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def forgot_password(request: ForgotPasswordRequest, db: DbSession):
    return await auth_controller.forgot_password(request=request, db=db)

@router.post("/verify-code")
async def verify_code(request: VerifyCodeRequest, db: DbSession):
    return await auth_controller.verify_code(request=request, db=db)

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: DbSession):
    return await auth_controller.reset_password(request=request, db=db)


@router.post("/login/google", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login_google(request: GoogleLoginRequest, db: DbSession):
    return await auth_controller.login_with_google(request=request, db=db)


@router.delete("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: AuthenticatedUser):
    return await auth_controller.logout_user(user=user)

@router.get("/admin/users", response_model=PaginatedUserResponse, status_code=status.HTTP_200_OK)
async def get_users(
    admin_user: AdminUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, min_length=1)
):
    return await auth_controller.list_users(db=db, page=page, size=size, search=search)

@router.patch("/admin/users/{user_id}/block", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def block_user(user_id: uuid.UUID, admin_user: AdminUser, db: DbSession):
    return await auth_controller.block_user(db=db, user_id=user_id, current_admin=admin_user)

@router.patch("/admin/users/{user_id}/unblock", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def unblock_user(user_id: uuid.UUID, admin_user: AdminUser, db: DbSession):
    return await auth_controller.unblock_user(db=db, user_id=user_id)