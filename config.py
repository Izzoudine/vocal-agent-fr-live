"""
vocal-agent-fr-live — Configuration module.

Defines SessionConfig (per-session dynamic parameters) and AppConfig (global app settings).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Session-level configuration (dynamic, per WebSocket connection)
# ---------------------------------------------------------------------------

@dataclass
class SessionConfig:
    """Configuration for a single voice agent session.

    These parameters can be set via the /start-session endpoint
    or updated dynamically via WebSocket `session.update` messages.
    """

    voice_id: str = os.getenv("TTS_VOICE_ID", "fr_FR-melo-voice1")
    personality: str = (
        "Tu es un assistant vocal intelligent, chaleureux et naturel. "
        "Tu parles avec un ton décontracté, amical et engageant. "
        "Tu utilises des expressions naturelles du français parlé."
    )
    situation: str = (
        "Tu es dans une conversation vocale en temps réel. "
        "Réponds de manière concise et naturelle, comme dans une vraie discussion."
    )
    language: str = "fr-FR"
    tts_engine: Literal["melo", "chatterbox"] = os.getenv("TTS_ENGINE", "melo")
    tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))
    emotion_exaggeration: float = float(os.getenv("TTS_EMOTION_EXAGGERATION", "0.5"))
    user_id: str = "default"

    def build_system_prompt(self) -> str:
        """Construct the full system prompt injected into the LLM.

        Combines personality, situation context, and conversational directives
        into a single coherent prompt.
        """
        return (
            f"Tu es {self.personality}\n\n"
            f"La situation actuelle est : {self.situation}\n\n"
            "Instructions importantes :\n"
            "- Parle TOUJOURS en français naturel et décontracté.\n"
            "- Utilise un ton conversationnel, comme si tu parlais à un ami.\n"
            "- Tes réponses doivent être CONCISES (2-3 phrases max) car elles seront "
            "prononcées à voix haute.\n"
            "- Tu peux utiliser des expressions familières, des interjections "
            "(ah, oh, ben, euh, etc.).\n"
            "- N'utilise JAMAIS de markdown, de listes à puces, ou de formatage texte.\n"
            "- N'utilise JAMAIS d'émojis.\n"
            "- Si l'utilisateur t'interrompt, arrête-toi et réponds à sa nouvelle question.\n"
            "- Sois expressif et montre des émotions dans tes réponses.\n"
        )


# ---------------------------------------------------------------------------
# Application-level configuration (global, from environment)
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """Global application configuration loaded from environment variables."""

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8765"))

    # Ollama / LLM
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-v0.3-q4_0")

    # STT
    stt_model_size: str = os.getenv("STT_MODEL_SIZE", "small")
    stt_language: str = os.getenv("STT_LANGUAGE", "fr")
    stt_device: str = os.getenv("STT_DEVICE", "cpu")
    stt_compute_type: str = os.getenv("STT_COMPUTE_TYPE", "int8")

    # TTS
    tts_engine: str = os.getenv("TTS_ENGINE", "melo")
    tts_voice_id: str = os.getenv("TTS_VOICE_ID", "fr_FR-melo-voice1")
    tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))
    tts_emotion_exaggeration: float = float(os.getenv("TTS_EMOTION_EXAGGERATION", "0.5"))

    # Memory
    mem0_enabled: bool = os.getenv("MEM0_ENABLED", "true").lower() == "true"
    mem0_storage_path: str = os.getenv("MEM0_STORAGE_PATH", "./data/mem0")

    # Security
    cors_origins: list[str] = field(default_factory=lambda: [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    ])
    api_key: str | None = os.getenv("API_KEY") or None
    rate_limit: str = os.getenv("RATE_LIMIT", "60/minute")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


# Singleton instances
app_config = AppConfig()
