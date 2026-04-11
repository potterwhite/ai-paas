#
# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
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
