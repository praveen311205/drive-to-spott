#!/usr/bin/env python3
"""Build state/attach_queue.jsonl from (1) extraction outputs state/extract/*.jsonl and (2) the candidate items in
state/review_decisions.jsonl (Drive triage: Gemini call notes, untitled screening docs). Sensitive, client and
internal items are never queued. Candidate lists and references go to state/review_items.jsonl for the report."""
import json, glob, os
S = os.path.join(os.path.dirname(__file__), "..", "state")
q, review = [], []
mod = {}
for f in ("inv_cv.jsonl", "inv_mig.jsonl"):
    for l in open(os.path.join(S, f)):
        d = json.loads(l); mod[d["id"]] = (d.get("modifiedTime") or "")[:10]
for f in sorted(glob.glob(os.path.join(S, "extract", "*.jsonl"))):
    for l in open(f):
        if l.strip():
            it = json.loads(l); it.setdefault("source_label", "Doc")
            if not it.get("conversation_date"):
                it["conversation_date"] = max((mod.get(i, "") for i in it.get("file_ids") or []), default="") or None
            q.append(it)
for l in open(os.path.join(S, "review_decisions.jsonl")):
    r = json.loads(l)
    k = r.get("kind")
    if k in ("candidate_screening", "candidate_call"):
        nm = (r.get("person_name") or "").split()
        lines = [x.strip(" -•") for x in (r.get("summary") or "").split("\n") if x.strip()]
        if len(lines) == 1: lines = [x.strip() + "." for x in lines[0].split(". ") if x.strip()]
        fields = {k2: v for k2, v in (r.get("fields") or {}).items() if v not in (None, "", [])}
        q.append({"key": "review:" + r["file_id"], "file_ids": [r["file_id"]], "first_name": nm[0] if len(nm) >= 2 else None,
                  "last_name": " ".join(nm[1:]) if len(nm) >= 2 else None, "linkedin": r.get("linkedin"),
                  "emails": [r["email"]] if r.get("email") else [], "phones": [],
                  "conversation_date": r.get("conversation_date") or mod.get(r["file_id"]),
                  "date_from_modified": not r.get("conversation_date"),
                  "force_uncertain": r.get("match_confidence") == "low", "note": lines[:5], "fields": fields,
                  "spott_candidate_id": r.get("spott_candidate_id") if r.get("match_confidence") == "high" else None,
                  "source_label": "call" if k == "candidate_call" else "Doc",
                  "issues": ("low-confidence match; " if r.get("match_confidence") == "low" else "") + (r.get("notes") or "")[:200],
                  "title": r.get("title")})
    elif k in ("candidate_list", "reference", "sensitive"):
        review.append({"file_id": r["file_id"], "title": r.get("title"), "kind": k, "person_name": r.get("person_name"),
                       "notes": (r.get("notes") or "")[:600] if k != "sensitive" else "not copied"})
json.dump
with open(os.path.join(S, "attach_queue.jsonl"), "w") as fh:
    for it in q: fh.write(json.dumps(it) + "\n")
with open(os.path.join(S, "review_items.jsonl"), "w") as fh:
    for it in review: fh.write(json.dumps(it) + "\n")
print("queued", len(q), "| review items", len(review))
