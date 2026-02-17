"""Authentication and authorization."""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token
security = HTTPBearer()

CSRF_TOKEN_SALT = "policycheck-csrf-token"
csrf_serializer = URLSafeTimedSerializer(SECRET_KEY)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength for user registration.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one non-alphanumeric character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must include at least one digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must include at least one special character"
    return True, "ok"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def create_csrf_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a stateless CSRF token signed with SECRET_KEY."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": subject,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "ttl": int(expires_delta.total_seconds()),
    }
    return csrf_serializer.dumps(payload, salt=CSRF_TOKEN_SALT)


def validate_csrf_token(token: str, expected_subject: Optional[str] = None) -> bool:
    """Validate CSRF token signature, expiration, and optional subject binding."""
    max_age_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60

    try:
        payload = csrf_serializer.loads(
            token,
            salt=CSRF_TOKEN_SALT,
            max_age=max_age_seconds,
        )
    except (SignatureExpired, BadSignature):
        return False

    if not isinstance(payload, dict):
        return False

    token_subject = payload.get("sub")
    if not token_subject:
        return False

    if expected_subject is not None and token_subject != expected_subject:
        return False

    return True


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    This is used as a FastAPI dependency.
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get the current authenticated user from JWT token (optional).
    
    Returns None if no valid credentials provided.
    Used for endpoints that support both auth methods.
    
    IMPROVEMENT: Catches specific exceptions instead of bare except.
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        payload = decode_token(token)
        
        username: str = payload.get("sub")
        if username is None:
            return None
        
        user = db.query(User).filter(User.username == username).first()
        return user
    except (JWTError, HTTPException):
        # Invalid or expired token
        return None
    except Exception as e:
        # Log unexpected errors but still fail gracefully
        logger.warning(f"Unexpected error in get_current_user_optional: {e}")
        return None


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user by username and password."""
    user = db.query(User).filter(User.username == username).first()
    
    if not user:
        return None
    
    if not verify_password(password, user.password_hash):
        return None
    
    return user


def create_user(db: Session, username: str, password: str, name: str, role: str = "reviewer", country: str = "NZ") -> User:
    """Create a new user."""
    is_valid, message = validate_password_strength(password)
    if not is_valid:
        raise ValueError(message)

    hashed_password = get_password_hash(password)
    
    user = User(
        username=username,
        password_hash=hashed_password,
        name=name,
        role=role,
        country=country
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user
