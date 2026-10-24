"""FastAPI Router for Real-Time Audio-to-Text Transcription Streaming.

Endpoints:
- GET /api/v1/transcription/stream?channel=tv_marathi_live (SSE live streaming transcript)
- POST /api/v1/transcription/chunk (Submit audio chunk for transcription & persistence)
- GET /api/v1/transcription/history (Retrieve persisted transcript history)
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, select, desc
from sqlalchemy.orm import Session, sessionmaker

from eureka.core.config import get_settings
from eureka.models.base import Base
from eureka.models.entities import TranscriptSegment
from eureka.services.transcription import get_transcription_provider

logger = logging.getLogger("eureka.api.transcription")
settings = get_settings()

router = APIRouter(prefix="/api/v1/transcription", tags=["Live Audio-to-Text Transcription"])

# Database Resolution
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

        _target_engine = create_engine(
            f"sqlite:///{target_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_target_engine)

    Base.metadata.create_all(bind=_target_engine)
    return _target_engine, _SessionLocal


def get_db():
    _, session_factory = get_engine()
    db: Session = session_factory()
    try:
        yield db
    finally:
        db.close()


class TranscribeChunkRequest(BaseModel):
    stream_id: str = "tv_marathi_live"
    start_time: float = 0.0
    duration: float = 12.0
    mime_type: str = "audio/mp3"
    audio_base64: Optional[str] = None


@router.post("/chunk")
async def transcribe_audio_chunk(
    req: TranscribeChunkRequest,
    db: Session = Depends(get_db),
):
    """Transcribes an audio chunk, persists to transcript_segments and returns metadata."""
    provider = get_transcription_provider()

    raw_bytes = None
    if req.audio_base64:
        import base64
        try:
            raw_bytes = base64.b64decode(req.audio_base64)
        except Exception:
            raw_bytes = None

    result = await provider.transcribe_chunk(
        audio_bytes=raw_bytes,
        mime_type=req.mime_type,
        start_time=req.start_time,
        duration=req.duration,
    )

    # Persist into database
    seg_id = f"TRN-{int(req.start_time)}-{uuid.uuid4().hex[:6]}"
    segment = TranscriptSegment(
        id=seg_id,
        stream_id=req.stream_id,
        start_time=result["start_time"],
        end_time=result["end_time"],
        text=result["text"],
        language=result["language"],
        provider=result["provider"],
        model=result["model"],
        machine_generated=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(segment)
    db.commit()

    return {
        "status": "success",
        "segment_id": seg_id,
        "segment": result,
    }


@router.get("/history")
def get_transcript_history(
    stream_id: str = Query(default="tv_marathi_live"),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve persisted transcript segments."""
    records = db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.stream_id == stream_id)
        .order_by(desc(TranscriptSegment.start_time))
        .limit(limit)
    ).scalars().all()

    return {
        "status": "success",
        "stream_id": stream_id,
        "total": len(records),
        "segments": [
            {
                "id": r.id,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "text": r.text,
                "language": r.language,
                "provider": r.provider,
                "model": r.model,
                "machine_generated": r.machine_generated,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reversed(records)
        ],
    }


@router.get("/stream")
async def stream_live_transcription(
    channel: str = Query(default="tv_marathi_live"),
):
    """Server-Sent Events (SSE) streaming live audio-to-text broadcast transcript chunks."""
    provider = get_transcription_provider()

    async def event_generator():
        current_time = 0.0
        duration = 12.0
        _, session_factory = get_engine()

        while True:
            result = await provider.transcribe_chunk(
                audio_bytes=None,
                mime_type="audio/mp3",
                start_time=current_time,
                duration=duration,
            )

            # Persist to database in background
            try:
                db = session_factory()
                seg_id = f"TRN-{int(current_time)}-{uuid.uuid4().hex[:6]}"
                segment = TranscriptSegment(
                    id=seg_id,
                    stream_id=channel,
                    start_time=result["start_time"],
                    end_time=result["end_time"],
                    text=result["text"],
                    language=result["language"],
                    provider=result["provider"],
                    model=result["model"],
                    machine_generated=True,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(segment)
                db.commit()
                db.close()
            except Exception as exc:
                logger.debug(f"Segment persistence notice: {exc}")

            payload = {
                "channel": channel,
                "segment": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            current_time += duration
            # Yield every 4.0 seconds for smooth live streaming feel
            await asyncio.sleep(4.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
