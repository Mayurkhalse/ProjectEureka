"""JWT Authentication and Role-Based Access Control (RBAC) Middleware.

Strictly enforces DGIPR Command Center roles:
- 'DG State Admin'
- 'District Collector'
- 'DIO Desk'
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from eureka.core.config import get_settings
from eureka.models.enums import UserRole

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_bearer = HTTPBearer(auto_error=True)


class TokenData(BaseModel):
    username: str
    role: UserRole
    district_code: Optional[str] = None


def create_access_token(
    username: str,
    role: UserRole,
    district_code: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create signed HS256 JWT access token with role and optional district scope."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {
        "sub": username,
        "role": role.value if hasattr(role, "value") else str(role),
        "district_code": district_code,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
) -> TokenData:
    """Validate bearer token and extract authenticated user context."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        role_str: str = payload.get("role")
        district_code: Optional[str] = payload.get("district_code")

        if username is None or role_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject or role claims",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            role = UserRole(role_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized role: '{role_str}'",
            )

        return TokenData(username=username, role=role, district_code=district_code)

    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(allowed_roles: List[UserRole]):
    """FastAPI dependency factory enforcing strict RBAC authorization."""

    def role_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access forbidden: User role '{current_user.role.value}' is not authorized. "
                    f"Required one of: {[r.value for r in allowed_roles]}"
                ),
            )
        return current_user

    return role_checker
