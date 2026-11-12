import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from backend.models.oauth_identity import OAuthLoginProvider


def validate_email_str(v: str) -> str:
    v = v.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
        raise ValueError("Invalid email format")
    return v


class EmailBaseRequest(BaseModel):
    email: str = Field(..., min_length=5)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)


class RegisterRequest(EmailBaseRequest):
    name: str = Field(..., min_length=2)
    password: str = Field(..., min_length=6)


class RegisterResponse(BaseModel):
    message: str
    email: str
    requires_verification: bool = True


class VerifyOtpRequest(EmailBaseRequest):
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyOtpResponse(BaseModel):
    message: str
    email: str
    verified: bool = True


class ResendOtpRequest(EmailBaseRequest):
    pass


class LoginRequest(EmailBaseRequest):
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    is_verified: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class OAuthLoginStartResponse(BaseModel):
    provider: OAuthLoginProvider
    authorization_url: str
    state: str
    configured: bool
    auto_connects_publishing: bool
    sandbox_available: bool = True


class OAuthLoginCallbackRequest(BaseModel):
    code: str = Field(..., min_length=4)
    state: str = Field(..., min_length=8)
    redirect_uri: Optional[str] = None


class OAuthSandboxLoginRequest(BaseModel):
    name: str = Field(default="Sentinel Creator", min_length=2, max_length=120)
    email: Optional[str] = None
    handle: Optional[str] = None

    @field_validator("email")
    @classmethod
    def check_optional_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_email_str(v)


class OAuthTokenResponse(TokenResponse):
    auto_connected_platforms: List[str] = Field(default_factory=list)
