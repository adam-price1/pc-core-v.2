"""Authentication API endpoints."""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator

from app.database import get_db
from app.auth import (
    authenticate_user,
    create_access_token,
    create_csrf_token,
    create_user,
    get_current_user,
    validate_password_strength,
)
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def log_security_event(
    event_type: str,
    username: str,
    ip_address: str,
    success: bool,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Log security-relevant authentication events."""
    logger.info(
        "SecurityEvent type=%s user=%s ip=%s success=%s details=%s",
        event_type,
        username,
        ip_address,
        success,
        details or {},
    )


class LoginRequest(BaseModel):
    """Login request."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with JWT token."""
    access_token: str
    csrf_token: str
    token_type: str
    user: dict


class RegisterRequest(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(default="reviewer", min_length=1, max_length=50)
    country: str = Field(default="NZ", max_length=5)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        is_valid, message = validate_password_strength(value)
        if not is_valid:
            raise ValueError(message)
        return value


class UserResponse(BaseModel):
    """User information response."""
    id: int
    username: str
    name: str
    role: str
    country: str
    
    class Config:
        from_attributes = True


@router.post("/login", response_model=LoginResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    ip_address = _client_ip(request)
    user = authenticate_user(db, credentials.username, credentials.password)
    
    if not user:
        log_security_event(
            event_type="LOGIN_FAILED",
            username=credentials.username,
            ip_address=ip_address,
            success=False,
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.username})
    csrf_token = create_csrf_token(subject=user.username)
    log_security_event(
        event_type="LOGIN_SUCCESS",
        username=user.username,
        ip_address=ip_address,
        success=True,
    )
    
    return LoginResponse(
        access_token=access_token,
        csrf_token=csrf_token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
            "country": user.country
        }
    )


@router.post("/register", response_model=UserResponse)
def register(
    user_data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Register a new user."""
    ip_address = _client_ip(request)
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        log_security_event(
            event_type="REGISTER_FAILED",
            username=user_data.username,
            ip_address=ip_address,
            success=False,
            details={"reason": "username_exists"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Create user
    try:
        user = create_user(
            db,
            username=user_data.username,
            password=user_data.password,
            name=user_data.name,
            role=user_data.role,
            country=user_data.country
        )
    except ValueError as exc:
        log_security_event(
            event_type="REGISTER_FAILED",
            username=user_data.username,
            ip_address=ip_address,
            success=False,
            details={"reason": "weak_password"},
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    log_security_event(
        event_type="REGISTER_SUCCESS",
        username=user.username,
        ip_address=ip_address,
        success=True,
    )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        name=user.name,
        role=user.role,
        country=user.country
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        name=current_user.name,
        role=current_user.role,
        country=current_user.country
    )
