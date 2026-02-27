"""
vocal-agent-fr-live — STT Service.

Custom STT service wrapping faster-whisper for French speech recognition.
Supports configurable model sizes and CPU/GPU inference.
Uses lazy model loading (models load on first use).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from config import app_config

logger = logging.getLogger(__name__)


class FasterWhisperSTTService:
    """STT service using faster-whisper.

    Loads a Whisper model optimized for French transcription.
    Models are loaded lazily on first transcription request.
    """

    def __init__(
        self,
        model_size: str | None = None,
        language: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ):
        self._model_size = model_size or app_config.stt_model_size
        self._language = language or app_config.stt_language
        self._device = device or app_config.stt_device
        self._compute_type = compute_type or app_config.stt_compute_type
        self._model = None
        self._loading = False
        self._sample_rate = 16000  # Whisper expects 16kHz mono

        logger.info(
            "FasterWhisperSTT: model=%s, device=%s, compute=%s, lang=%s",
            self._model_size,
            self._device,
            self._compute_type,
            self._language,
        )

    async def _ensure_model_loaded(self):
        """Lazy-load the Whisper model on first use."""
        if self._model is not None:
            return
        if self._loading:
            while self._loading:
                await asyncio.sleep(0.5)
            return

        self._loading = True
        try:
            await self._load_model()
        finally:
            self._loading = False

    async def _load_model(self):
        """Load the faster-whisper model in a background thread."""

        def _load():
            from faster_whisper import WhisperModel

            logger.info("Loading faster-whisper model: %s ...", self._model_size)
            model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("faster-whisper model loaded successfully.")
            return model

        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(None, _load)

    async def run_stt(self, audio: bytes) -> str:
        """Transcribe audio bytes using faster-whisper.

        Args:
            audio: Raw PCM audio data (16-bit, 16kHz, mono).

        Returns:
            Transcribed text string.
        """
        await self._ensure_model_loaded()

        if self._model is None:
            logger.error("STT model could not be loaded!")
            return ""

        def _transcribe(audio_data: bytes) -> str:
            # Convert raw PCM bytes to numpy float32 array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            if len(audio_np) == 0:
                return ""

            segments, info = self._model.transcribe(
                audio_np,
                language=self._language,
                beam_size=5,
                best_of=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=300,
                ),
                without_timestamps=True,
                condition_on_previous_text=True,
            )

            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            full_text = " ".join(text_parts).strip()
            if full_text:
                logger.debug("STT transcription: %s", full_text)
            return full_text

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _transcribe, audio)
