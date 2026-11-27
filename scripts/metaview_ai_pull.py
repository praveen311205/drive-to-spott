#!/usr/bin/env python3
"""Pull ALL Metaview conversations with the 'Migration –' AI fields -> state/metaview/ai_conversations.json.
Re-requests until Metaview has processed every transcript."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from mv_client import tool
D = os.path.join(os.path.dirname(__file__), "..", "state", "metaview")
AI = json.load(open(os.path.join(D, "ai_fields.json")))
F = ["default:candidate", "default:contact", "default:start_time", "default:calendar_event_title", "default:conversation_type",
     "OSPT:dc97a97a-08f8-11f1-9bba-abf885ce5e94", "OSPT:5610c000-a82b-11ef-89d6-1f8b46e09485"] + list(AI.values())
OUT = os.path.join(D, "ai_conversations.json")
conv = json.load(open(OUT)) if os.path.exists(OUT) else {}
done = lambda c: all(c["fields"].get(f) for f in AI.values())
for rnd in range(40):
    off, pending = 0, 0
    while True:
        r = json.loads(tool("search_conversations", {"filters": [], "fields": F, "limit": 50, "offset": off, "sort_by": "default:start_time", "sort_ascending": False}))
        for c in r["conversations"]:
            if not done(conv.get(str(c["id"]), {"fields": {}})): conv[str(c["id"])] = c
        pending += sum(v.get("pending_count", 0) for v in (r.get("ai_processing") or {}).values())
        off += 50
        if not r.get("has_more"): break
    json.dump(conv, open(OUT, "w"))
    ready = sum(1 for c in conv.values() if done(c))
    print(f"round {rnd}: {len(conv)} conversations, {ready} fully processed, pending {pending}", flush=True)
    if pending == 0 or ready == len(conv): break
    time.sleep(120)
