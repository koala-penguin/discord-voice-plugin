#!/usr/bin/env python3
"""
Stop hook: delivers queued ASR transcriptions to Claude via asyncRewake.

Polls for up to 280s for a voice message. If nothing arrives, sends a
keepalive (exit 2) so the Stop hooks re-fire and the session never dies.
"""
import os, json, glob, sys, time

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'voice-inbox')
WAIT_FILE = os.path.join(inbox, '00_wait.json')
PID_FILE = os.path.join(inbox, '00_vpoll.pid')

POLL_SECS = 280  # just under the 300s idle timeout

# Kill previous instance to avoid accumulation
os.makedirs(inbox, exist_ok=True)
my_pid = os.getpid()
try:
    old_pid = int(open(PID_FILE).read().strip())
    if old_pid != my_pid:
        try: os.kill(old_pid, 9)
        except: pass
except: pass
with open(PID_FILE, 'w') as f:
    f.write(str(my_pid))

def write_wait_marker(seconds=280):
    os.makedirs(inbox, exist_ok=True)
    with open(WAIT_FILE, 'w') as f:
        json.dump({'__wait__': True, 'expires': time.time() + seconds}, f)

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
        write_wait_marker(280)
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

# Poll for messages
for _ in range(POLL_SECS):
    time.sleep(1)
    if deliver_first():
        sys.exit(2)

# Nothing arrived — send keepalive to prevent session death
print('<keepalive source="voice-poll" ts="{}"/>'.format(time.strftime('%Y-%m-%dT%H:%M:%S')))
sys.exit(2)
