"""Whisper transcription — Phase 4.6."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form

from app.api.deps import verify_api_key
from app.providers.whisper_provider import WhisperProvider

router = APIRouter()


@router.post("/transcriptions")
async def transcribe_audio(
    file: UploadFile,
    model: str = Form(default="Systran/faster-whisper-large-v3"),
    language: str | None = Form(default=None),
    response_format: str = Form(default="json"),
    temperature: float = Form(default=0.0),
    _=Depends(verify_api_key),
):
    """Transcribe audio via Whisper provider."""
    whisper = WhisperProvider()
    payload = {
        "model": model,
        "response_format": response_format,
        "temperature": str(temperature),
    }
    if language:
        payload["language"] = language

    try:
        result = await whisper.forward_request(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Whisper unavailable: {e}")
