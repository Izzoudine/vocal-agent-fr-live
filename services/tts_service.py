"""
vocal-agent-fr-live — TTS Service.

Custom Pipecat TTS services for MeloTTS (primary) and Chatterbox (fallback).
Supports voice ID selection, streaming chunk-by-chunk synthesis, and emotion control.
"""

from __future__ import annotations

import asyncio
import io
import logging
import struct
from typing import Any, AsyncGenerator

import numpy as np
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.ai_services import TTSService

from config import app_config

logger = logging.getLogger(__name__)

# Default TTS output audio parameters
TTS_SAMPLE_RATE = 24000  # MeloTTS outputs 24kHz
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH = 2  # 16-bit PCM


class MeloTTSService(TTSService):
    """Custom Pipecat TTS service using MeloTTS for French synthesis.

    MeloTTS provides high-quality, real-time French speech synthesis
    that runs efficiently on CPU.
    """

    def __init__(
        self,
        voice_id: str = "fr_FR-melo-voice1",
        speed: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(sample_rate=TTS_SAMPLE_RATE, **kwargs)
        self._voice_id = voice_id
        self._speed = speed
        self._model = None
        self._speaker_ids: dict[str, int] | None = None

        logger.info("MeloTTS: voice_id=%s, speed=%.1f", voice_id, speed)

    async def start(self, frame: Frame):
        """Initialize MeloTTS model on service start."""
        await super().start(frame)
        await self._load_model()

    async def _load_model(self):
        """Load MeloTTS model in a background thread."""

        def _load():
            try:
                from melo.api import TTS as MeloTTS

                logger.info("Loading MeloTTS French model...")
                model = MeloTTS(language="FR", device="auto")
                speaker_ids = model.hps.data.spk2id
                logger.info(
                    "MeloTTS loaded. Available speakers: %s",
                    list(speaker_ids.keys()),
                )
                return model, speaker_ids
            except ImportError:
                logger.error(
                    "MeloTTS not installed. Install with: pip install MeloTTS"
                )
                raise
            except Exception as e:
                logger.error("Failed to load MeloTTS: %s", e)
                raise

        loop = asyncio.get_event_loop()
        self._model, self._speaker_ids = await loop.run_in_executor(None, _load)

    def _resolve_speaker_id(self) -> int:
        """Resolve the voice_id to a MeloTTS speaker ID."""
        if self._speaker_ids is None:
            return 0

        # Try exact match first
        if self._voice_id in self._speaker_ids:
            return self._speaker_ids[self._voice_id]

        # Try matching by suffix (e.g., "voice1" → first speaker)
        for key, sid in self._speaker_ids.items():
            if self._voice_id.lower() in key.lower():
                return sid

        # Default to first speaker
        logger.warning(
            "Voice ID '%s' not found. Using default. Available: %s",
            self._voice_id,
            list(self._speaker_ids.keys()),
        )
        return list(self._speaker_ids.values())[0]

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Synthesize text to speech using MeloTTS.

        Yields TTSAudioRawFrame chunks for streaming playback.
        """
        yield TTSStartedFrame()

        try:
            audio_data = await self._synthesize(text)

            if audio_data is not None and len(audio_data) > 0:
                # Convert to bytes and send in chunks for streaming
                chunk_size = TTS_SAMPLE_RATE  # ~1 second chunks
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i : i + chunk_size]
                    # Convert float32 to int16 PCM
                    pcm_chunk = (chunk * 32767).astype(np.int16).tobytes()
                    yield TTSAudioRawFrame(
                        audio=pcm_chunk,
                        sample_rate=TTS_SAMPLE_RATE,
                        num_channels=TTS_CHANNELS,
                    )

        except Exception as e:
            logger.error("MeloTTS synthesis error: %s", e)
            yield ErrorFrame(f"TTS error: {e}")

        yield TTSStoppedFrame()

    async def _synthesize(self, text: str) -> np.ndarray | None:
        """Run MeloTTS synthesis in a background thread."""
        if self._model is None:
            logger.error("MeloTTS model not loaded!")
            return None

        def _synth():
            speaker_id = self._resolve_speaker_id()
            audio = self._model.tts_to_file(
                text,
                speaker_id,
                quiet=True,
                speed=self._speed,
            )
            return np.array(audio, dtype=np.float32)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _synth)


class ChatterboxTTSService(TTSService):
    """Custom Pipecat TTS service using Chatterbox for expressive French synthesis.

    Chatterbox provides emotion-controllable TTS with zero-shot voice cloning.
    Used as fallback when more expressiveness is needed.
    """

    CHATTERBOX_SAMPLE_RATE = 24000

    def __init__(
        self,
        voice_id: str = "default",
        emotion_exaggeration: float = 0.5,
        reference_audio_path: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(sample_rate=self.CHATTERBOX_SAMPLE_RATE, **kwargs)
        self._voice_id = voice_id
        self._emotion_exaggeration = emotion_exaggeration
        self._reference_audio_path = reference_audio_path
        self._model = None

        logger.info(
            "ChatterboxTTS: voice_id=%s, emotion=%.2f",
            voice_id,
            emotion_exaggeration,
        )

    async def start(self, frame: Frame):
        """Initialize Chatterbox model on service start."""
        await super().start(frame)
        await self._load_model()

    async def _load_model(self):
        """Load Chatterbox model in a background thread."""

        def _load():
            try:
                from chatterbox.tts import ChatterboxTTS

                logger.info("Loading Chatterbox TTS model...")
                model = ChatterboxTTS.from_pretrained(device="cpu")
                logger.info("Chatterbox TTS loaded successfully.")
                return model
            except ImportError:
                logger.error(
                    "Chatterbox not installed. Install with: pip install chatterbox-tts"
                )
                raise
            except Exception as e:
                logger.error("Failed to load Chatterbox: %s", e)
                raise

        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(None, _load)

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Synthesize text with Chatterbox TTS.

        Yields TTSAudioRawFrame chunks for streaming playback.
        """
        yield TTSStartedFrame()

        try:
            audio_data = await self._synthesize(text)

            if audio_data is not None and len(audio_data) > 0:
                chunk_size = self.CHATTERBOX_SAMPLE_RATE
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i : i + chunk_size]
                    pcm_chunk = (chunk * 32767).astype(np.int16).tobytes()
                    yield TTSAudioRawFrame(
                        audio=pcm_chunk,
                        sample_rate=self.CHATTERBOX_SAMPLE_RATE,
                        num_channels=TTS_CHANNELS,
                    )

        except Exception as e:
            logger.error("Chatterbox synthesis error: %s", e)
            yield ErrorFrame(f"TTS error: {e}")

        yield TTSStoppedFrame()

    async def _synthesize(self, text: str) -> np.ndarray | None:
        """Run Chatterbox synthesis in a background thread."""
        if self._model is None:
            logger.error("Chatterbox model not loaded!")
            return None

        def _synth():
            wav = self._model.generate(
                text,
                audio_prompt_path=self._reference_audio_path,
                exaggeration=self._emotion_exaggeration,
            )
            return wav.squeeze().cpu().numpy().astype(np.float32)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _synth)


def create_tts_service(
    engine: str = "melo",
    voice_id: str = "fr_FR-melo-voice1",
    speed: float = 1.0,
    emotion_exaggeration: float = 0.5,
    reference_audio_path: str | None = None,
) -> TTSService:
    """Factory function to create the appropriate TTS service.

    Args:
        engine: "melo" or "chatterbox"
        voice_id: Voice identifier string
        speed: Speech speed (MeloTTS only)
        emotion_exaggeration: Emotion level 0.0-1.0 (Chatterbox only)
        reference_audio_path: Path to reference audio for voice cloning (Chatterbox only)

    Returns:
        Configured TTS service instance.
    """
    if engine.lower() == "chatterbox":
        logger.info("Creating Chatterbox TTS service")
        return ChatterboxTTSService(
            voice_id=voice_id,
            emotion_exaggeration=emotion_exaggeration,
            reference_audio_path=reference_audio_path,
        )
    else:
        logger.info("Creating MeloTTS service")
        return MeloTTSService(
            voice_id=voice_id,
            speed=speed,
        )
