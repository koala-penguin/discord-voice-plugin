# Discord Voice Receive Fix — Implementation Notes
_2026-04-05_

## Problem

Voice receive (ASR transcription → Claude response) was broken in CLI mode. The plugin correctly transcribed speech and sent MCP push notifications (`mcp.notification()`), but Claude Code CLI does not deliver MCP push notifications as conversation turns while the session is active. They were silently dropped.

## Root Cause

`notifications/claude/channel` MCP push notifications work in the desktop app but not in the terminal CLI. In the CLI, new turns can only be triggered by:
1. User typing in the terminal
2. Hook `asyncRewake` (hooks that exit code 2 inject their stdout as a new turn)

## Solution Overview

Three-part fix:

1. **server.ts** — write each transcription to a queue file in addition to MCP notification
2. **`voice-poll.py`** — Stop hook: instant check + 30s poll if listening mode active
3. **`voice-inbox-watcher.py`** — PostToolUse hook on `voice_play`: background 10-min listener that creates a self-sustaining voice loop

---

## Part 1: server.ts — Voice Inbox Queue

In `processVoiceQueue()`, after ASR produces a transcription, write it to a file:

```typescript
const inboxDir = join(STATE_DIR, 'voice-inbox')
mkdirSync(inboxDir, { recursive: true })
const queueFile = join(inboxDir, `${Date.now()}.json`)
writeFileSync(queueFile, JSON.stringify({
  content: transcription,
  chat_id: session.textChannelId,
  message_id: `voice-${Date.now()}`,
  user: username,
  ts: new Date().toISOString(),
}))
```

Files land at `~/.claude/channels/discord/voice-inbox/TIMESTAMP.json`.

The existing `mcp.notification()` call is kept as a fallback for desktop app users.

---

## Part 2: voice-poll.py — Stop Hook

**Location:** `~/.claude/channels/discord/voice-poll.py`

Runs after every Claude turn (Stop hook). Does an instant check for queued messages. If the 30-second "listening mode" wait marker is active (written by the watcher when it delivers a message), polls for up to 30 seconds.

**settings.json Stop hook:**
```json
"Stop": [{
  "hooks": [{
    "type": "command",
    "command": "python3 $HOME/.claude/channels/discord/voice-poll.py",
    "asyncRewake": true
  }]
}]
```

This handles messages that arrive during an active text turn.

---

## Part 3: voice-inbox-watcher.py — PostToolUse Hook (main fix)

**Location:** `~/.claude/channels/discord/voice-inbox-watcher.py`

The key fix. Triggered via `PostToolUse` on `mcp__discord-voice__voice_play` with `asyncRewake: true` — runs **asynchronously in the background**, not blocking the session.

**How it works:**
1. Every time Claude calls `voice_play`, this script starts in the background
2. It polls `voice-inbox/` every second for up to 10 minutes
3. When a voice message arrives, it prints the `<channel source="voice" ...>` tag and exits 2
4. `asyncRewake` injects this as a new turn → Claude responds via `voice_play` → new watcher starts
5. Creates a self-sustaining loop for the entire voice conversation

**PID file** (`00_watcher.pid`): if a new watcher starts (new `voice_play` call) while the old one is still running, the new watcher kills the old one. Only one watcher runs at a time.

**Timeout:** 10 minutes. Prevents orphan processes if Claude crashes. Long enough to cover any natural pause in conversation.

**settings.json PostToolUse hook:**
```json
"PostToolUse": [{
  "matcher": "mcp__discord-voice__voice_play",
  "hooks": [{
    "type": "command",
    "command": "python3 $HOME/.claude/channels/discord/voice-inbox-watcher.py",
    "asyncRewake": true
  }]
}]
```

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.claude/plugins/lib/discord-voice/server.ts` | Plugin — writes to voice-inbox on ASR result |
| `~/.claude/channels/discord/voice-inbox/` | Queue directory for transcriptions |
| `~/.claude/channels/discord/voice-poll.py` | Stop hook — catches messages during text turns |
| `~/.claude/channels/discord/voice-inbox-watcher.py` | PostToolUse hook — background listener loop |
| `~/.claude/settings.json` | Hook configuration |

---

## Conversation Flow

```
User speaks
  → ASR (~2-3s after silence)
  → TIMESTAMP.json written to voice-inbox/

PostToolUse watcher (background, running)
  → finds file within 1s
  → prints <channel source="voice" ...>
  → exits 2 → asyncRewake injects new turn

Claude receives voice turn
  → calls voice_play
  → PostToolUse hook fires → new watcher starts (kills old one via PID file)
  → cycle repeats
```

## Gap: Session Idle Without Prior voice_play

If Claude has never called `voice_play` in this session (or the 10-min watcher timed out), there is no running background watcher. In this case, speak in the voice channel then type any message in text — the Stop hook will pick up the queued message on the next turn.

To restart the loop manually, call `voice_play` with any text.
