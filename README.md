# Discord + Voice for Claude Code

A voice channel extension for [Claude Code](https://claude.ai/code) that works **alongside** the official `discord@claude-plugins-official` plugin.

> **How it works:** The official plugin handles message delivery (text/DM). This plugin adds voice channel tools on top — ASR (speech-to-text) and TTS (text-to-speech). Both run together; you still need the official plugin's `--channels` flag.

- Talk to Claude via Discord voice channel — speech is transcribed and delivered as messages
- Claude responds by speaking back into the voice channel via TTS
- Pluggable ASR backends: **Qwen3/mlx** (Apple Silicon) or **Whisper** (cross-platform)
- TTS via **edge-tts** — free, no API key, supports 300+ voices

## Voice tools added by this plugin

| Tool | Description |
|---|---|
| `voice_join(channel_id, guild_id, text_channel_id)` | Join a voice channel and start listening |
| `voice_play(guild_id, text?, voice?, clone?, lang?, speed?, local?, file?)` | Speak TTS or play an audio file |
| `voice_stop(guild_id)` | Stop currently playing audio |
| `voice_leave(guild_id)` | Disconnect from voice channel |
| `voice_clone_create(name, file?, url?, ref_text?)` | Register a new cloned voice from audio file or YouTube URL |

---

## Prerequisites

### 1. System

```bash
# macOS (Homebrew)
brew install ffmpeg bun

# Linux (apt)
sudo apt install ffmpeg
curl -fsSL https://bun.sh/install | bash
```

> **ffmpeg is required** for audio conversion in the ASR pipeline.

### 2. TTS — edge-tts (all platforms)

```bash
pip3 install edge-tts
```

Verify:
```bash
python3 -m edge_tts --voice en-US-GuyNeural --text "Hello" --write-media /tmp/test.mp3
```

### 3. ASR — choose one backend

#### Option A: Whisper (cross-platform, recommended for most users)

```bash
pip3 install openai-whisper
```

Verify:
```bash
python3 -m whisper --help
```

#### Option B: mlx_audio / Qwen3 ASR (Apple Silicon only, best quality)

```bash
python3 -m venv ~/.venvs/discord-voice
~/.venvs/discord-voice/bin/pip install mlx-audio mlx huggingface_hub

# Download Qwen3 ASR model (~1.7GB)
~/.venvs/discord-voice/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Qwen3-ASR-1.7B-bf16', local_dir='$HOME/.omlx/models/Qwen3-ASR-1.7B-bf16')
"
```

---

## Installation

### 1. Create a Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
2. Go to **Bot** tab → enable **Message Content Intent** (required)
3. Copy your **Bot Token** (reset if needed — shown only once)
4. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot permissions: `View Channels`, `Send Messages`, `Read Message History`, `Attach Files`, `Add Reactions`, `Connect`, `Speak`, `Use Voice Activity`
5. Visit the generated URL to add the bot to your server

### 2. Install Claude Code plugins

```bash
# Install Claude Code if needed
npm install -g @anthropic-ai/claude-code

# Install the official Discord plugin (required for message relay)
# Run inside a claude session:
#   /plugin install discord@claude-plugins-official

# Copy this voice plugin into Claude Code's custom plugins directory
cp -r /path/to/discord-voice-plugin ~/.claude/plugins/custom/discord-voice
```

### 3. Store your bot token

```bash
mkdir -p ~/.claude/channels/discord
echo "DISCORD_BOT_TOKEN=your_token_here" > ~/.claude/channels/discord/.env
chmod 600 ~/.claude/channels/discord/.env
```

### 4. Start Claude Code

Both plugins must be active. The `--channels` flag activates the official plugin's message relay — without it, Discord messages never reach Claude. The voice plugin loads automatically from the custom plugins directory.

```bash
cd ~/your-project
DISCORD=1 claude --channels plugin:discord@claude-plugins-official
```

> **Multi-session support:** The `DISCORD=1` env var gates all Discord hooks. Sessions without it skip voice auto-join and message watchers, so you can run multiple Claude Code sessions without them fighting over the bot. Only one session should use `DISCORD=1` at a time.

### 5. Pair your Discord account

DM your bot on Discord — it replies with a pairing code. Then in Claude Code run:

```
/discord:access pair <code>
```

Done! Your DMs now reach Claude.

---

## Configuration

All configuration is via environment variables. Add them to `~/.claude/channels/discord/.env`:

| Variable | Default | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Your Discord bot token |
| `VOICE_ASR_BACKEND` | `mlx` on Apple Silicon, `whisper` otherwise | ASR engine: `mlx` or `whisper` |
| `VOICE_ASR_MODEL` | `Qwen3-ASR-1.7B-bf16` (mlx) / `base` (whisper) | Model path (mlx) or size (whisper: tiny/base/small/medium/large) |
| `VOICE_ASR_PYTHON` | venv python (mlx) / `python3` (whisper) | Python interpreter for ASR |
| `VOICE_TTS_VOICE` | `en-US-GuyNeural` | Default TTS voice (any [edge-tts voice](https://github.com/rany2/edge-tts#voices)) |
| `VOICE_SILENCE_MS` | `1500` | Silence duration (ms) before utterance is considered finished |
| `VOICE_AUTO_JOIN_CHANNEL` | *(unset)* | Voice channel ID to join automatically on startup |
| `VOICE_AUTO_JOIN_GUILD` | *(unset)* | Guild ID for auto-join |
| `VOICE_AUTO_JOIN_TEXT` | *(unset)* | Text channel ID for auto-join ASR notifications |
| `VOICE_CLONE_SERVER` | *(unset)* | URL of a Qwen3-TTS API server for voice cloning (see below) |
| `DISCORD_STATE_DIR` | `~/.claude/channels/discord` | Override state directory |
| `DISCORD_ACCESS_MODE` | *(unset)* | Set to `static` to pin access.json at boot (disables pairing) |

### Example `.env`

```env
DISCORD_BOT_TOKEN=MTIz...

# Use Whisper with the small model for better accuracy
VOICE_ASR_BACKEND=whisper
VOICE_ASR_MODEL=small

# Korean voice
VOICE_TTS_VOICE=ko-KR-InJoonNeural
```

---

## Using Voice Channel

Once Claude Code is running:

1. Join a Discord voice channel
2. Ask Claude to join (via text or DM):
   > "Join my voice channel — channel ID is `123456`, guild ID is `789012`, text channel ID is `345678`"
3. Claude joins and starts listening
4. Speak — your words are transcribed and delivered to Claude
5. Claude responds by speaking in the voice channel

**How to find IDs:** Enable Developer Mode in Discord (Settings → Advanced → Developer Mode), then right-click any channel or server to **Copy ID**.

---

## What this plugin adds

This plugin extends the official plugin — it does not replace it. Both must run together.

| Feature | Official plugin | + This plugin |
|---|---|---|
| Text/DM messages | ✅ handled | unchanged |
| File attachments | ✅ handled | unchanged |
| Emoji reactions | ✅ handled | unchanged |
| Permission relay | ✅ handled | unchanged |
| Voice channel join/leave | ❌ | ✅ |
| Speech-to-text (ASR) | ❌ | ✅ Whisper or mlx/Qwen3 |
| Text-to-speech in voice | ❌ | ✅ edge-tts (300+ voices) |
| Direct audio file playback | ❌ | ✅ |
| Auto-join voice on startup | ❌ | ✅ (via env vars) |

---

## Voice Cloning (optional)

> **Note:** Voice cloning is for personal/educational use only — it requires reference audio clips of the target voice.
>
> Voice cloning uses the [Qwen3-TTS-12Hz-1.7B-Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) model. Two inference paths are supported:
>
> 1. **Remote GPU server** (primary, ~6-10s) — Set `VOICE_CLONE_SERVER` to a Qwen3-TTS API server that implements `/generate` and `/generate_custom` endpoints
> 2. **Local MLX** (fallback, ~24-45s, Apple Silicon only) — Uses `mlx_audio.tts.generate` with the model at `~/.omlx/models/Qwen3-TTS-12Hz-1.7B-Base-bf16`. When the GPU server is unreachable, Claude asks the user before falling back to the slower local model. Pass `local=true` on `voice_play` to force local inference.
>
> Without a clone server or local model configured, edge-tts (the default) works for all standard TTS — no GPU needed.

Set `VOICE_CLONE_SERVER` in your `.env` to enable:

```env
VOICE_CLONE_SERVER=http://192.168.1.100:8880
```

Then use the `clone` parameter on `voice_play`:

```
voice_play(guild_id="...", text="Hello!", clone="uncle_roger", lang="en")
```

Register new voices with `voice_clone_create`:

```
voice_clone_create(name="my_voice", file="/path/to/15sec-clip.mp3")
voice_clone_create(name="celebrity", url="https://youtube.com/watch?v=...")
```

---

## Text Message Delivery

Discord text messages (DMs and channel messages) are delivered via a file-based inbox queue, since MCP push notifications don't reliably trigger conversation turns in the CLI.

Two watcher scripts handle delivery:

- **`text-inbox-watcher.py`** — persistent, runs from SessionStart. Polls `text-inbox/` every 2 seconds indefinitely. Ensures text DMs are always delivered, even when away from the terminal.
- **`voice-inbox-watcher.py`** — temporary (10 min timeout), started after each `voice_play` or `reply`. Polls `voice-inbox/` for speech transcriptions.

Text DMs can reactivate the voice listener: a text message arrives → Claude replies → the PostToolUse hook restarts the voice watcher.

See `hooks/` directory for the watcher scripts and `docs/SETUP.md` Step 5 for the settings.json hook configuration.

---

## TTS Audio Retention

Generated TTS audio files are saved in `recent-tts/` for 24 hours. This allows sending audio clips to Discord DMs instantly without regenerating them. Files older than 1 day are cleaned up automatically on each voice_play call.

---

## Known issues

### @discordjs/opus ABI mismatch on Bun

`@discordjs/opus` prebuilds target Node.js ABI versions but Bun uses a different ABI. This plugin auto-patches the prebuild directory on startup by creating a symlink — no manual action needed.

### DAVE encryption

Discord's new DAVE end-to-end voice encryption is enabled by default. This requires `@snazzah/davey` which is included in `package.json`. If you encounter voice connection issues on older Discord clients, this may be the cause.

---

## Access control

See [ACCESS.md](./ACCESS.md) for full documentation on DM policies, guild channels, allowlists, and the `access.json` schema.

---

## Contributing

PRs welcome. This plugin is a community extension of the official `discord@claude-plugins-official` plugin. Please keep `server.ts` self-contained (single file, no build step) to stay consistent with the official plugin's philosophy.
