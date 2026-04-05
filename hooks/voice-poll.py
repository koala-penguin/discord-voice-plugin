#!/usr/bin/env python3
"""
Stop hook: delivers queued ASR transcriptions to Claude via asyncRewake.

Normal mode: polls up to 5s for a message.
Listening mode: after a voice message is delivered, a 30s wait marker is
written so the NEXT Stop hook invocation polls for up to 30s. This keeps
the voice conversation alive without requiring the user to type.
"""
import os, json, glob, sys, time

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'voice-inbox')
WAIT_FILE = os.path.join(inbox, '00_wait.json')  # sorts first, won't be mistaken for a message

def write_wait_marker(seconds=30):
    os.makedirs(inbox, exist_ok=True)
    with open(WAIT_FILE, 'w') as f:
        json.dump({'__wait__': True, 'expires': time.time() + seconds}, f)

def check_wait_marker():
    """Return True if listening mode is still active."""
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
    """Deliver the oldest real message. Returns True if delivered."""
    files = sorted(f for f in glob.glob(os.path.join(inbox, '*.json'))
                   if not os.path.basename(f).startswith('00_'))
    if not files:
        return False
    try:
        with open(files[0]) as f:
            d = json.load(f)
        os.remove(files[0])
        # Re-arm listening mode for 30s after delivery
        write_wait_marker(30)
        print('<channel source="voice" chat_id="{chat_id}" message_id="{message_id}" user="{user}" ts="{ts}">{content}</channel>'.format(**d))
        return True
    except Exception:
        return False

# Instant check
if deliver_first():
    sys.exit(2)

# No inbox dir = not in voice mode, exit fast
if not os.path.isdir(inbox):
    sys.exit(0)

# Determine poll window: 30s in listening mode, 5s otherwise
poll_secs = 30 if check_wait_marker() else 5

for _ in range(poll_secs):
    time.sleep(1)
    if deliver_first():
        sys.exit(2)

sys.exit(0)
