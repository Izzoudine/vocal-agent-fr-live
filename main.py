"""
vocal-agent-fr-live — Main Application.

FastAPI server with WebSocket endpoint for real-time speech-to-speech
voice agent in French. Orchestrates Pipecat pipeline: STT → LLM → TTS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import AppConfig, SessionConfig, app_config
from services.llm_service import ConversationManager, create_ollama_service
from services.memory_service import MemoryManager
from services.stt_service import FasterWhisperSTTService
from services.tts_service import create_tts_service

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, app_config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vocal-agent")

# ---------------------------------------------------------------------------
# Session Storage
# ---------------------------------------------------------------------------

active_sessions: dict[str, dict[str, Any]] = {}
memory_manager = MemoryManager()

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    """Request body for creating a new voice agent session."""

    voice_id: str = Field(default="fr_FR-melo-voice1", description="TTS voice identifier")
    personality: str = Field(
        default=(
            "Tu es un assistant vocal intelligent, chaleureux et naturel. "
            "Tu parles avec un ton décontracté, amical et engageant."
        ),
        description="Full personality description for the agent",
    )
    situation: str = Field(
        default=(
            "Tu es dans une conversation vocale en temps réel. "
            "Réponds de manière concise et naturelle."
        ),
        description="Current situational context",
    )
    language: str = Field(default="fr-FR", description="Language code")
    tts_engine: str = Field(default="melo", description="TTS engine: 'melo' or 'chatterbox'")
    user_id: str = Field(default="default", description="User identifier for memory")


class StartSessionResponse(BaseModel):
    """Response from creating a new session."""

    session_id: str
    websocket_url: str
    config: dict[str, Any]


class SessionUpdateMessage(BaseModel):
    """WebSocket message for updating session parameters."""

    type: str = "session.update"
    voice_id: str | None = None
    personality: str | None = None
    situation: str | None = None
    tts_engine: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"
    active_sessions: int = 0
    memory_enabled: bool = False


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def verify_api_key(api_key: str | None = Query(None, alias="api_key")):
    """Optional API key verification."""
    if app_config.api_key is None:
        return True  # Auth disabled
    if api_key != app_config.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    rate_limiting_enabled = True
except ImportError:
    limiter = None
    rate_limiting_enabled = False
    logger.warning("slowapi not installed — rate limiting disabled")

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup/shutdown."""
    logger.info("=" * 60)
    logger.info("  vocal-agent-fr-live starting up")
    logger.info("  Host: %s:%s", app_config.host, app_config.port)
    logger.info("  LLM:  %s @ %s", app_config.ollama_model, app_config.ollama_host)
    logger.info("  STT:  faster-whisper (%s)", app_config.stt_model_size)
    logger.info("  TTS:  %s", app_config.tts_engine)
    logger.info("  Mem:  %s", "enabled" if memory_manager.is_enabled else "disabled")
    logger.info("=" * 60)
    yield
    # Shutdown: cleanup sessions
    logger.info("Shutting down — cleaning up %d sessions", len(active_sessions))
    active_sessions.clear()


app = FastAPI(
    title="vocal-agent-fr-live",
    description="Self-hosted live speech-to-speech vocal agent in French",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
if rate_limiting_enabled and limiter is not None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        active_sessions=len(active_sessions),
        memory_enabled=memory_manager.is_enabled,
    )


@app.post("/start-session", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest, _auth: bool = Depends(verify_api_key)):
    """Create a new voice agent session.

    Returns a session_id and WebSocket URL for the client to connect to.
    """
    session_id = str(uuid.uuid4())

    session_config = SessionConfig(
        voice_id=request.voice_id,
        personality=request.personality,
        situation=request.situation,
        language=request.language,
        tts_engine=request.tts_engine,
        user_id=request.user_id,
    )

    active_sessions[session_id] = {
        "config": session_config,
        "conversation": ConversationManager(session_config),
        "created": True,
    }

    logger.info("Session created: %s (voice=%s, tts=%s)", session_id, request.voice_id, request.tts_engine)

    return StartSessionResponse(
        session_id=session_id,
        websocket_url=f"ws://{app_config.host}:{app_config.port}/ws/{session_id}",
        config={
            "voice_id": session_config.voice_id,
            "personality": session_config.personality[:100] + "...",
            "situation": session_config.situation[:100] + "...",
            "language": session_config.language,
            "tts_engine": session_config.tts_engine,
        },
    )


@app.get("/sessions")
async def list_sessions(_auth: bool = Depends(verify_api_key)):
    """List active sessions."""
    return {
        "sessions": [
            {
                "session_id": sid,
                "voice_id": data["config"].voice_id,
                "user_id": data["config"].user_id,
            }
            for sid, data in active_sessions.items()
        ]
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, _auth: bool = Depends(verify_api_key)):
    """Delete a session."""
    if session_id in active_sessions:
        del active_sessions[session_id]
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


# ---------------------------------------------------------------------------
# WebSocket Endpoint — Main Voice Pipeline
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_voice_endpoint(websocket: WebSocket, session_id: str):
    """Main WebSocket endpoint for real-time voice interaction.

    Protocol:
    - Client sends: binary audio frames (PCM 16-bit, 16kHz, mono)
    - Client sends: JSON control messages (session.update, etc.)
    - Server sends: binary audio frames (PCM 16-bit, 24kHz, mono)
    - Server sends: JSON event messages (transcription, response, etc.)
    """
    await websocket.accept()

    # Get or create session
    if session_id not in active_sessions:
        # Create default session if not pre-created via /start-session
        default_config = SessionConfig()
        active_sessions[session_id] = {
            "config": default_config,
            "conversation": ConversationManager(default_config),
            "created": True,
        }
        logger.info("Auto-created session: %s", session_id)

    session = active_sessions[session_id]
    session_config: SessionConfig = session["config"]
    conversation: ConversationManager = session["conversation"]

    logger.info("WebSocket connected: session=%s", session_id)

    # Send connection confirmation
    await websocket.send_json({
        "type": "session.created",
        "session_id": session_id,
        "config": {
            "voice_id": session_config.voice_id,
            "language": session_config.language,
            "tts_engine": session_config.tts_engine,
        },
    })

    # Initialize services
    stt_service = FasterWhisperSTTService()
    llm_service = create_ollama_service(session_config)
    tts_service = create_tts_service(
        engine=session_config.tts_engine,
        voice_id=session_config.voice_id,
        speed=session_config.tts_speed,
        emotion_exaggeration=session_config.emotion_exaggeration,
    )

    # Audio buffer for accumulating input
    audio_buffer = bytearray()
    is_speaking = False
    current_response = ""

    try:
        while True:
            message = await websocket.receive()

            # Handle binary audio data
            if "bytes" in message:
                audio_data = message["bytes"]

                # Accumulate audio
                audio_buffer.extend(audio_data)

                # Process when we have enough audio (~0.5 second at 16kHz, 16-bit mono)
                min_audio_bytes = 8000 * 2  # 0.5 seconds of audio
                if len(audio_buffer) >= min_audio_bytes:
                    # Transcribe
                    transcription = await stt_service.run_stt(bytes(audio_buffer))
                    audio_buffer.clear()

                    if transcription and transcription.strip():
                        logger.info("User said: %s", transcription)

                        # Send transcription event to client
                        await websocket.send_json({
                            "type": "transcription",
                            "text": transcription,
                            "is_final": True,
                        })

                        # Inject memory context if available
                        if memory_manager.is_enabled:
                            memory_context = await memory_manager.get_relevant_memories(
                                query=transcription,
                                user_id=session_config.user_id,
                            )
                            if memory_context:
                                conversation.inject_memory_context(memory_context)

                        # Add user message to conversation
                        conversation.add_user_message(transcription)

                        # Get LLM response
                        await websocket.send_json({
                            "type": "response.start",
                        })

                        try:
                            import ollama as ollama_client

                            response_text = ""
                            stream = ollama_client.chat(
                                model=app_config.ollama_model,
                                messages=conversation.messages,
                                stream=True,
                                options={
                                    "num_predict": 150,  # Keep responses short for voice
                                    "temperature": 0.7,
                                    "top_p": 0.9,
                                },
                            )

                            # Collect full response (for TTS we need complete sentences)
                            for chunk in stream:
                                if "message" in chunk and "content" in chunk["message"]:
                                    token = chunk["message"]["content"]
                                    response_text += token

                            response_text = response_text.strip()

                            if response_text:
                                logger.info("Agent says: %s", response_text)

                                # Send text response to client
                                await websocket.send_json({
                                    "type": "response.text",
                                    "text": response_text,
                                })

                                # Add to conversation history
                                conversation.add_assistant_message(response_text)

                                # Store in memory
                                if memory_manager.is_enabled:
                                    await memory_manager.add_conversation(
                                        user_message=transcription,
                                        assistant_message=response_text,
                                        user_id=session_config.user_id,
                                    )

                                # Synthesize speech
                                await websocket.send_json({
                                    "type": "audio.start",
                                    "sample_rate": 24000,
                                    "channels": 1,
                                })

                                async for chunk in tts_service.run_tts(response_text):
                                    await websocket.send_bytes(chunk["audio"])

                                await websocket.send_json({
                                    "type": "audio.end",
                                })

                        except Exception as e:
                            logger.error("LLM/TTS error: %s", e)
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Processing error: {str(e)}",
                            })

                        await websocket.send_json({
                            "type": "response.end",
                        })

            # Handle text/JSON control messages
            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "session.update":
                        # Update session configuration dynamically
                        update = SessionUpdateMessage(**data)
                        if update.voice_id:
                            session_config.voice_id = update.voice_id
                        if update.personality:
                            session_config.personality = update.personality
                        if update.situation:
                            session_config.situation = update.situation
                        if update.tts_engine:
                            session_config.tts_engine = update.tts_engine
                            # Recreate TTS service with new engine
                            tts_service = create_tts_service(
                                engine=update.tts_engine,
                                voice_id=session_config.voice_id,
                                speed=session_config.tts_speed,
                                emotion_exaggeration=session_config.emotion_exaggeration,
                            )

                        # Update conversation manager with new config
                        conversation.update_session_config(session_config)

                        await websocket.send_json({
                            "type": "session.updated",
                            "config": {
                                "voice_id": session_config.voice_id,
                                "personality": session_config.personality[:100] + "...",
                                "situation": session_config.situation[:100] + "...",
                                "tts_engine": session_config.tts_engine,
                            },
                        })
                        logger.info("Session %s updated", session_id)

                    elif msg_type == "conversation.clear":
                        conversation.clear()
                        await websocket.send_json({
                            "type": "conversation.cleared",
                        })
                        logger.info("Conversation cleared: %s", session_id)

                    elif msg_type == "memory.clear":
                        await memory_manager.clear_user_memories(session_config.user_id)
                        await websocket.send_json({
                            "type": "memory.cleared",
                        })

                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                    elif msg_type == "input.text":
                        # Text input mode (bypass STT)
                        text_input = data.get("text", "").strip()
                        if text_input:
                            # Process as if it were transcribed speech
                            await websocket.send_json({
                                "type": "transcription",
                                "text": text_input,
                                "is_final": True,
                                "source": "text",
                            })

                            if memory_manager.is_enabled:
                                memory_context = await memory_manager.get_relevant_memories(
                                    query=text_input,
                                    user_id=session_config.user_id,
                                )
                                if memory_context:
                                    conversation.inject_memory_context(memory_context)

                            conversation.add_user_message(text_input)

                            await websocket.send_json({"type": "response.start"})

                            try:
                                import ollama as ollama_client

                                response_text = ""
                                stream = ollama_client.chat(
                                    model=app_config.ollama_model,
                                    messages=conversation.messages,
                                    stream=True,
                                    options={
                                        "num_predict": 150,
                                        "temperature": 0.7,
                                        "top_p": 0.9,
                                    },
                                )

                                for chunk in stream:
                                    if "message" in chunk and "content" in chunk["message"]:
                                        response_text += chunk["message"]["content"]

                                response_text = response_text.strip()

                                if response_text:
                                    await websocket.send_json({
                                        "type": "response.text",
                                        "text": response_text,
                                    })

                                    conversation.add_assistant_message(response_text)

                                    if memory_manager.is_enabled:
                                        await memory_manager.add_conversation(
                                            user_message=text_input,
                                            assistant_message=response_text,
                                            user_id=session_config.user_id,
                                        )

                                    await websocket.send_json({
                                        "type": "audio.start",
                                        "sample_rate": 24000,
                                        "channels": 1,
                                    })

                                    async for chunk in tts_service.run_tts(response_text):
                                        await websocket.send_bytes(chunk["audio"])

                                    await websocket.send_json({"type": "audio.end"})

                            except Exception as e:
                                logger.error("Processing error: %s", e)
                                await websocket.send_json({
                                    "type": "error",
                                    "message": str(e),
                                })

                            await websocket.send_json({"type": "response.end"})

                    else:
                        logger.warning("Unknown message type: %s", msg_type)

                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        # Cleanup session
        if session_id in active_sessions:
            del active_sessions[session_id]
        logger.info("Session cleaned up: %s", session_id)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=app_config.host,
        port=app_config.port,
        reload=False,
        log_level=app_config.log_level.lower(),
        ws_max_size=16 * 1024 * 1024,  # 16MB max WebSocket message
    )
