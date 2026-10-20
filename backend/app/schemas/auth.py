from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserPublic(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    business_id: UUID | None
    is_active: bool

    model_config = {"from_attributes": True}