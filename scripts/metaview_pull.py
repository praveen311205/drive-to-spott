#!/usr/bin/env python3
"""Pull Metaview candidate conversations (Job Interview + Candidate Debrief) with candidate, emails, date, client, job
title and AI summary into state/metaview/conversations.json. Re-requests until summaries are ready."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from mv_client import tool
OUT = os.path.join(os.path.dirname(__file__), "..", "state", "metaview", "conversations.json")
TYPES = ["22eae796-087b-11ef-9815-5f761d7a35b3", "386f3400-087b-11ef-9816-335c9f345f49"]
F = ["default:candidate", "default:start_time", "default:summary", "OSPT:dc97a97a-08f8-11f1-9bba-abf885ce5e94",
     "OSPT:5610c000-a82b-11ef-89d6-1f8b46e09485", "default:calendar_event_title", "default:phone_number"]
conv = json.load(open(OUT)) if os.path.exists(OUT) else {}
for rnd in range(12):
    off, pending = 0, 0
    while True:
        r = json.loads(tool("search_conversations", {"filters": [{"id": "default:conversation_type", "operation": "is_one_of", "value": TYPES}],
                                                     "fields": F, "limit": 50, "offset": off, "sort_by": "default:start_time", "sort_ascending": False}))
        for c in r["conversations"]:
            old = conv.get(str(c["id"]))
            if not old or not old["fields"].get("default:summary"): conv[str(c["id"])] = c
        pending += (r.get("ai_processing") or {}).get("default:summary", {}).get("pending_count", 0)
        off += 50
        if not r.get("has_more"): break
    json.dump(conv, open(OUT, "w"))
    ready = sum(1 for c in conv.values() if c["fields"].get("default:summary"))
    print(f"round {rnd}: {len(conv)} conversations, {ready} with summary, pending {pending}", flush=True)
    if ready == len(conv) or pending == 0: break
    time.sleep(90)
