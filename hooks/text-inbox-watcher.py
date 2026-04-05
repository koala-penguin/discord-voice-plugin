#!/usr/bin/env python3
"""
Persistent text message watcher — started from SessionStart hook.
Runs indefinitely, polling text-inbox/ every 2 seconds.
Delivers Discord text messages to Claude via asyncRewake.

PID file prevents duplicates — new watcher kills old one.
"""
import os, json, glob, sys, time, signal

text_inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'text-inbox')
PID_FILE = os.path.join(text_inbox, '00_text_watcher.pid')

os.makedirs(text_inbox, exist_ok=True)

# Kill old watcher if running
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
    # Exit if superseded by a newer watcher
    try:
        current_pid = int(open(PID_FILE).read().strip())
        if current_pid != my_pid:
            sys.exit(0)
    except Exception:
        pass
    if deliver_first():
        sys.exit(2)
