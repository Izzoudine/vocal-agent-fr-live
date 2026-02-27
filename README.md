# 🎙️ vocal-agent-fr-live

**Backend self-hosted complet pour agent vocal live speech-to-speech en français natif.**

Un agent vocal temps réel qui écoute, comprend et répond vocalement en français — 100% local, sans API cloud.

```
🎤 Vous parlez → 🧠 STT → 💬 LLM → 🔊 TTS → 🔈 Il répond vocalement
```

---

## 📋 Table des matières

- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Prérequis](#prérequis)
- [Installation rapide (Docker)](#installation-rapide-docker)
- [Installation manuelle](#installation-manuelle)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Protocole WebSocket](#protocole-websocket)
- [Exemples clients](#exemples-clients)
- [Déploiement DigitalOcean + Coolify](#déploiement-digitalocean--coolify)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Client                        │
│         (React / Flutter / Swift)               │
│                                                 │
│   🎤 Micro ──→ WebSocket ──→ 🔈 Haut-parleur   │
└───────────────────┬─────────────────────────────┘
                    │ WebSocket (binary audio + JSON)
                    ▼
┌─────────────────────────────────────────────────┐
│            vocal-agent-fr-live                  │
│                FastAPI Server                   │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │   STT    │  │   LLM    │  │     TTS      │  │
│  │ faster-  │→ │  Ollama  │→ │  MeloTTS /   │  │
│  │ whisper  │  │ Mistral  │  │  Chatterbox  │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                     ↕                           │
│              ┌───────────┐                      │
│              │   mem0    │                      │
│              │  Mémoire  │                      │
│              └───────────┘                      │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│              Ollama Server                      │
│         (LLM inference locale)                  │
└─────────────────────────────────────────────────┘
```

---

## Stack technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **STT** | `faster-whisper` + whisper-large-v3-french | Reconnaissance vocale français |
| **LLM** | Ollama + Mistral 7B (ou Lucie-7B) | Intelligence conversationnelle |
| **TTS** | MeloTTS (principal) + Chatterbox (fallback) | Synthèse vocale française |
| **Mémoire** | mem0 | Mémoire relationnelle persistante |
| **API** | FastAPI + WebSocket | Communication temps réel |
| **Orchestration** | Pipecat | Pipeline audio |

---

## Prérequis

### Minimum (CPU)
- **OS** : Linux (Ubuntu 22.04+), macOS, ou Windows (via Docker)
- **RAM** : 8 GB (avec modèles small/medium)
- **Stockage** : 50 GB SSD
- **Python** : 3.12+
- **Docker** : 24.0+

### Recommandé (GPU)
- **GPU** : NVIDIA avec 8GB+ VRAM (RTX 3060+)
- **RAM** : 16 GB
- **Latence** : <1.2s glass-to-glass avec GPU

---

## Installation rapide (Docker)

```bash
# 1. Cloner le projet
git clone https://github.com/YOUR_USER/vocal-agent-fr-live.git
cd vocal-agent-fr-live

# 2. Copier et configurer l'environnement
cp .env.example .env
# Éditez .env selon vos besoins

# 3. Lancer tout avec Docker Compose
docker-compose up -d

# 4. Vérifier que tout fonctionne
curl http://localhost:8765/health
```

Le premier lancement téléchargera automatiquement :
- Le modèle Ollama (~4 GB)
- Le modèle Whisper (~500 MB pour `small`)
- Le modèle MeloTTS (~500 MB)

---

## Installation manuelle

```bash
# 1. Créer un environnement virtuel
python3.12 -m venv venv
source venv/bin/activate  # Linux/macOS
# ou: .\venv\Scripts\activate  # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Installer Ollama séparément
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull mistral:7b-instruct-v0.3-q4_0

# 4. Configurer
cp .env.example .env
# Modifiez OLLAMA_HOST=http://localhost:11434

# 5. Lancer
python main.py
```

---

## Configuration

### Variables d'environnement (.env)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `HOST` | `0.0.0.0` | Adresse d'écoute |
| `PORT` | `8765` | Port du serveur |
| `OLLAMA_HOST` | `http://ollama:11434` | URL du serveur Ollama |
| `OLLAMA_MODEL` | `mistral:7b-instruct-v0.3-q4_0` | Modèle LLM |
| `STT_MODEL_SIZE` | `small` | Taille du modèle Whisper |
| `STT_DEVICE` | `cpu` | Device STT (`cpu` / `cuda`) |
| `TTS_ENGINE` | `melo` | Moteur TTS (`melo` / `chatterbox`) |
| `TTS_VOICE_ID` | `fr_FR-melo-voice1` | Identifiant de voix |
| `MEM0_ENABLED` | `true` | Activer la mémoire |
| `API_KEY` | *(vide)* | Clé API optionnelle |
| `CORS_ORIGINS` | `http://localhost:3000` | Origines CORS autorisées |

### Configuration de session dynamique

Chaque session peut être personnalisée avec :

```json
{
  "voice_id": "fr_FR-melo-voice1",
  "personality": "Tu es Eve, une coach sportive énergétique et motivante de 28 ans...",
  "situation": "Vous êtes dans une salle de sport virtuelle à Cotonou à 7h du matin, il fait 28°C...",
  "language": "fr-FR",
  "tts_engine": "melo",
  "user_id": "user-123"
}
```

---

## API Reference

### `GET /health`
Vérification de l'état du serveur.

```bash
curl http://localhost:8765/health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "active_sessions": 2,
  "memory_enabled": true
}
```

### `POST /start-session`
Créer une nouvelle session vocale.

```bash
curl -X POST http://localhost:8765/start-session \
  -H "Content-Type: application/json" \
  -d '{
    "voice_id": "fr_FR-melo-voice1",
    "personality": "Tu es Eve, une coach sportive énergétique...",
    "situation": "Salle de sport virtuelle à Cotonou, 7h du matin, 28°C",
    "language": "fr-FR",
    "tts_engine": "melo",
    "user_id": "user-123"
  }'
```

```json
{
  "session_id": "a1b2c3d4-...",
  "websocket_url": "ws://localhost:8765/ws/a1b2c3d4-...",
  "config": { ... }
}
```

### `GET /sessions`
Lister les sessions actives.

### `DELETE /sessions/{session_id}`
Supprimer une session.

---

## Protocole WebSocket

### Connexion

```
ws://localhost:8765/ws/{session_id}
```

### Messages Client → Serveur

#### Audio (binaire)
Envoyez des frames audio brutes :
- **Format** : PCM 16-bit, 16kHz, mono
- **Taille recommandée** : chunks de 32000 octets (~1 seconde)

#### `session.update` (JSON)
Mettre à jour la configuration en cours de session :

```json
{
  "type": "session.update",
  "voice_id": "eve-energetique",
  "personality": "Tu es un philosophe zen...",
  "situation": "Méditation guidée au lever du soleil..."
}
```

#### `input.text` (JSON)
Envoyer du texte au lieu de l'audio (bypass STT) :

```json
{
  "type": "input.text",
  "text": "Salut, comment tu vas ?"
}
```

#### `conversation.clear` (JSON)
Réinitialiser l'historique de conversation :

```json
{ "type": "conversation.clear" }
```

#### `memory.clear` (JSON)
Effacer la mémoire de l'utilisateur :

```json
{ "type": "memory.clear" }
```

#### `ping` (JSON)
```json
{ "type": "ping" }
```

### Messages Serveur → Client

#### `session.created`
```json
{
  "type": "session.created",
  "session_id": "a1b2c3d4-...",
  "config": { "voice_id": "...", "language": "fr-FR", "tts_engine": "melo" }
}
```

#### `transcription`
```json
{
  "type": "transcription",
  "text": "Salut comment ça va ?",
  "is_final": true
}
```

#### `response.start` / `response.text` / `response.end`
```json
{ "type": "response.start" }
{ "type": "response.text", "text": "Ça va super bien ! Et toi ?" }
{ "type": "response.end" }
```

#### `audio.start` / Audio binaire / `audio.end`
```json
{ "type": "audio.start", "sample_rate": 24000, "channels": 1 }
// ... binary audio frames (PCM 16-bit) ...
{ "type": "audio.end" }
```

#### `error`
```json
{ "type": "error", "message": "Processing error: ..." }
```

---

## Exemples clients

### React (minimal)

Voir [`examples/react-client/`](./examples/react-client/) — Application React complète avec :
- Capture audio via MediaRecorder
- WebSocket bidirectionnel
- Lecture audio en streaming
- Interface visuelle

### Flutter (minimal)

Voir [`examples/flutter-client/`](./examples/flutter-client/) — Application Flutter avec :
- Enregistrement audio
- WebSocket via `web_socket_channel`
- Lecture audio

### Test rapide avec websocat

```bash
# Installer websocat
# https://github.com/nickel-org/websocat

# Connexion texte simple (bypass audio)
websocat ws://localhost:8765/ws/test-session

# Envoyez:
{"type": "input.text", "text": "Salut ! Tu es qui ?"}
```

### Test avec Python

```python
import asyncio
import json
import websockets

async def test():
    uri = "ws://localhost:8765/ws/test-session"
    async with websockets.connect(uri) as ws:
        # Attendez la confirmation de session
        msg = await ws.recv()
        print("Session:", json.loads(msg))

        # Envoyez un message texte
        await ws.send(json.dumps({
            "type": "input.text",
            "text": "Salut ! Raconte-moi une blague en français."
        }))

        # Recevez les réponses
        while True:
            msg = await ws.recv()
            if isinstance(msg, str):
                data = json.loads(msg)
                print(f"[{data['type']}]", data.get('text', ''))
                if data['type'] == 'response.end':
                    break
            else:
                print(f"[audio] {len(msg)} bytes")

asyncio.run(test())
```

---

## Déploiement DigitalOcean + Coolify

### Option 1 : Déploiement direct sur Droplet

```bash
# 1. Créer un Droplet DigitalOcean
#    - Image : Ubuntu 24.04
#    - Plan : CPU Optimized 8GB RAM (ou GPU Droplet pour <1.2s latence)
#    - Stockage : 50GB+ SSD
#    - Région : proche de vos utilisateurs

# 2. Se connecter au Droplet
ssh root@YOUR_DROPLET_IP

# 3. Installer Docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# 4. Cloner le projet
git clone https://github.com/YOUR_USER/vocal-agent-fr-live.git
cd vocal-agent-fr-live

# 5. Configurer
cp .env.example .env
nano .env  # Ajustez les variables

# 6. Lancer
docker compose up -d

# 7. Vérifier
curl http://localhost:8765/health

# 8. (Optionnel) Configurer un reverse proxy nginx
apt install -y nginx
# Configurez nginx pour proxy_pass vers localhost:8765
# avec support WebSocket (Upgrade headers)
```

### Option 2 : Via Coolify

```bash
# 1. Installer Coolify sur votre Droplet
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash

# 2. Accéder à Coolify UI : http://YOUR_DROPLET_IP:8000

# 3. Ajouter une nouvelle ressource :
#    - Type : Docker Compose
#    - Source : GitHub repository
#    - Branche : main
#    - Docker Compose file : docker-compose.yml

# 4. Configurer les variables d'environnement dans Coolify UI

# 5. Déployer !
```

### GitHub Secrets necessaires

Pour le CI/CD automatique (`.github/workflows/deploy-coolify.yml`) :

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | IP du Droplet |
| `DEPLOY_USER` | Utilisateur SSH (ex: `root`) |
| `DEPLOY_SSH_KEY` | Clé SSH privée |
| `COOLIFY_WEBHOOK_URL` | *(optionnel)* URL webhook Coolify |

---

## Troubleshooting

### Le serveur ne démarre pas

```bash
# Vérifier les logs
docker-compose logs -f vocal-agent

# Vérifier que Ollama est ready
curl http://localhost:11434/api/tags

# Vérifier les modèles téléchargés
docker-compose logs ollama-pull
```

### Erreur "Model not found"

```bash
# Télécharger le modèle manuellement
docker-compose exec ollama ollama pull mistral:7b-instruct-v0.3-q4_0
```

### Mémoire insuffisante (OOM)

- Réduisez `STT_MODEL_SIZE` à `small` ou `tiny`
- Utilisez un modèle LLM plus petit : `mistral:7b-instruct-v0.3-q4_0`
- Désactivez la mémoire : `MEM0_ENABLED=false`

### Latence élevée

- **CPU** : Attendez 3-8s de latence, c'est normal
- **GPU** : Passez `STT_DEVICE=cuda`, utilisez `large-v3`
- Utilisez WebRTC au lieu de WebSocket pour le transport audio

### Support GPU NVIDIA

Décommentez la section GPU dans `docker-compose.yml` et installez :

```bash
# NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update && apt-get install -y nvidia-container-toolkit
systemctl restart docker
```

---

## Licence

MIT — Utilisez, modifiez, distribuez librement.

---

## Contributeurs

Contributions bienvenues ! Ouvrez une issue ou un PR.
