/**
 * vocal-agent-fr-live — Minimal React Client
 *
 * Demonstrates WebSocket connection to the voice agent backend
 * with audio capture, streaming, and playback.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react'

const AGENT_WS_URL = 'ws://localhost:8765/ws'
const START_SESSION_URL = 'http://localhost:8765/start-session'

const styles = {
    container: {
        maxWidth: '600px',
        margin: '40px auto',
        padding: '24px',
        fontFamily: "'Inter', -apple-system, sans-serif",
        background: '#0f0f0f',
        color: '#e0e0e0',
        minHeight: '100vh',
    },
    title: {
        fontSize: '24px',
        fontWeight: 700,
        marginBottom: '8px',
        color: '#fff',
    },
    subtitle: {
        fontSize: '14px',
        color: '#888',
        marginBottom: '32px',
    },
    card: {
        background: '#1a1a1a',
        borderRadius: '12px',
        padding: '20px',
        marginBottom: '16px',
        border: '1px solid #333',
    },
    button: {
        padding: '12px 24px',
        borderRadius: '8px',
        border: 'none',
        fontWeight: 600,
        fontSize: '14px',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        marginRight: '8px',
        marginBottom: '8px',
    },
    btnPrimary: {
        background: '#3b82f6',
        color: '#fff',
    },
    btnDanger: {
        background: '#ef4444',
        color: '#fff',
    },
    btnSecondary: {
        background: '#333',
        color: '#fff',
    },
    status: {
        padding: '8px 12px',
        borderRadius: '8px',
        fontSize: '13px',
        marginBottom: '16px',
        display: 'inline-block',
    },
    statusConnected: {
        background: '#052e16',
        color: '#4ade80',
        border: '1px solid #166534',
    },
    statusDisconnected: {
        background: '#2a1215',
        color: '#f87171',
        border: '1px solid #7f1d1d',
    },
    log: {
        background: '#111',
        borderRadius: '8px',
        padding: '12px',
        maxHeight: '300px',
        overflowY: 'auto',
        fontSize: '12px',
        fontFamily: 'monospace',
        lineHeight: '1.6',
        border: '1px solid #333',
    },
    logEntry: {
        padding: '2px 0',
        borderBottom: '1px solid #222',
    },
    input: {
        width: '100%',
        padding: '10px 14px',
        borderRadius: '8px',
        border: '1px solid #333',
        background: '#111',
        color: '#e0e0e0',
        fontSize: '14px',
        marginBottom: '8px',
        boxSizing: 'border-box',
    },
    label: {
        fontSize: '12px',
        fontWeight: 600,
        color: '#888',
        marginBottom: '4px',
        display: 'block',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
    },
    inputGroup: {
        marginBottom: '12px',
    },
}

export default function App() {
    const [isConnected, setIsConnected] = useState(false)
    const [isRecording, setIsRecording] = useState(false)
    const [sessionId, setSessionId] = useState('')
    const [logs, setLogs] = useState([])
    const [textInput, setTextInput] = useState('')
    const [config, setConfig] = useState({
        personality: 'Tu es un assistant vocal chaleureux et naturel.',
        situation: 'Conversation vocale en temps réel.',
        voice_id: 'fr_FR-melo-voice1',
        tts_engine: 'melo',
    })

    const wsRef = useRef(null)
    const mediaRecorderRef = useRef(null)
    const audioContextRef = useRef(null)
    const audioQueueRef = useRef([])

    const addLog = useCallback((type, message) => {
        const time = new Date().toLocaleTimeString('fr-FR')
        setLogs(prev => [...prev.slice(-100), { time, type, message }])
    }, [])

    // --- WebSocket Connection ---
    const connect = useCallback(async () => {
        try {
            // Create session via REST API
            const res = await fetch(START_SESSION_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...config,
                    language: 'fr-FR',
                    user_id: 'react-user',
                }),
            })

            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()
            setSessionId(data.session_id)

            // Connect WebSocket
            const ws = new WebSocket(data.websocket_url)
            ws.binaryType = 'arraybuffer'

            ws.onopen = () => {
                setIsConnected(true)
                addLog('system', `Connecté — session: ${data.session_id.slice(0, 8)}...`)
            }

            ws.onmessage = (event) => {
                if (event.data instanceof ArrayBuffer) {
                    // Audio data — queue for playback
                    audioQueueRef.current.push(event.data)
                    playAudioQueue()
                } else {
                    const msg = JSON.parse(event.data)
                    switch (msg.type) {
                        case 'session.created':
                            addLog('system', '🎙️ Session prête')
                            break
                        case 'transcription':
                            addLog('user', `🗣️ ${msg.text}`)
                            break
                        case 'response.text':
                            addLog('agent', `🤖 ${msg.text}`)
                            break
                        case 'audio.start':
                            addLog('audio', '🔊 Audio en cours...')
                            break
                        case 'audio.end':
                            addLog('audio', '🔇 Audio terminé')
                            break
                        case 'error':
                            addLog('error', `❌ ${msg.message}`)
                            break
                        default:
                            addLog('system', `[${msg.type}]`)
                    }
                }
            }

            ws.onclose = () => {
                setIsConnected(false)
                addLog('system', 'Déconnecté')
            }

            ws.onerror = (err) => {
                addLog('error', 'Erreur WebSocket')
                console.error(err)
            }

            wsRef.current = ws
        } catch (err) {
            addLog('error', `Connexion échouée: ${err.message}`)
        }
    }, [config, addLog])

    const disconnect = useCallback(() => {
        wsRef.current?.close()
        wsRef.current = null
        setIsConnected(false)
    }, [])

    // --- Audio Playback ---
    const playAudioQueue = useCallback(async () => {
        if (!audioContextRef.current) {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 24000,
            })
        }

        const ctx = audioContextRef.current
        while (audioQueueRef.current.length > 0) {
            const data = audioQueueRef.current.shift()
            const int16 = new Int16Array(data)
            const float32 = new Float32Array(int16.length)
            for (let i = 0; i < int16.length; i++) {
                float32[i] = int16[i] / 32768
            }

            const buffer = ctx.createBuffer(1, float32.length, 24000)
            buffer.getChannelData(0).set(float32)
            const source = ctx.createBufferSource()
            source.buffer = buffer
            source.connect(ctx.destination)
            source.start()
        }
    }, [])

    // --- Audio Recording ---
    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                },
            })

            // Use ScriptProcessor for raw PCM access
            const ctx = new AudioContext({ sampleRate: 16000 })
            const source = ctx.createMediaStreamSource(stream)
            const processor = ctx.createScriptProcessor(4096, 1, 1)

            processor.onaudioprocess = (e) => {
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                    const float32 = e.inputBuffer.getChannelData(0)
                    const int16 = new Int16Array(float32.length)
                    for (let i = 0; i < float32.length; i++) {
                        int16[i] = Math.max(-1, Math.min(1, float32[i])) * 32767
                    }
                    wsRef.current.send(int16.buffer)
                }
            }

            source.connect(processor)
            processor.connect(ctx.destination)

            mediaRecorderRef.current = { stream, ctx, processor, source }
            setIsRecording(true)
            addLog('system', '🎤 Enregistrement démarré')
        } catch (err) {
            addLog('error', `Micro inaccessible: ${err.message}`)
        }
    }, [addLog])

    const stopRecording = useCallback(() => {
        const rec = mediaRecorderRef.current
        if (rec) {
            rec.processor.disconnect()
            rec.source.disconnect()
            rec.ctx.close()
            rec.stream.getTracks().forEach(t => t.stop())
            mediaRecorderRef.current = null
        }
        setIsRecording(false)
        addLog('system', '🎤 Enregistrement arrêté')
    }, [addLog])

    // --- Text Input ---
    const sendText = useCallback(() => {
        if (!textInput.trim() || !wsRef.current) return
        wsRef.current.send(JSON.stringify({
            type: 'input.text',
            text: textInput.trim(),
        }))
        addLog('user', `📝 ${textInput.trim()}`)
        setTextInput('')
    }, [textInput, addLog])

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            disconnect()
            stopRecording()
        }
    }, [disconnect, stopRecording])

    const getLogColor = (type) => {
        switch (type) {
            case 'user': return '#60a5fa'
            case 'agent': return '#34d399'
            case 'error': return '#f87171'
            case 'audio': return '#a78bfa'
            default: return '#888'
        }
    }

    return (
        <div style={styles.container}>
            <h1 style={styles.title}>🎙️ Agent Vocal FR</h1>
            <p style={styles.subtitle}>Client React — vocal-agent-fr-live</p>

            {/* Status */}
            <span style={{
                ...styles.status,
                ...(isConnected ? styles.statusConnected : styles.statusDisconnected),
            }}>
                {isConnected ? '● Connecté' : '○ Déconnecté'}
            </span>

            {/* Config */}
            {!isConnected && (
                <div style={styles.card}>
                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Personnalité</label>
                        <input
                            style={styles.input}
                            value={config.personality}
                            onChange={e => setConfig(c => ({ ...c, personality: e.target.value }))}
                        />
                    </div>
                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Situation</label>
                        <input
                            style={styles.input}
                            value={config.situation}
                            onChange={e => setConfig(c => ({ ...c, situation: e.target.value }))}
                        />
                    </div>
                    <button
                        style={{ ...styles.button, ...styles.btnPrimary }}
                        onClick={connect}
                    >
                        Se connecter
                    </button>
                </div>
            )}

            {/* Controls */}
            {isConnected && (
                <div style={styles.card}>
                    <div style={{ marginBottom: '12px' }}>
                        {!isRecording ? (
                            <button
                                style={{ ...styles.button, ...styles.btnPrimary }}
                                onClick={startRecording}
                            >
                                🎤 Commencer à parler
                            </button>
                        ) : (
                            <button
                                style={{ ...styles.button, ...styles.btnDanger }}
                                onClick={stopRecording}
                            >
                                ⏹ Arrêter
                            </button>
                        )}
                        <button
                            style={{ ...styles.button, ...styles.btnSecondary }}
                            onClick={disconnect}
                        >
                            Déconnecter
                        </button>
                    </div>

                    {/* Text input */}
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <input
                            style={{ ...styles.input, marginBottom: 0, flex: 1 }}
                            placeholder="Ou tapez un message..."
                            value={textInput}
                            onChange={e => setTextInput(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && sendText()}
                        />
                        <button
                            style={{ ...styles.button, ...styles.btnPrimary, marginRight: 0 }}
                            onClick={sendText}
                        >
                            Envoyer
                        </button>
                    </div>
                </div>
            )}

            {/* Logs */}
            <div style={styles.card}>
                <label style={{ ...styles.label, marginBottom: '8px' }}>Journal</label>
                <div style={styles.log}>
                    {logs.length === 0 && (
                        <div style={{ color: '#555' }}>En attente de connexion...</div>
                    )}
                    {logs.map((log, i) => (
                        <div key={i} style={styles.logEntry}>
                            <span style={{ color: '#555' }}>{log.time}</span>{' '}
                            <span style={{ color: getLogColor(log.type) }}>{log.message}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
