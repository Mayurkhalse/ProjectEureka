"""WebAuthn Router for Biometric Authentication (Face ID, Windows Hello, Touch ID).

Strict Security & Privacy Design:
- ZERO biometric images, templates, or facial embeddings stored on the server.
- Uses standard FIDO2 / WebAuthn protocol (py_webauthn) via device authenticator.
- Public key cryptography: device signs challenge using local secure enclave.
- Server validates assertion signature with stored public key.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session, sessionmaker
from jose import JWTError, jwt

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    AuthenticatorAttachment,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from eureka.api.auth import TokenData, create_access_token, get_current_user
from eureka.core.config import get_settings
from eureka.models.base import Base
from eureka.models.entities import WebAuthnCredential
from eureka.models.enums import UserRole

logger = logging.getLogger("eureka.auth.webauthn")
settings = get_settings()

router = APIRouter(prefix="/api/v1/auth/webauthn", tags=["WebAuthn Biometric Face Lock"])

# Database Engine & Session Resolution
_target_engine = None
_SessionLocal = None


def get_engine():
    global _target_engine, _SessionLocal
    if _target_engine is not None:
        return _target_engine, _SessionLocal

    try:
        from eureka.core.database import sync_engine
        with sync_engine.connect() as conn:
            conn.execute(select(1))
        _target_engine = sync_engine
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
        logger.info("WebAuthn router connected to PostgreSQL.")
    except Exception as exc:
        current_dir = Path(__file__).resolve().parent
        root_dir = current_dir.parents[3]
        sqlite_candidates = [
            root_dir / "backend" / "eureka.db",
            root_dir / "eureka.db",
        ]
        target_path = None
        for p in sqlite_candidates:
            if p.exists():
                target_path = p
                break
        if not target_path:
            target_path = root_dir / "backend" / "eureka.db"

        logger.info(f"PostgreSQL not reachable ({exc}). Using SQLite at {target_path}")
        _target_engine = create_engine(
            f"sqlite:///{target_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_target_engine)

    # Ensure tables exist
    Base.metadata.create_all(bind=_target_engine)
    return _target_engine, _SessionLocal


def get_db():
    _, session_factory = get_engine()
    db: Session = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_allowed_origins() -> List[str]:
    origins = [
        settings.WEBAUTHN_ORIGIN,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://localhost:3000",
    ]
    # Filter out empty or duplicate
    seen = set()
    res = []
    for o in origins:
        if o and o not in seen:
            seen.add(o)
            res.append(o)
    return res


def make_challenge_token(challenge: bytes, user_id: str, flow: str) -> str:
    payload = {
        "challenge": bytes_to_base64url(challenge),
        "user_id": user_id,
        "flow": flow,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def parse_challenge_token(token: str, expected_flow: str) -> tuple[bytes, str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("flow") != expected_flow:
            raise HTTPException(status_code=400, detail="Challenge token flow mismatch")
        challenge = base64url_to_bytes(payload["challenge"])
        user_id = payload["user_id"]
        return challenge, user_id
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or expired WebAuthn challenge token: {exc}",
        )


# Request & Response Schemas
class RegisterOptionsRequest(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None


class VerifyRegistrationRequest(BaseModel):
    credential: Dict[str, Any]
    challenge_token: str
    label: Optional[str] = "Face ID / Windows Hello"


class LoginOptionsRequest(BaseModel):
    username: Optional[str] = None


class VerifyLoginRequest(BaseModel):
    credential: Dict[str, Any]
    challenge_token: str
    username: Optional[str] = None


class CredentialSummary(BaseModel):
    id: str
    credential_id: str
    label: str
    created_at: str
    last_used_at: Optional[str]


# ---------------------------------------------------------------------------
# 1. Registration Flow: Register Options
# ---------------------------------------------------------------------------
@router.post("/register-options")
def get_register_options(
    req: RegisterOptionsRequest,
    current_user: Optional[TokenData] = Depends(lambda: None),
    db: Session = Depends(get_db),
):
    """Generate WebAuthn registration options for platform biometric face lock."""
    # Resolve user
    user_id = req.username or (current_user.username if current_user else "dg_admin")
    display_name = req.display_name or user_id

    # Exclude already registered credentials for this user
    existing_creds = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    ).scalars().all()

    exclude_descriptors = []
    for c in existing_creds:
        try:
            exclude_descriptors.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            )
        except Exception:
            continue

    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user_id.encode("utf-8"),
        user_name=user_id,
        user_display_name=display_name,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude_descriptors,
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            COSEAlgorithmIdentifier.EDDSA,
        ],
    )

    challenge_token = make_challenge_token(options.challenge, user_id, "registration")
    options_dict = json.loads(options_to_json(options))

    return {
        "status": "success",
        "options": options_dict,
        "challenge_token": challenge_token,
    }


# ---------------------------------------------------------------------------
# 2. Registration Flow: Verify Registration
# ---------------------------------------------------------------------------
@router.post("/verify-registration")
def verify_registration(
    req: VerifyRegistrationRequest,
    db: Session = Depends(get_db),
):
    """Verify WebAuthn attestation response and persist credential public key."""
    expected_challenge, user_id = parse_challenge_token(req.challenge_token, "registration")
    allowed_origins = get_allowed_origins()

    try:
        verified = verify_registration_response(
            credential=req.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=allowed_origins,
            require_user_verification=False,
        )
    except Exception as exc:
        logger.warning(f"WebAuthn registration verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Biometric registration verification failed: {str(exc)}",
        )

    cred_id_str = bytes_to_base64url(verified.credential_id)
    pub_key_str = bytes_to_base64url(verified.credential_public_key)

    # Check if credential already exists
    existing = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cred_id_str)
    ).scalar_one_or_none()

    if existing:
        existing.public_key = pub_key_str
        existing.sign_count = verified.sign_count
        existing.label = req.label or existing.label
        existing.last_used_at = datetime.now(timezone.utc)
    else:
        new_cred = WebAuthnCredential(
            user_id=user_id,
            credential_id=cred_id_str,
            public_key=pub_key_str,
            sign_count=verified.sign_count,
            label=req.label or "Face ID / Windows Hello",
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_cred)

    db.commit()

    return {
        "status": "success",
        "message": "Biometric authenticator registered successfully.",
        "user_id": user_id,
        "credential_id": cred_id_str,
        "label": req.label or "Face ID / Windows Hello",
    }


# ---------------------------------------------------------------------------
# 3. Authentication Flow: Login Options
# ---------------------------------------------------------------------------
@router.post("/login-options")
def get_login_options(
    req: LoginOptionsRequest,
    db: Session = Depends(get_db),
):
    """Generate WebAuthn assertion challenge for face lock login."""
    user_id = req.username or "dg_admin"

    # Find registered credentials for this user
    creds = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    ).scalars().all()

    allow_descriptors = []
    for c in creds:
        try:
            allow_descriptors.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            )
        except Exception:
            continue

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=allow_descriptors if allow_descriptors else None,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    challenge_token = make_challenge_token(options.challenge, user_id, "authentication")
    options_dict = json.loads(options_to_json(options))

    return {
        "status": "success",
        "has_registered_credentials": len(creds) > 0,
        "options": options_dict,
        "challenge_token": challenge_token,
    }


# ---------------------------------------------------------------------------
# 4. Authentication Flow: Verify Login
# ---------------------------------------------------------------------------
@router.post("/verify-login")
def verify_login(
    req: VerifyLoginRequest,
    db: Session = Depends(get_db),
):
    """Verify biometric assertion response and issue signed JWT access token."""
    expected_challenge, token_user_id = parse_challenge_token(req.challenge_token, "authentication")
    allowed_origins = get_allowed_origins()

    # Find the credential in the database
    raw_cred_id = req.credential.get("id") or req.credential.get("rawId")
    if not raw_cred_id:
        raise HTTPException(status_code=400, detail="Missing credential ID in assertion response")

    cred_record = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == raw_cred_id)
    ).scalar_one_or_none()

    if not cred_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Biometric credential not registered on this device or account.",
        )

    try:
        verified = verify_authentication_response(
            credential=req.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=allowed_origins,
            credential_public_key=base64url_to_bytes(cred_record.public_key),
            credential_current_sign_count=cred_record.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        logger.warning(f"WebAuthn assertion verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Biometric face verification rejected: {str(exc)}",
        )

    # Update sign count & last used
    cred_record.sign_count = verified.new_sign_count
    cred_record.last_used_at = datetime.now(timezone.utc)
    db.commit()

    # Determine user role from username
    user_id = cred_record.user_id
    role = UserRole.DG_STATE_ADMIN
    district_code = None

    if "collector" in user_id.lower():
        role = UserRole.DISTRICT_COLLECTOR
        district_code = "MH-12"
    elif "dio" in user_id.lower():
        role = UserRole.DIO_DESK
        district_code = "MH-12"

    access_token = create_access_token(
        username=user_id,
        role=role,
        district_code=district_code,
    )

    return {
        "status": "success",
        "message": "Biometric face verification successful.",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user_id,
            "role": role.value,
            "district_code": district_code,
        },
    }


# ---------------------------------------------------------------------------
# 5. List Registered Credentials
# ---------------------------------------------------------------------------
@router.get("/credentials")
def list_credentials(
    username: str = Query(default="dg_admin"),
    db: Session = Depends(get_db),
):
    """List registered WebAuthn authenticators for the user."""
    creds = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == username)
    ).scalars().all()

    return {
        "status": "success",
        "username": username,
        "total": len(creds),
        "credentials": [
            CredentialSummary(
                id=c.id,
                credential_id=c.credential_id,
                label=c.label or "Face ID / Windows Hello",
                created_at=c.created_at.isoformat() if c.created_at else "",
                last_used_at=c.last_used_at.isoformat() if c.last_used_at else None,
            ).model_dump()
            for c in creds
        ],
    }


# ---------------------------------------------------------------------------
# 6. Delete Credential
# ---------------------------------------------------------------------------
@router.delete("/credentials/{credential_id}")
def delete_credential(
    credential_id: str,
    db: Session = Depends(get_db),
):
    """Deregister a biometric authenticator."""
    cred = db.execute(
        select(WebAuthnCredential).where(
            (WebAuthnCredential.id == credential_id) | (WebAuthnCredential.credential_id == credential_id)
        )
    ).scalar_one_or_none()

    if not cred:
        raise HTTPException(status_code=404, detail="Authenticator credential not found")

    db.delete(cred)
    db.commit()

    return {
        "status": "success",
        "message": "Authenticator deregistered successfully.",
        "credential_id": credential_id,
    }
