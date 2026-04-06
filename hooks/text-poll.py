#!/usr/bin/env python3
"""
Stop hook: delivers queued Discord text messages to Claude via asyncRewake.

Polls for up to 280s so text messages are caught even while voice-poll is
also running. No keepalive — voice-poll handles that.
"""
import os, json, glob, sys, time

inbox = os.path.join(os.path.expanduser('~'), '.claude', 'channels', 'discord', 'text-inbox')

POLL_SECS = 280

def deliver_first():
    """Deliver the oldest message. Returns True if delivered."""
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

# Instant check
if deliver_first():
    sys.exit(2)

# Poll for messages
for _ in range(POLL_SECS):
    time.sleep(1)
    if deliver_first():
        sys.exit(2)

# No keepalive here — voice-poll handles session keep-alive
sys.exit(0)
