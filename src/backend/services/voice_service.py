from abc import ABC, abstractmethod
import logging
import os
from typing import Set
from google import genai
from google.genai import types
from backend.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_MIMES: Set[str] = {
    "audio/mp3",
    "audio/mpeg",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/aac",
    "audio/flac",
}

MAX_AUDIO_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB limit for mobile voice notes


class VoiceTranscriptionError(Exception):
    """Raised when an audio file cannot be validated or transcribed."""


class IVoiceTranscriber(ABC):
    """Strategy interface for transcribing voice memos into clean text."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        pass


class GeminiVoiceTranscriber(IVoiceTranscriber):
    """
    Speech-to-Text transcription powered by Google Gemini 2.5 Flash multimodal audio understanding.
    Removes speech disfluencies (ums, uhs) while preserving exact context, nuance, and intent.
    """

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        clean_mime = mime_type.lower().split(";")[0].strip()
        # Normalize m4a / mp4 audio
        if clean_mime in ("audio/x-m4a", "audio/m4a"):
            clean_mime = "audio/mp4"

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=clean_mime)

        prompt = (
            "You are an expert audio transcription model for modern business founders and creators.\n"
            "Transcribe the spoken audio with exact fidelity, applying natural punctuation, proper capitalization, "
            "and paragraph spacing.\n"
            "Remove speech disfluencies and filler words (e.g. 'um', 'uh', 'you know', repeated stutters) "
            "while faithfully preserving all key concepts, numbers, product details, names, and the speaker's natural tone.\n"
            "Output ONLY the final clean transcription with zero conversational preamble, metadata, or markdown formatting."
        )

        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[audio_part, prompt],
            )
            text = (response.text or "").strip()
            if not text:
                raise VoiceTranscriptionError("Audio transcription returned an empty result.")
            return text
        except Exception as exc:
            logger.error("Gemini audio transcription failed: %s", exc)
            raise VoiceTranscriptionError(f"Speech transcription failed: {exc}") from exc


class FallbackVoiceTranscriber(IVoiceTranscriber):
    """
    Development fallback transcriber used when GEMINI_API_KEY is not configured.
    Allows frontend developers to record and test the full voice-to-post flow immediately.
    """

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        size_kb = len(audio_bytes) // 1024
        logger.info("[Dev Voice] Generating fallback transcript for %s (%d KB)", mime_type, size_kb)
        return (
            "We are officially launching our new collection this Friday! "
            "Every single piece has been designed for maximum comfort and durability without cutting corners on style. "
            "To celebrate launch week, early supporters get 20% off. "
            "We cannot wait for you to experience what we have been building behind the scenes."
        )


class VoiceTranscriberFactory:
    """Factory resolving the active IVoiceTranscriber implementation."""

    @classmethod
    def get_transcriber(cls) -> IVoiceTranscriber:
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if api_key:
            return GeminiVoiceTranscriber(api_key=api_key)
        return FallbackVoiceTranscriber()
