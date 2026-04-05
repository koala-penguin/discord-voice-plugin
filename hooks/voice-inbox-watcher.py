#!/usr/bin/env python3
"""
PostToolUse hook for voice_play — runs asynchronously in the background.
Waits up to 60 seconds for the next queued voice message, then exits 2
to inject it as a new turn (asyncRewake). Each voice_play call kicks off
a new watcher, keeping the voice conversation alive without text input.
"""
import os, json, glob, sys, time

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'voice-inbox')
WAIT_FILE = os.path.join(inbox, '00_wait.json')
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

# Write our PID so a newer watcher can kill us (avoid duplicates)
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

# Poll for up to 10 minutes, then exit cleanly (avoids orphan if session dies)
for _ in range(600):
    time.sleep(1)
    # Exit if superseded by a newer watcher
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

# Timed out — clean up PID file if still ours
try:
    if int(open(WATCHER_PID_FILE).read().strip()) == my_pid:
        os.remove(WATCHER_PID_FILE)
except Exception:
    pass
sys.exit(0)
