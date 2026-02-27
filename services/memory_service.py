"""
vocal-agent-fr-live — Memory Service.

Wraps mem0 for persistent conversational memory.
Provides per-user memory storage, retrieval, and emotional state tracking.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import app_config

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages persistent conversational memory using mem0.

    Stores user preferences, facts, and emotional states across sessions.
    Retrieves relevant memories to inject into LLM context.
    """

    def __init__(self, storage_path: str | None = None, enabled: bool | None = None):
        self._storage_path = storage_path or app_config.mem0_storage_path
        self._enabled = enabled if enabled is not None else app_config.mem0_enabled
        self._memory = None

        if self._enabled:
            self._init_mem0()

    def _init_mem0(self):
        """Initialize mem0 memory instance."""
        try:
            from mem0 import Memory

            config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "vocal_agent_memories",
                        "path": self._storage_path,
                    },
                },
            }

            self._memory = Memory.from_config(config)
            logger.info("mem0 memory initialized at: %s", self._storage_path)

        except ImportError:
            logger.warning(
                "mem0 not installed. Memory features disabled. "
                "Install with: pip install mem0ai"
            )
            self._enabled = False
        except Exception as e:
            logger.error("Failed to initialize mem0: %s", e)
            self._enabled = False

    async def add_memory(
        self,
        message: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a conversation exchange in memory.

        Args:
            message: The message content to memorize.
            user_id: User identifier for per-user memory.
            metadata: Optional metadata (e.g., emotional state, topic).
        """
        if not self._enabled or self._memory is None:
            return

        def _add():
            try:
                self._memory.add(
                    message,
                    user_id=user_id,
                    metadata=metadata or {},
                )
                logger.debug("Memory stored for user %s", user_id)
            except Exception as e:
                logger.error("Failed to store memory: %s", e)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _add)

    async def add_conversation(
        self,
        user_message: str,
        assistant_message: str,
        user_id: str,
    ) -> None:
        """Store a full conversation turn (user + assistant) in memory.

        Args:
            user_message: What the user said.
            assistant_message: What the assistant replied.
            user_id: User identifier.
        """
        if not self._enabled or self._memory is None:
            return

        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ]

        def _add():
            try:
                self._memory.add(
                    messages,
                    user_id=user_id,
                )
                logger.debug("Conversation turn stored for user %s", user_id)
            except Exception as e:
                logger.error("Failed to store conversation: %s", e)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _add)

    async def get_relevant_memories(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
    ) -> str:
        """Retrieve relevant memories for context injection.

        Args:
            query: The current user message to find relevant memories for.
            user_id: User identifier.
            limit: Maximum number of memories to retrieve.

        Returns:
            Formatted string of relevant memories for LLM context injection.
        """
        if not self._enabled or self._memory is None:
            return ""

        def _search():
            try:
                results = self._memory.search(
                    query=query,
                    user_id=user_id,
                    limit=limit,
                )
                return results
            except Exception as e:
                logger.error("Failed to search memories: %s", e)
                return []

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _search)

        if not results:
            return ""

        # Format memories for LLM context
        memory_lines = []
        for i, result in enumerate(results, 1):
            if isinstance(result, dict):
                memory_text = result.get("memory", result.get("text", str(result)))
            else:
                memory_text = str(result)
            memory_lines.append(f"- {memory_text}")

        context = "\n".join(memory_lines)
        logger.debug(
            "Retrieved %d memories for user %s:\n%s",
            len(memory_lines),
            user_id,
            context,
        )
        return context

    async def get_all_memories(self, user_id: str) -> list[dict[str, Any]]:
        """Get all stored memories for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of memory entries.
        """
        if not self._enabled or self._memory is None:
            return []

        def _get_all():
            try:
                return self._memory.get_all(user_id=user_id)
            except Exception as e:
                logger.error("Failed to get all memories: %s", e)
                return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_all)

    async def clear_user_memories(self, user_id: str) -> None:
        """Clear all memories for a specific user.

        Args:
            user_id: User identifier.
        """
        if not self._enabled or self._memory is None:
            return

        def _clear():
            try:
                self._memory.delete_all(user_id=user_id)
                logger.info("Cleared all memories for user %s", user_id)
            except Exception as e:
                logger.error("Failed to clear memories: %s", e)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _clear)

    @property
    def is_enabled(self) -> bool:
        """Whether memory features are active."""
        return self._enabled
