# Discord Voice Channel Integration — Setup Guide
_For a brand new system_

This guide sets up a Discord bot that joins a voice channel, transcribes speech with a local ASR model, and lets Claude respond via TTS — all in real time from the Claude Code CLI.

---

## Prerequisites

### System
- macOS (tested) or Linux
- [Bun](https://bun.sh) runtime
- Python 3 with `pip`
- `ffmpeg` installed (`brew install ffmpeg`)

### Python environment
```bash
python3 -m venv ~/.venvs/qwen-tts
source ~/.venvs/qwen-tts/bin/activate
pip install mlx-audio edge-tts
```

### ASR model (Qwen3 ASR — runs on Apple Silicon via MLX)
```bash
# Download to ~/.omlx/models/
python3 -c "
from mlx_audio.stt.utils import load_model
load_model('Qwen/Qwen3-ASR-1.7B')
"
# Or manually place model files at:
# ~/.omlx/models/Qwen3-ASR-1.7B-bf16/
```

### TTS (edge-tts — must be system Python, not the venv)
```bash
/usr/bin/python3 -m pip install edge-tts
# Test:
/usr/bin/python3 -m edge_tts --text "Hello" --voice en-US-GuyNeural --write-media /tmp/test.mp3
```
The plugin calls `/usr/bin/python3 -m edge_tts` directly — it does NOT use the Qwen venv for TTS.

---

## Step 1: Create a Discord Bot

1. Go to https://discord.com/developers/applications → **New Application**
2. Go to **Bot** → Enable:
   - **Message Content Intent**
   - **Server Members Intent**
   - **Presence Intent**
3. Copy the **Bot Token** — you'll need it later
4. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Connect`, `Speak`, `Use Voice Activity`
5. Use the generated URL to invite the bot to your server
6. Note your server's **Guild ID**, **Voice Channel ID**, and **Text Channel ID**
   (Enable Developer Mode in Discord settings → right-click channels to copy IDs)

---

## Step 2: Install the Plugin

### 2a. Register MCP server in Claude Code

```bash
claude mcp add discord-voice \
  --command bun \
  --args "run" "--cwd" "/PATH/TO/plugin" "--shell=bun" "--silent" "start"
```

Or add manually to `~/.claude.json` under `projects["/your/project"].mcpServers`:
```json
"discord-voice": {
  "type": "stdio",
  "command": "bun",
  "args": ["run", "--cwd", "/PATH/TO/plugin", "--shell=bun", "--silent", "start"],
  "env": {}
}
```

### 2b. Plugin directory structure

Recommended path: `~/.claude/plugins/lib/discord-voice/`

```
~/.claude/plugins/lib/discord-voice/
  server.ts        # Full MCP server plugin (~1400 lines — see Step 6 for voice-specific parts)
  package.json
```

> **Note:** The `server.ts` is a complete MCP server handling Discord gateway connection, message routing, access control, voice receive, TTS, and all tool endpoints. Step 6 only shows the voice-receive-specific code. You need the full file — it is not just the snippets shown below.

**package.json:**
```json
{
  "name": "claude-channel-discord",
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "start": "bun install --no-summary && bun server.ts"
  },
  "dependencies": {
    "@discordjs/opus": "^0.10.0",
    "@discordjs/voice": "^0.19.0",
    "@modelcontextprotocol/sdk": "^1.0.0",
    "@snazzah/davey": "^0.1.10",
    "discord.js": "^14.14.0",
    "sodium-native": "^4.0.0"
  }
}
```

### 2c. Bot token and state directory

```bash
mkdir -p ~/.claude/channels/discord
cat > ~/.claude/channels/discord/.env << 'EOF'
DISCORD_BOT_TOKEN=your_token_here
EOF
chmod 600 ~/.claude/channels/discord/.env
```

---

## Step 3: Configure Access

Create `~/.claude/channels/discord/access.json`:
```json
{
  "dmPolicy": "allowlist",
  "allowFrom": ["YOUR_DISCORD_USER_ID"],
  "groups": {
    "YOUR_TEXT_CHANNEL_ID": {
      "requireMention": false,
      "allowFrom": ["YOUR_DISCORD_USER_ID"]
    }
  },
  "pending": {}
}
```

Your Discord user ID: Settings → Advanced → Enable Developer Mode → click your name → Copy User ID.

---

## Step 4: Voice Delivery Scripts

These two Python scripts enable automatic voice responses without requiring text input.

### 4a. voice-poll.py
`~/.claude/channels/discord/voice-poll.py`

```python
#!/usr/bin/env python3
import os, json, glob, sys, time

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'voice-inbox')
WAIT_FILE = os.path.join(inbox, '00_wait.json')

def write_wait_marker(seconds=30):
    os.makedirs(inbox, exist_ok=True)
    with open(WAIT_FILE, 'w') as f:
        json.dump({'__wait__': True, 'expires': time.time() + seconds}, f)

def check_wait_marker():
    try:
        with open(WAIT_FILE) as f:
            d = json.load(f)
        if d.get('__wait__') and time.time() < d.get('expires', 0):
            return True
        os.remove(WAIT_FILE)
    except FileNotFoundError:
        pass
    except Exception:
        try: os.remove(WAIT_FILE)
        except: pass
    return False

def deliver_first():
    files = sorted(f for f in glob.glob(os.path.join(inbox, '*.json'))
                   if not os.path.basename(f).startswith('00_'))
    if not files:
        return False
    try:
        with open(files[0]) as f:
            d = json.load(f)
        os.remove(files[0])
        write_wait_marker(30)
        print('<channel source="voice" chat_id="{chat_id}" message_id="{message_id}" user="{user}" ts="{ts}">{content}</channel>'.format(**d))
        return True
    except Exception:
        return False

if deliver_first():
    sys.exit(2)

if not os.path.isdir(inbox):
    sys.exit(0)

poll_secs = 30 if check_wait_marker() else 5
for _ in range(poll_secs):
    time.sleep(1)
    if deliver_first():
        sys.exit(2)

sys.exit(0)
```

### 4b. voice-inbox-watcher.py (temporary, 10 min)
`~/.claude/channels/discord/voice-inbox-watcher.py`

Started by PostToolUse on `voice_play` or `reply`. Polls voice-inbox only, times out after 10 minutes.

```python
#!/usr/bin/env python3
import os, json, glob, sys, time

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'voice-inbox')
WATCHER_PID_FILE = os.path.join(inbox, '00_watcher.pid')

def is_real_message(path):
    return not os.path.basename(path).startswith('00_')

def deliver_first():
    files = sorted(f for f in glob.glob(os.path.join(inbox, '*.json')) if is_real_message(f))
    if not files:
        return False
    try:
        with open(files[0]) as f:
            d = json.load(f)
        os.remove(files[0])
        print('<channel source="voice" chat_id="{chat_id}" message_id="{message_id}" user="{user}" ts="{ts}">{content}</channel>'.format(**d))
        return True
    except Exception:
        return False

os.makedirs(inbox, exist_ok=True)

my_pid = os.getpid()
try:
    old_pid = int(open(WATCHER_PID_FILE).read().strip())
    if old_pid != my_pid:
        try: os.kill(old_pid, 9)
        except: pass
except Exception:
    pass
with open(WATCHER_PID_FILE, 'w') as f:
    f.write(str(my_pid))

# Poll for up to 10 minutes
for _ in range(600):
    time.sleep(1)
    try:
        current_pid = int(open(WATCHER_PID_FILE).read().strip())
        if current_pid != my_pid:
            sys.exit(0)
    except Exception:
        pass
    if deliver_first():
        try: os.remove(WATCHER_PID_FILE)
        except: pass
        sys.exit(2)

try:
    if int(open(WATCHER_PID_FILE).read().strip()) == my_pid:
        os.remove(WATCHER_PID_FILE)
except Exception:
    pass
sys.exit(0)
```

### 4c. text-inbox-watcher.py (persistent)
`~/.claude/channels/discord/text-inbox-watcher.py`

Started by SessionStart. Runs **indefinitely**, polling text-inbox every 2 seconds. Ensures text DMs are always delivered, even when away from the terminal. When a text message triggers a `reply`, the PostToolUse hook restarts the voice watcher — so text DMs reactivate the voice listener.

```python
#!/usr/bin/env python3
import os, json, glob, sys, time, signal

text_inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'text-inbox')
PID_FILE = os.path.join(text_inbox, '00_text_watcher.pid')

os.makedirs(text_inbox, exist_ok=True)

my_pid = os.getpid()
try:
    old_pid = int(open(PID_FILE).read().strip())
    if old_pid != my_pid:
        try: os.kill(old_pid, 9)
        except: pass
except Exception:
    pass
with open(PID_FILE, 'w') as f:
    f.write(str(my_pid))

def deliver_first():
    files = sorted(glob.glob(os.path.join(text_inbox, '*.json')))
    if not files:
        return False
    try:
        with open(files[0]) as f:
            d = json.load(f)
        os.remove(files[0])
        att_attrs = ''
        if d.get('attachment_count'):
            att_attrs = ' attachment_count="{attachment_count}" attachments="{attachments}"'.format(**d)
        print('<channel source="discord" chat_id="{chat_id}" message_id="{message_id}" user="{user}" ts="{ts}"{att}>{content}</channel>'.format(att=att_attrs, **d))
        return True
    except Exception:
        return False

# Poll indefinitely
while True:
    time.sleep(2)
    try:
        current_pid = int(open(PID_FILE).read().strip())
        if current_pid != my_pid:
            sys.exit(0)
    except Exception:
        pass
    if deliver_first():
        sys.exit(2)
```

---

## Step 5: Configure Claude Code Settings

`~/.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "mcp__discord-voice__reply",
      "mcp__discord-voice__react",
      "mcp__discord-voice__download_attachment",
      "mcp__discord-voice__edit_message",
      "mcp__discord-voice__fetch_messages",
      "mcp__discord-voice__voice_join",
      "mcp__discord-voice__voice_leave",
      "mcp__discord-voice__voice_play",
      "mcp__discord-voice__voice_stop",
      "mcp__discord-voice__voice_clone_create"
    ]
  },
  "hooks": {
    "SessionStart": [{
      "hooks": [
        {
          "type": "command",
          "command": "sleep 10 && echo 'System: Join Discord voice channel now. Call mcp__discord-voice__voice_join with channel_id=VOICE_CHANNEL_ID guild_id=GUILD_ID text_channel_id=TEXT_CHANNEL_ID. After joining, immediately call voice_play with a short greeting to activate the voice listener loop.' && exit 2",
          "asyncRewake": true
        },
        {
          "type": "command",
          "command": "python3 $HOME/.claude/channels/discord/text-inbox-watcher.py",
          "asyncRewake": true
        }
      ]
    }],
    "PostToolUse": [
      {
        "matcher": "mcp__discord-voice__voice_play",
        "hooks": [{
          "type": "command",
          "command": "python3 $HOME/.claude/channels/discord/voice-inbox-watcher.py",
          "asyncRewake": true
        }]
      },
      {
        "matcher": "mcp__discord-voice__reply",
        "hooks": [{
          "type": "command",
          "command": "python3 $HOME/.claude/channels/discord/voice-inbox-watcher.py",
          "asyncRewake": true
        }]
      }
    ],
    "Stop": [{
      "hooks": [
        {
          "type": "command",
          "command": "python3 $HOME/.claude/channels/discord/text-poll.py",
          "asyncRewake": true
        },
        {
          "type": "command",
          "command": "python3 $HOME/.claude/channels/discord/voice-poll.py",
          "asyncRewake": true
        }
      ]
    }]
  }
}
```

Replace `VOICE_CHANNEL_ID`, `GUILD_ID`, `TEXT_CHANNEL_ID` with your actual IDs.

---

## Step 5b: Text Message Delivery Script

`~/.claude/channels/discord/text-poll.py` — delivers Discord text messages to Claude.

```python
#!/usr/bin/env python3
import os, json, glob, sys

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'text-inbox')

def deliver_first():
    files = sorted(glob.glob(os.path.join(inbox, '*.json')))
    if not files:
        return False
    try:
        with open(files[0]) as f:
            d = json.load(f)
        os.remove(files[0])
        att_attrs = ''
        if d.get('attachment_count'):
            att_attrs = ' attachment_count="{attachment_count}" attachments="{attachments}"'.format(**d)
        print('<channel source="discord" chat_id="{chat_id}" message_id="{message_id}" user="{user}" ts="{ts}"{att}>{content}</channel>'.format(att=att_attrs, **d))
        return True
    except Exception:
        return False

if deliver_first():
    sys.exit(2)
sys.exit(0)
```

---

## Step 5c: Voice Cloning (optional)

Voice cloning requires a GPU-powered Qwen3-TTS API server. See the [Voice Cloning section in README](../README.md#voice-cloning-optional) for details.

Add to `~/.claude/channels/discord/.env`:
```env
VOICE_CLONE_SERVER=http://YOUR_GPU_SERVER:8880
```

Reference audio clips go in `~/projects/voice-refs/` — use `voice_clone_create` tool to register new voices.

---

## Step 6: server.ts — Key Implementation Points

Your `server.ts` plugin must do the following for voice receive to work:

### 6a. Write to voice-inbox on ASR result

Inside `processVoiceQueue()`, after getting a transcription:
```typescript
import { mkdirSync, writeFileSync } from 'fs'
import { join } from 'path'

const inboxDir = join(STATE_DIR, 'voice-inbox')
mkdirSync(inboxDir, { recursive: true })
writeFileSync(join(inboxDir, `${Date.now()}.json`), JSON.stringify({
  content: transcription,
  chat_id: session.textChannelId,
  message_id: `voice-${Date.now()}`,
  user: username,
  ts: new Date().toISOString(),
}))
```

### 6b. DAVE encryption — wait for 2nd transitioned event

Discord uses DAVE E2E encryption on voice channels. The `transitioned` event with id=0 fires **twice**:
1. `DavePrepareTransition` — key exchange starting, NOT ready
2. `DaveMlsAnnounceCommitTransition` or `DaveMlsWelcome` — ready for decryption

Wait for the **second** occurrence before starting the receive pipeline:
```typescript
await new Promise<void>((resolve) => {
  let resolved = false
  const timeout = setTimeout(() => {
    if (resolved) return
    resolved = true
    connection.off('transitioned', onTransitioned)
    resolve()
  }, 8000)  // fallback for non-MLS channels
  let count = 0
  function onTransitioned(id: number) {
    if (id !== 0) return
    if (++count >= 2) {
      if (resolved) return
      resolved = true
      clearTimeout(timeout)
      connection.off('transitioned', onTransitioned)
      resolve()
    }
  }
  connection.on('transitioned', onTransitioned)
})
```

### 6c. Bun ABI compatibility fix for @discordjs/opus

Bun uses ABI v137 but the `@discordjs/opus` prebuild is for v141. Without this fix, Opus decode fails silently (no audio). Add this near the top of `server.ts`:

```typescript
import { readdirSync, symlinkSync, existsSync } from 'fs'
import { resolve, dirname } from 'path'

try {
  const opusPrebuild = dirname(require.resolve('@discordjs/opus/prebuild'))
  const dirs = readdirSync(opusPrebuild)
  const v141 = dirs.find(d => d.includes('node-v141'))
  const v137 = v141?.replace('v141', 'v137')
  if (v141 && v137 && !existsSync(resolve(opusPrebuild, v137))) {
    symlinkSync(resolve(opusPrebuild, v141), resolve(opusPrebuild, v137))
  }
} catch {}
```

### 6d. Always set `daveEncryption: true`

```typescript
const connection = joinVoiceChannel({
  channelId,
  guildId,
  adapterCreator: guild.voiceAdapterCreator,
  selfDeaf: false,
  selfMute: false,
  daveEncryption: true,
} as any)
```

### 6e. Re-subscribe on close

After each utterance ends (silence timeout), the audio stream closes. Re-subscribe:
```typescript
subscription.on('close', () => {
  if (voiceSessions.has(session.guildId)) {
    setupUserSubscription(session, userId)
  }
})
```

---

## Step 7: Claude Code Behavior Rules

Add to your `CLAUDE.md` or system prompt so Claude responds correctly:

```
Voice/TTS behavior:
- source="voice" message → respond with voice_play only (no text reply)
- source="discord" message → respond with text reply only (no voice)
- English speech → voice: en-US-GuyNeural
- Korean speech → voice: ko-KR-InJoonNeural at 1.3x speed
- Clone voices available: use clone="name" param on voice_play
```

---

## How It Works End-to-End

```
User speaks in voice channel
  ↓
Discord → bot receives Opus packets (DAVE-decrypted)
  ↓
Silence detected (1.5s) → stream ends
  ↓
Opus → PCM decode → WAV file
  ↓
ASR model (Qwen3 / Whisper) → transcription text
  ↓
Written to ~/.claude/channels/discord/voice-inbox/TIMESTAMP.json
  ↓
voice-inbox-watcher.py (running in background) finds file
  ↓
Prints <channel source="voice" ...> tag → exits 2
  ↓
asyncRewake injects as new Claude turn
  ↓
Claude responds via voice_play
  ↓
PostToolUse hook starts new voice-inbox-watcher.py
  ↓
Loop continues
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Bot joins but no transcription | Check ASR model path, ffmpeg installed, Python venv |
| "notification sent OK" but no Claude response | Voice-inbox watcher not running — call voice_play once to start it |
| Multiple bot instances / reconnect loop | Run `ps aux \| grep server.ts` — kill duplicates; check only one plugin enabled |
| Audio garbled / DAVE not decrypting | Verify `daveEncryption: true` and waiting for 2nd `transitioned` event |
| Watcher not starting | Check PostToolUse hook in settings.json and that script path is correct |
| Opus decode silent failure (Bun) | Run the ABI symlink fix in Step 6c — Bun v137 needs symlink to v141 prebuild |
