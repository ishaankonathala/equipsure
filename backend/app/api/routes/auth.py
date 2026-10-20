from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserPublic
from app.services.auth import authenticate_user

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise INVALID_CREDENTIALS

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )
    return TokenResponse(access_token=token, expires_in=settings.access_token_minutes * 60)


@router.get("/me", response_model=UserPublic)
def me(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise INVALID_CREDENTIALS

    try:
        claims = decode_access_token(credentials.credentials)
    except Exception:
        raise INVALID_CREDENTIALS

    user = db.get(User, UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise INVALID_CREDENTIALS
    return user