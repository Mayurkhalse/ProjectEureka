"""Unit and integration tests for the Audio-to-Text Transcription pipeline."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from eureka.api.main import app
from eureka.services.transcription import (
    DemoProvider,
    GeminiAudioProvider,
    get_transcription_provider,
)

client = TestClient(app)


@pytest.mark.asyncio
async def test_demo_provider_monotonic_timestamps():
    """Verify DemoProvider produces monotonic timestamps and machine_generated flag."""
    provider = DemoProvider()

    prev_end = 0.0
    for i in range(5):
        start = float(i * 12)
        chunk = await provider.transcribe_chunk(start_time=start, duration=12.0)

        assert chunk["start_time"] == start
        assert chunk["end_time"] == start + 12.0
        assert chunk["start_time"] >= prev_end
        assert chunk["machine_generated"] is True
        assert chunk["language"] in ("mr", "en")
        assert len(chunk["text"]) > 0
        prev_end = chunk["end_time"]


@pytest.mark.asyncio
async def test_gemini_audio_provider_mocked_response():
    """Mock Gemini API response and assert Marathi text is parsed with machine_generated=True."""
    mock_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"text": "मुख्यमंत्री महोदयांनी जलसंधारण कामांना गती देण्याचे आदेश दिले.", "language": "mr"}'
                        }
                    ]
                }
            }
        ]
    }

    provider = GeminiAudioProvider(api_key="fake-key-for-test", model_name="gemini-2.0-flash")

    # Mock httpx response
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: mock_gemini_response
        mock_post.return_value = mock_response

        # Supply dummy audio bytes (> 100 bytes to trigger API call)
        dummy_audio = b"\x00" * 256
        result = await provider.transcribe_chunk(
            audio_bytes=dummy_audio,
            mime_type="audio/mp3",
            start_time=24.0,
            duration=12.0,
        )

        assert result["start_time"] == 24.0
        assert result["end_time"] == 36.0
        assert result["language"] == "mr"
        assert "जलसंधारण" in result["text"]
        assert result["provider"] == "gemini"
        assert result["machine_generated"] is True


def test_transcription_chunk_endpoint():
    """Verify POST /api/v1/transcription/chunk endpoint persists and returns segment."""
    response = client.post(
        "/api/v1/transcription/chunk",
        json={
            "stream_id": "test_broadcast_stream",
            "start_time": 48.0,
            "duration": 12.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "segment_id" in data
    seg = data["segment"]
    assert seg["start_time"] == 48.0
    assert seg["end_time"] == 60.0
    assert seg["machine_generated"] is True


def test_transcription_history_endpoint():
    """Verify GET /api/v1/transcription/history endpoint returns persisted segments."""
    response = client.get("/api/v1/transcription/history?stream_id=test_broadcast_stream&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "segments" in data
    assert isinstance(data["segments"], list)
