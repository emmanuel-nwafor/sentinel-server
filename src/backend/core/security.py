import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from backend.core.config import settings


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def create_oauth_state_token(user_id: str, platform: str, expires_minutes: int = 15) -> str:
    """Create a signed, short-lived state token for OAuth 2.0 CSRF protection."""
    return create_access_token(
        data={"sub": user_id, "platform": platform, "purpose": "oauth_state"},
        expires_delta=timedelta(minutes=expires_minutes),
    )


def verify_oauth_state_token(state_token: str, expected_platform: str) -> Optional[str]:
    """Verify OAuth state token and return user_id if valid for the given platform."""
    payload = decode_access_token(state_token)
    if not payload:
        return None
    if payload.get("purpose") != "oauth_state" or payload.get("platform") != expected_platform:
        return None
    return payload.get("sub")


def inspect_oauth_state_token(state_token: str) -> Optional[dict]:
    """Inspect and decode signed OAuth state token to dynamically identify platform and user."""
    payload = decode_access_token(state_token)
    if not payload or payload.get("purpose") != "oauth_state":
        return None
    return payload


class TokenCipher:
    """
    Symmetric Fernet cipher for encrypting OAuth access/refresh tokens at rest in PostgreSQL.
    """

    def __init__(self, key: Optional[str] = None):
        raw_key = key or settings.TOKEN_ENCRYPTION_KEY
        if raw_key:
            key_bytes = raw_key.encode("utf-8")
        else:
            digest = hashlib.sha256(settings.JWT_SECRET.encode("utf-8")).digest()
            key_bytes = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key_bytes)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext secret into a UTF-8 Fernet token string."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a stored Fernet token string back to plaintext."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt stored social token.") from exc


token_cipher = TokenCipher()


def generate_otp_code(length: int = 6) -> str:
    """Generate a cryptographically random numeric OTP code."""
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def hash_otp(otp_code: str, email: str) -> str:
    """Create a keyed HMAC-SHA256 digest of an OTP bound to the user's email."""
    message = f"{email.lower().strip()}:{otp_code.strip()}".encode("utf-8")
    return hmac.new(settings.JWT_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_otp_hash(otp_code: str, email: str, expected_hash: str) -> bool:
    """Constant-time comparison of an OTP candidate against its stored HMAC digest."""
    candidate = hash_otp(otp_code, email)
    return hmac.compare_digest(candidate, expected_hash)
