# Masquerade

**AI Board Game Arena** — LLM agents play social deduction games with independent reasoning, memory, and strategy. Watch the full game unfold as a cinematic video or interactive web replay.

[中文文档](README_zh.md)

https://github.com/GOODDAYDAY/Masquerade

---

## What Is This?

Masquerade is a fully automated pipeline where AI agents play board games **with zero human intervention**. Each player is an independent LLM agent with its own persona, memory, and decision-making strategy. The entire game — thinking, speaking, voting, deception — is driven by AI.

After a game finishes, Masquerade can:
- **Replay it interactively** in a web-based theater with playback controls
- **Render it to video** (2K 60fps MP4 with TTS voice acting) via Remotion

### Supported Games

| Game | Players | Description |
|:-----|:--------|:------------|
| **Who Is The Spy** (谁是卧底) | 3–8 | Each player gets a secret word. One is the spy with a different word. Find the spy through discussion and voting. |
| **Werewolf** (狼人杀) | 8–12 | Classic Mafia-style game with 6 roles: Werewolf, Villager, Seer, Witch, Hunter, Guard. Day/night phases with role-specific abilities. |

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  Masquerade Pipeline              │
│                                                  │
│  1. Game Simulation    Python backend            │
│     GameEngine ←→ PlayerAgent (LLM)              │
│     Orchestrator drives turns, records script     │
│                                                  │
│  2. TTS Generation     edge-tts                  │
│     Script → MP3 audio per speech event           │
│                                                  │
│  3. Output                                       │
│     ├─ Interactive Web Theater (React + Vite)    │
│     └─ Video Rendering (Remotion, 2K 60fps)      │
└──────────────────────────────────────────────────┘
```

### Core Design Principles

- **Game Engine** — Pure game logic, LLM-agnostic. Easy to add new games.
- **Agent** — LangGraph-based reasoning with memory, strategy tips, and expression tracking.
- **Orchestrator** — Decouples engine from agents. Supports concurrent LLM calls during batch phases (voting, night actions).
- **Script** — Structured JSON with full timeline, inner monologue, memory snapshots.
- **Frontend** — Game-agnostic React components. One UI supports all game types.
- **Remotion** — Deterministic frame-driven rendering. Same input = same output, every time.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI-compatible LLM API key (DeepSeek, OpenAI, etc.)
- ffmpeg (for video rendering)

### Setup

```bash
# Clone
git clone https://github.com/GOODDAYDAY/Masquerade.git
cd Masquerade

# Python dependencies
pip install -e .

# Frontend dependencies
cd frontend && npm install && cd ..

# Configure LLM API key
cp .env.example .env
# Edit .env and set MASQUERADE_LLM__API_KEY
```

### Run a Game

```bash
# List available games
python -m backend.main --list

# Run a spy game
python -m backend.main spy

# Run a werewolf game
python -m backend.main werewolf
```

Output: `output/scripts/game_<type>_<timestamp>.json`

### Generate TTS Audio

```bash
python -m backend.tts.generate output/scripts/game_spy_xxx.json
```

Output: `output/audio/<game_id>/` (MP3 files + manifest.json)

### Interactive Web Replay

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`, drag & drop the game script JSON, and watch the replay with playback controls and audio.

### Render Video (Remotion)

```bash
# Render a specific game script to MP4
node scripts/render-video.mjs game_spy_xxx.json
```

Output: `output/videos/<game_name>.mp4` (2K 60fps, H.264)

### One-Click Pipeline

```bash
# Windows: run game → generate TTS → render video
scripts\run.bat
```

## Project Structure

```
Masquerade/
├── backend/
│   ├── main.py              # CLI entry point
│   ├── engine/              # Game engines (spy, werewolf)
│   ├── agent/               # LLM player agents (LangGraph)
│   ├── orchestrator/        # Game runner + concurrency
│   ├── script/              # Script recording (JSON output)
│   ├── tts/                 # TTS audio generation (edge-tts)
│   └── core/                # Config, logging, exceptions
├── frontend/
│   ├── src/
│   │   ├── components/      # Interactive theater (React + Framer Motion)
│   │   ├── remotion/        # Video rendering (Remotion, frame-driven)
│   │   ├── core/            # Timeline controller, audio manager
│   │   └── types/           # Shared TypeScript types
│   └── package.json
├── config/
│   ├── app_config.yaml      # Global settings (LLM, concurrency, logging)
│   └── games/               # Per-game configs (players, roles, words)
├── scripts/                  # Automation (.bat + .sh)
├── output/                   # Generated scripts, audio, videos
└── requirements/             # Requirement tracking documents
```

## Configuration

### LLM Provider

Masquerade supports any **OpenAI-compatible API**. Configure in `.env` or `config/app_config.yaml`:

```yaml
llm:
  model: deepseek-chat
  api_base: https://api.deepseek.com/v1
  temperature: 0.7
```

Tested providers: **DeepSeek**, **OpenAI**, **local LLMs** (via ollama/vLLM).

### Game Config

Customize players, roles, and rules in `config/games/`:

```yaml
# config/games/spy.yaml
spy_count: 1
blank_count: 0
players:
  - name: Alice
    persona: "A cautious analyst who observes before speaking"
  - name: Bob
    persona: "A bold leader who drives discussion"
  # ...
```

## Extending

### Add a New Game

1. Create `backend/engine/<game>/game.py` extending `GameEngine`
2. Define role-specific strategies in `strategy.py`
3. Register with `@register_game("game_name")`
4. Add config in `config/games/<game>.yaml`
5. Frontend scenes are game-agnostic — new games work automatically

### Change TTS Provider

Replace `backend/tts/generate.py` with your preferred TTS engine. The contract is simple: produce MP3 files + `manifest.json` per game script.

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Game engine | Python, Pydantic |
| LLM agents | LangGraph, OpenAI SDK |
| TTS | edge-tts (Microsoft, free) |
| Interactive replay | React 18, TypeScript, Framer Motion, Tailwind CSS, Vite |
| Video rendering | Remotion 4 (frame-driven, deterministic) |
| Video encoding | H.264 via ffmpeg, GPU-accelerated (NVENC/AMF/QSV auto-detect) |

## License

[Apache License 2.0](LICENSE) — Free to use, modify, and distribute. Attribution required.
