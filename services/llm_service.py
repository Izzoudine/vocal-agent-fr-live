"""
vocal-agent-fr-live — LLM Service.

Configures and wraps Pipecat's OLLamaLLMService for French conversational AI.
Handles dynamic system prompt injection and conversation history management.
"""

from __future__ import annotations

import logging
from typing import Any

from pipecat.services.ollama import OLLamaLLMService

from config import AppConfig, SessionConfig, app_config

logger = logging.getLogger(__name__)


def create_ollama_service(
    session_config: SessionConfig,
    config: AppConfig | None = None,
) -> OLLamaLLMService:
    """Create and configure an OLLama LLM service for a session.

    Args:
        session_config: Per-session configuration with personality/situation.
        config: Global app config (defaults to singleton).

    Returns:
        Configured OLLamaLLMService instance.
    """
    cfg = config or app_config

    system_prompt = session_config.build_system_prompt()

    logger.info(
        "Creating Ollama LLM service: model=%s, host=%s",
        cfg.ollama_model,
        cfg.ollama_host,
    )
    logger.debug("System prompt:\n%s", system_prompt)

    service = OLLamaLLMService(
        model=cfg.ollama_model,
        base_url=cfg.ollama_host,
    )

    return service


def build_initial_messages(session_config: SessionConfig) -> list[dict[str, str]]:
    """Build the initial message list with system prompt for the LLM.

    Args:
        session_config: Session configuration.

    Returns:
        List of message dicts suitable for the LLM conversation.
    """
    return [
        {
            "role": "system",
            "content": session_config.build_system_prompt(),
        },
    ]


class ConversationManager:
    """Manages conversation history for a session.

    Keeps a rolling window of messages to stay within context limits
    while preserving the system prompt.
    """

    MAX_HISTORY_MESSAGES = 20  # Keep last N user+assistant turns

    def __init__(self, session_config: SessionConfig):
        self.session_config = session_config
        self._messages: list[dict[str, str]] = build_initial_messages(session_config)

    @property
    def messages(self) -> list[dict[str, str]]:
        """Current conversation messages."""
        return self._messages

    def add_user_message(self, text: str) -> None:
        """Add a user message to the conversation."""
        self._messages.append({"role": "user", "content": text})
        self._trim_history()

    def add_assistant_message(self, text: str) -> None:
        """Add an assistant message to the conversation."""
        self._messages.append({"role": "assistant", "content": text})
        self._trim_history()

    def inject_memory_context(self, memory_context: str) -> None:
        """Inject memory context into the system prompt.

        Updates the system prompt to include relevant memory information
        retrieved from mem0.
        """
        base_prompt = self.session_config.build_system_prompt()
        enhanced_prompt = (
            f"{base_prompt}\n\n"
            f"Contexte mémorisé sur l'utilisateur :\n{memory_context}\n"
            "Utilise ces informations de manière naturelle dans la conversation, "
            "sans les répéter mot pour mot."
        )
        # Update the system message (always first)
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = enhanced_prompt
        else:
            self._messages.insert(0, {"role": "system", "content": enhanced_prompt})

    def update_session_config(self, new_config: SessionConfig) -> None:
        """Update session config and refresh the system prompt."""
        self.session_config = new_config
        base_prompt = new_config.build_system_prompt()
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = base_prompt
        else:
            self._messages.insert(0, {"role": "system", "content": base_prompt})

    def _trim_history(self) -> None:
        """Keep conversation history within the maximum window."""
        # Always keep system prompt (index 0) + last N messages
        if len(self._messages) > self.MAX_HISTORY_MESSAGES + 1:
            system_msg = self._messages[0]
            recent = self._messages[-(self.MAX_HISTORY_MESSAGES):]
            self._messages = [system_msg] + recent

    def clear(self) -> None:
        """Clear conversation history, keeping the system prompt."""
        self._messages = build_initial_messages(self.session_config)
