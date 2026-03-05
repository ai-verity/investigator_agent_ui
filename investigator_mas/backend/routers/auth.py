"""
backend/routers/auth.py
POST /auth/login  →  LoginResponse (JWT + role)
"""

from fastapi import APIRouter, HTTPException, status
from backend.models.schemas import LoginRequest, LoginResponse
from backend.services.auth_service import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid username or password")
    token = create_access_token(user["username"], user["role"])
    return LoginResponse(access_token=token, role=user["role"])
