from fastapi import APIRouter, status

from src.core.dependencies import DbSession
from src.schemas.user import LoginResponse, UserCreate, UserLogin, UserResponse
from src.api.controllers import auth as auth_controller

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: DbSession):
    return auth_controller.register_user(user_in=user_in, db=db)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(user_in: UserLogin, db: DbSession):
    return auth_controller.login_user(user_in=user_in, db=db)