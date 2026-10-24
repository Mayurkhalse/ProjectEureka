"""Live Audio-to-Text Transcription Service for Project EUREKA.

Features:
- Provider Interface: TranscriptionProvider
- GeminiAudioProvider: sends 10-15s audio chunks to Gemini API (GEMINI_TRANSCRIBE_MODEL)
  using the main GEMINI_API_KEY. Target language: Marathi (Devanagari) with English fallback.
- DemoProvider: deterministic pre-seeded Marathi broadcast transcript chunks with monotonic timestamps.
- Provider Factory: selects GeminiAudioProvider when GEMINI_API_KEY is present and valid,
  otherwise DemoProvider for zero-configuration, 100% reliable offline/demo operation.
"""

import abc
import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from eureka.core.config import get_settings

logger = logging.getLogger("eureka.transcription")
settings = get_settings()

# Canonical Marathi broadcast sample segments
DEMO_BROADCAST_TRANSCRIPTS = [
    {
        "text": "सह्याद्री अतिथीगृह येथे मुख्यमंत्री महोदयांच्या अध्यक्षतेखाली राज्य आपत्ती निवारण व पूर्वतयारी बैठक संपन्न.",
        "language": "mr",
    },
    {
        "text": "मराठवाडा आणि विदर्भातील ग्रामीण पाणीपुरवठा व जलसंधारण कामांसाठी ५५० कोटी रुपयांचा निधी तातडीने मंजूर.",
        "language": "mr",
    },
    {
        "text": "Chief Minister directs all District Collectors to maintain strict 90-minute SLA resolution for civic emergencies.",
        "language": "en",
    },
    {
        "text": "पुणे-नाशिक औद्योगिक कॉरिडॉर आणि रस्ते रुंदीकरण कामांचा उपमुख्यमंत्री महोदयांकडून उच्चस्तरीय सविस्तर आढावा.",
        "language": "mr",
    },
    {
        "text": "कोकण किनारपट्टी भागात पर्यटनाला चालना देण्यासाठी नवीन शाश्वत इको-टुरिझम विकास आराखडा जाहीर.",
        "language": "mr",
    },
    {
        "text": "राज्य माहिती कक्षाकडून समाजमाध्यमांवरील दिशाभूल करणाऱ्या खोट्या बातम्या व अफवांचे तात्काळ अधिकृत खंडन प्रसिद्ध.",
        "language": "mr",
    },
    {
        "text": "DGIPR Maha-Command Center actively tracks government scheme hoardings and display boards across all 36 districts.",
        "language": "en",
    },
    {
        "text": "ठाणे, पालघर व रायगड जिल्ह्यातील ग्रामीण प्राथमिक आरोग्य केंद्रांमध्ये २४ तास औषधोपचार सेवा सुरू ठेवण्याचे निर्देश.",
        "language": "mr",
    },
    {
        "text": "कृषी उत्पन्न बाजार समितीमध्ये डिजिटल पेमेंट प्रणालीद्वारे शेतकऱ्यांच्या थेट बँक खात्यात खरीप अनुदानाची रक्कम वर्ग.",
        "language": "mr",
    },
    {
        "text": "सर्व जिल्हा माहिती अधिकाऱ्यांना शासकीय जनकल्याणकारी योजनांची खरी माहिती शेवटच्या घटकापर्यंत पोहोचवण्याचे आवाहन.",
        "language": "mr",
    },
    {
        "text": "Maha Mumbai Metro and Coastal Road connectivity projects reviewed for Phase-2 commissioning timeline.",
        "language": "en",
    },
    {
        "text": "जिल्हास्तरीय संनियंत्रण कक्षाकडून वृत्तपत्रीय कात्रणे आणि टीव्ही वृत्तवाहिन्यांवरील विश्लेषणाची नोंद सुरू.",
        "language": "mr",
    },
]


class TranscriptionProvider(abc.ABC):
    """Abstract base class for audio transcription providers."""

    @abc.abstractmethod
    async def transcribe_chunk(
        self,
        audio_bytes: Optional[bytes] = None,
        mime_type: str = "audio/mp3",
        start_time: float = 0.0,
        duration: float = 12.0,
    ) -> Dict[str, Any]:
        """Transcribe an audio chunk of 10 to 15 seconds.

        Returns:
            Dict containing: start_time, end_time, text, language, provider, model, machine_generated
        """
        pass


class DemoProvider(TranscriptionProvider):
    """Deterministic pre-seeded provider for demo and offline test environments."""

    def __init__(self, model_name: str = "demo-marathi-v1"):
        self.model_name = model_name

    async def transcribe_chunk(
        self,
        audio_bytes: Optional[bytes] = None,
        mime_type: str = "audio/mp3",
        start_time: float = 0.0,
        duration: float = 12.0,
    ) -> Dict[str, Any]:
        # Deterministically select segment based on start_time offset
        idx = int(start_time / max(duration, 1.0)) % len(DEMO_BROADCAST_TRANSCRIPTS)
        sample = DEMO_BROADCAST_TRANSCRIPTS[idx]

        return {
            "start_time": round(start_time, 2),
            "end_time": round(start_time + duration, 2),
            "text": sample["text"],
            "language": sample["language"],
            "provider": "demo",
            "model": self.model_name,
            "machine_generated": True,
        }


class GeminiAudioProvider(TranscriptionProvider):
    """Google Gemini Audio Transcription Provider using main GEMINI_API_KEY."""

    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model_name = model_name or settings.GEMINI_TRANSCRIBE_MODEL or "gemini-2.0-flash"
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        )
        self.fallback = DemoProvider(model_name="demo-fallback")

    async def transcribe_chunk(
        self,
        audio_bytes: Optional[bytes] = None,
        mime_type: str = "audio/mp3",
        start_time: float = 0.0,
        duration: float = 12.0,
    ) -> Dict[str, Any]:
        if not audio_bytes or len(audio_bytes) < 100:
            # If no raw audio supplied in mock/stream mode, delegate to fallback
            return await self.fallback.transcribe_chunk(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                start_time=start_time,
                duration=duration,
            )

        try:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": b64_audio,
                                }
                            },
                            {
                                "text": (
                                    "Transcribe this audio clip accurately. If the speech is in Marathi, "
                                    "output in Marathi Devanagari script. If in English, output in English. "
                                    "Return JSON with keys 'text' (the transcript) and 'language' ('mr' or 'en')."
                                )
                            },
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            }

            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(
                    self.endpoint,
                    params={"key": self.api_key},
                    json=payload,
                )

                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_part = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = json.loads(text_part) if text_part.strip().startswith("{") else {}
                        transcribed_text = parsed.get("text") or text_part.strip()
                        language = parsed.get("language") or ("mr" if any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in transcribed_text) else "en")

                        return {
                            "start_time": round(start_time, 2),
                            "end_time": round(start_time + duration, 2),
                            "text": transcribed_text,
                            "language": language,
                            "provider": "gemini",
                            "model": self.model_name,
                            "machine_generated": True,
                        }

                logger.warning(f"Gemini API returned {res.status_code}: {res.text}. Using fallback.")
        except Exception as exc:
            logger.warning(f"Gemini transcription failed ({exc}). Using demo fallback.")

        # Fallback to demo provider on API error
        result = await self.fallback.transcribe_chunk(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            start_time=start_time,
            duration=duration,
        )
        result["provider"] = "gemini_fallback_demo"
        return result


def get_transcription_provider() -> TranscriptionProvider:
    """Factory selecting GeminiAudioProvider when API key is configured, else DemoProvider."""
    gemini_key = (
        settings.GEMINI_API_KEY
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_STUDIO_API_KEY")
    )

    if gemini_key and len(gemini_key.strip()) > 10:
        logger.info("Initializing GeminiAudioProvider with configured API key.")
        return GeminiAudioProvider(api_key=gemini_key.strip())

    logger.info("No Gemini key configured. Initializing DemoProvider.")
    return DemoProvider()
