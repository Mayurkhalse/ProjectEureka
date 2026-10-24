"""FastAPI router for Meeting Changes data foundation:

Provides role-scoped read-only endpoints for:
- /api/v1/districts/{code}/positions
- /api/v1/districts/{code}/hoardings
- /api/v1/districts/{code}/clippings
- /api/v1/districts/{code}/social
- /api/v1/districts/{code}/tv
- /api/v1/hoardings (Statewide field publicity, with district/scheme/department filters)
- /api/v1/ticker (Statewide live news ticker items)
- /api/v1/sources/{source_type}/{source_id} (In-app source document detail viewer)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import create_engine, select, desc
from sqlalchemy.orm import Session, sessionmaker

from eureka.api.auth import TokenData, get_current_user
from eureka.core.config import get_settings
from eureka.core.reference_data import DISTRICTS
from eureka.models.base import Base
from eureka.models.entities import (
    DistrictPosition,
    SchemeHoarding,
    Clipping,
    SocialPost,
    TvClip,
    TickerItem,
)
from eureka.models.enums import UserRole

router = APIRouter(prefix="/api/v1", tags=["Data Foundation: Positions, Hoardings, Monitoring & Ticker"])

settings = get_settings()

# Engine resolution with automatic SQLite fallback & auto-seed
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
    except Exception:
        # Fallback to local SQLite datastore
        current_dir = Path(__file__).resolve().parent
        root_dir = current_dir.parents[3]
        sqlite_candidates = [
            root_dir / "backend" / "eureka.db",
            root_dir / "eureka.db",
            root_dir / "eureka_db.db",
        ]
        target_path = None
        for p in sqlite_candidates:
            if p.exists():
                target_path = p
                break
        if not target_path:
            target_path = root_dir / "backend" / "eureka.db"

        sqlite_url = f"sqlite:///{target_path.as_posix()}"
        _target_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

    # Ensure tables exist
    Base.metadata.create_all(bind=_target_engine, checkfirst=True)
    _SessionLocal = sessionmaker(bind=_target_engine, autocommit=False, autoflush=False)

    # Check if empty; if so, trigger seeder automatically
    with _SessionLocal() as session:
        try:
            cnt = session.query(DistrictPosition).count()
            if cnt == 0:
                from scripts.seed_demo_dashboard import seed_demo_data
                seed_demo_data()
        except Exception:
            pass

    return _target_engine, _SessionLocal


def get_db():
    _, SessionLocal = get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def enforce_district_scope(requested_code: str, current_user: TokenData):
    """Enforces that district-level roles can only access their assigned district."""
    req_upper = requested_code.strip().upper()
    if current_user.role in [UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK] and current_user.district_code:
        user_dist = current_user.district_code.strip().upper()
        if req_upper != user_dist:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"RBAC Scope Violation: {current_user.role.value} assigned to {user_dist} cannot access {req_upper}.",
            )


def normalize_district_code(code: str) -> str:
    """Normalizes input (e.g. 'thane', 'MH-04', '4') to standard 'MH-XX' code."""
    c = code.strip().upper()
    if c.startswith("MH-"):
        return c
    # Try finding by name or numeric id
    c_lower = code.strip().lower()
    for d_code, div, name_en, name_mr, alt in DISTRICTS:
        if c_lower in [name_en.lower(), d_code.lower()]:
            return d_code
        if alt and c_lower == alt.lower():
            return d_code
        # Try numeric e.g. "4" -> "MH-04"
        try:
            num = int(code)
            if int(d_code.split("-")[1]) == num:
                return d_code
        except ValueError:
            pass
    return c


# --- 1. District Positions ---

@router.get("/districts/{code}/positions")
def get_district_positions(
    code: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    norm_code = normalize_district_code(code)
    enforce_district_scope(norm_code, current_user)

    positions = (
        db.query(DistrictPosition)
        .filter(DistrictPosition.district_code == norm_code)
        .all()
    )

    # Sort deterministically by leadership hierarchy
    cat_order = {
        "MINISTER": 1,
        "MP": 2,
        "MLA": 3,
        "MLC": 4,
        "COLLECTOR": 5,
        "SP": 6,
        "ZP_CEO": 7,
        "MUNICIPAL": 8,
        "DIO": 9,
        "OTHER": 10,
    }
    positions_sorted = sorted(positions, key=lambda p: (cat_order.get(p.category, 99), p.id))

    return {
        "status": "success",
        "district_code": norm_code,
        "total_positions": len(positions_sorted),
        "provenance": "synthetic",
        "positions": [
            {
                "id": p.id,
                "district_code": p.district_code,
                "category": p.category,
                "designation_en": p.designation_en,
                "designation_mr": p.designation_mr,
                "person_name": p.person_name,
                "responsibilities_en": p.responsibilities_en,
                "responsibilities_mr": p.responsibilities_mr,
                "phone": p.phone,
                "email": p.email,
                "provenance": p.provenance,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in positions_sorted
        ],
    }


# --- 2. Scheme Hoardings (District scoped & Statewide) ---

@router.get("/districts/{code}/hoardings")
def get_district_hoardings(
    code: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    norm_code = normalize_district_code(code)
    enforce_district_scope(norm_code, current_user)

    hoardings = (
        db.query(SchemeHoarding)
        .filter(SchemeHoarding.district_code == norm_code)
        .order_by(SchemeHoarding.id)
        .all()
    )

    return {
        "status": "success",
        "district_code": norm_code,
        "total_hoardings": len(hoardings),
        "provenance": "synthetic",
        "hoardings": [
            {
                "id": h.id,
                "district_code": h.district_code,
                "scheme_name_en": h.scheme_name_en,
                "scheme_name_mr": h.scheme_name_mr,
                "department_code": h.department_code,
                "lat": h.lat,
                "lon": h.lon,
                "address": h.address,
                "size": h.size,
                "installed_on": h.installed_on,
                "expires_on": h.expires_on,
                "status": h.status,
                "announcement_en": h.announcement_en,
                "announcement_mr": h.announcement_mr,
                "image_url": h.image_url,
                "provenance": h.provenance,
            }
            for h in hoardings
        ],
    }


@router.get("/hoardings")
def get_statewide_hoardings(
    district_code: Optional[str] = Query(None, description="Optional filter by district code (e.g. MH-04)"),
    department_code: Optional[str] = Query(None, description="Optional filter by department"),
    scheme: Optional[str] = Query(None, description="Optional substring search in scheme name"),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(SchemeHoarding)

    # Scoping for district-level roles
    if current_user.role in [UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK] and current_user.district_code:
        query = query.filter(SchemeHoarding.district_code == current_user.district_code.strip().upper())
    elif district_code:
        norm_code = normalize_district_code(district_code)
        query = query.filter(SchemeHoarding.district_code == norm_code)

    if department_code:
        query = query.filter(SchemeHoarding.department_code == department_code.strip().upper())

    if scheme:
        pattern = f"%{scheme.strip()}%"
        query = query.filter(
            (SchemeHoarding.scheme_name_en.ilike(pattern)) | (SchemeHoarding.scheme_name_mr.ilike(pattern))
        )

    hoardings = query.order_by(SchemeHoarding.district_code, SchemeHoarding.id).all()

    return {
        "status": "success",
        "total_hoardings": len(hoardings),
        "provenance": "synthetic",
        "hoardings": [
            {
                "id": h.id,
                "district_code": h.district_code,
                "scheme_name_en": h.scheme_name_en,
                "scheme_name_mr": h.scheme_name_mr,
                "department_code": h.department_code,
                "lat": h.lat,
                "lon": h.lon,
                "address": h.address,
                "size": h.size,
                "installed_on": h.installed_on,
                "expires_on": h.expires_on,
                "status": h.status,
                "announcement_en": h.announcement_en,
                "announcement_mr": h.announcement_mr,
                "image_url": h.image_url,
                "provenance": h.provenance,
            }
            for h in hoardings
        ],
    }


# --- 3. News Clippings ---

@router.get("/districts/{code}/clippings")
def get_district_clippings(
    code: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    norm_code = normalize_district_code(code)
    enforce_district_scope(norm_code, current_user)

    items = (
        db.query(Clipping)
        .filter(Clipping.district_code == norm_code)
        .order_by(desc(Clipping.published_at))
        .all()
    )

    return {
        "status": "success",
        "district_code": norm_code,
        "total_clippings": len(items),
        "provenance": "synthetic",
        "clippings": [
            {
                "id": c.id,
                "district_code": c.district_code,
                "headline": c.headline,
                "outlet": c.outlet,
                "language": c.language,
                "published_at": c.published_at.isoformat() if c.published_at else None,
                "source_url": c.source_url,
                "clipping_image_url": c.clipping_image_url,
                "summary": c.summary,
                "provenance": c.provenance,
            }
            for c in items
        ],
    }


# --- 4. Social Posts ---

@router.get("/districts/{code}/social")
def get_district_social_posts(
    code: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    norm_code = normalize_district_code(code)
    enforce_district_scope(norm_code, current_user)

    items = (
        db.query(SocialPost)
        .filter(SocialPost.district_code == norm_code)
        .order_by(desc(SocialPost.posted_at))
        .all()
    )

    return {
        "status": "success",
        "district_code": norm_code,
        "total_social_posts": len(items),
        "provenance": "synthetic",
        "social_posts": [
            {
                "id": s.id,
                "district_code": s.district_code,
                "platform": s.platform,
                "handle": s.handle,
                "post_url": s.post_url,
                "text": s.text,
                "posted_at": s.posted_at.isoformat() if s.posted_at else None,
                "engagement": s.engagement,
                "provenance": s.provenance,
            }
            for s in items
        ],
    }


# --- 5. Broadcast TV Clips ---

@router.get("/districts/{code}/tv")
def get_district_tv_clips(
    code: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    norm_code = normalize_district_code(code)
    enforce_district_scope(norm_code, current_user)

    items = (
        db.query(TvClip)
        .filter(TvClip.district_code == norm_code)
        .order_by(desc(TvClip.aired_at))
        .all()
    )

    return {
        "status": "success",
        "district_code": norm_code,
        "total_tv_clips": len(items),
        "provenance": "synthetic",
        "tv_clips": [
            {
                "id": t.id,
                "district_code": t.district_code,
                "channel": t.channel,
                "programme": t.programme,
                "clip_url": t.clip_url,
                "aired_at": t.aired_at.isoformat() if t.aired_at else None,
                "start_offset_sec": t.start_offset_sec,
                "transcript_text": t.transcript_text,
                "provenance": t.provenance,
            }
            for t in items
        ],
    }


# --- 6. Live News Ticker ---

@router.get("/ticker")
def get_live_ticker_items(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Statewide live news ticker items refreshed periodically."""
    now = datetime.now(timezone.utc)
    items = (
        db.query(TickerItem)
        .order_by(desc(TickerItem.created_at))
        .limit(20)
        .all()
    )

    return {
        "status": "success",
        "total_items": len(items),
        "is_live": False,  # Flag for UI: True when connected to live Kafka/feed, False for synthetic sample
        "provenance": "synthetic",
        "items": [
            {
                "id": item.id,
                "kind": item.kind,
                "text_en": item.text_en,
                "text_mr": item.text_mr,
                "link_url": item.link_url,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                "provenance": item.provenance,
            }
            for item in items
        ],
    }


# --- 7. In-App Source Detail Viewer (/sources/{type}/{id}) ---

@router.get("/sources/{source_type}/{source_id}")
def get_source_detail(
    source_type: str,
    source_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    st = source_type.strip().lower()
    sid = source_id.strip()

    if st in ["clipping", "clippings"]:
        item = db.query(Clipping).filter(Clipping.id == sid).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Clipping '{sid}' not found")
        return {
            "status": "success",
            "type": "clipping",
            "id": item.id,
            "district_code": item.district_code,
            "title": item.headline,
            "outlet": item.outlet,
            "language": item.language,
            "timestamp": item.published_at.isoformat() if item.published_at else None,
            "source_url": item.source_url,
            "image_url": item.clipping_image_url,
            "body": item.summary,
            "provenance": item.provenance,
        }

    elif st in ["social", "social_post", "social_posts"]:
        item = db.query(SocialPost).filter(SocialPost.id == sid).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Social post '{sid}' not found")
        return {
            "status": "success",
            "type": "social",
            "id": item.id,
            "district_code": item.district_code,
            "platform": item.platform,
            "handle": item.handle,
            "source_url": item.post_url,
            "timestamp": item.posted_at.isoformat() if item.posted_at else None,
            "body": item.text,
            "engagement": item.engagement,
            "provenance": item.provenance,
        }

    elif st in ["tv", "tv_clip", "tv_clips"]:
        item = db.query(TvClip).filter(TvClip.id == sid).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"TV clip '{sid}' not found")
        return {
            "status": "success",
            "type": "tv",
            "id": item.id,
            "district_code": item.district_code,
            "channel": item.channel,
            "programme": item.programme,
            "source_url": item.clip_url,
            "timestamp": item.aired_at.isoformat() if item.aired_at else None,
            "start_offset_sec": item.start_offset_sec,
            "body": item.transcript_text,
            "provenance": item.provenance,
        }

    elif st in ["hoarding", "hoardings", "scheme"]:
        item = db.query(SchemeHoarding).filter(SchemeHoarding.id == sid).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Hoarding '{sid}' not found")
        return {
            "status": "success",
            "type": "hoarding",
            "id": item.id,
            "district_code": item.district_code,
            "title_en": item.scheme_name_en,
            "title_mr": item.scheme_name_mr,
            "department": item.department_code,
            "address": item.address,
            "coordinates": {"lat": item.lat, "lon": item.lon},
            "size": item.size,
            "installed_on": item.installed_on,
            "expires_on": item.expires_on,
            "status": item.status,
            "announcement_en": item.announcement_en,
            "announcement_mr": item.announcement_mr,
            "image_url": item.image_url,
            "provenance": item.provenance,
        }

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type '{source_type}'. Allowed: clipping, social, tv, hoarding.",
        )
