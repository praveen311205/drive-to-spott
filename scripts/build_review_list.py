#!/usr/bin/env python3
"""Consolidated review list for Praveen -> state/review_list.csv (and a dated copy in the scratchpad if given)."""
import json, csv, glob, collections, os, re, sys
S = os.path.join(os.path.dirname(__file__), "..", "state"); L = os.path.join(S, "loxo")
plan = {json.loads(l)["loxo_id"]: json.loads(l) for l in open(f"{L}/plan.jsonl")}
cid = {}
for f in sorted(glob.glob(f"{L}/import_log*.jsonl")):
    if "dry" in f: continue
    for l in open(f):
        x = json.loads(l)
        if x["status"] == "ok": cid[x["loxo_id"]] = x["candidate_id"]
deleted = {json.loads(l)["deleted"] for l in open(f"{L}/shell_deletions.jsonl")} if os.path.exists(f"{L}/shell_deletions.jsonl") else set()
rows = []
def add(sec, name, sid, issue, action): rows.append([sec, name or "", sid or "", issue, action])
for l in open(f"{L}/notes_review.jsonl"):
    r = json.loads(l)
    if isinstance(r["loxo_id"], int):
        p = plan.get(r["loxo_id"]); add("1. Loxo note not attached", p["name"] if p else "", cid.get(r["loxo_id"]), f"{r.get('date') or ''} {r['why']}".strip(), "Move to the right record/company, or ignore")
    else:
        add("2. Contact / name problem from Loxo", r["loxo_id"].title(), "", r["why"], "Set the real first name")
seen = set()
for f in sorted(glob.glob(f"{L}/import_log*.jsonl")):
    if "dry" in f: continue
    for l in open(f):
        x = json.loads(l)
        for part in (x.get("issues") or "").split(";"):
            part = part.strip()
            if "already on" in part:
                m = re.search(r"\(([0-9a-f-]{36})\)", part)
                if m and m.group(1) in deleted: continue          # conflict with a deleted empty shell: resolved
            if ("already on" in part or "invalid phone" in part) and (x["loxo_id"], part) not in seen:
                seen.add((x["loxo_id"], part)); add("2. Contact / name problem from Loxo", x["name"], x.get("candidate_id"), part, "Check which person the email/phone belongs to")
for p in plan.values():
    if p["action"] == "name_match_check":
        add("3. Same name as a Spott record, not imported", p["name"], ";".join(p["spott_ids"] or []), f"no LinkedIn/email match; last Loxo activity {p['last_activity']}", "Same person? Merge Loxo data; otherwise import as new")
att = {json.loads(l)["key"]: json.loads(l) for l in open(f"{S}/attach_log.jsonl")}
for r in att.values():
    if r["status"] == "unidentified": add("4. Drive screening note with no name", "", "", r["issues"][:200], "Navin: who is this?")
    if r["status"] == "match_uncertain": add("4. Drive note, uncertain match", r["name"], "", r["issues"][:200], "Confirm the right record")
for r in (json.loads(l) for l in open(f"{S}/review_items.jsonl")):
    add("5. Drive file", r.get("person_name") or "", "", f"{r['kind']}: {r['title']} {r.get('notes') or ''}"[:250], "Sensitive: never import. Lists/reference: decide")
add("5. Drive file", "Renato Freitas", "", "CV in Migration folder (Dec 2024); possibly the former GTM Talent freelancer (renato@gtmtalent.tech)", "Import as candidate or skip")
if os.path.exists(f"{L}/company_log.jsonl"):
    last = {}
    for l in open(f"{L}/company_log.jsonl"):
        x = json.loads(l); last[x["key"]] = x
    for x in last.values():
        if x["kind"] == "contact" and x["status"] == "review":
            add("7. Loxo contact without a company", x["name"], "", x["issues"], "Add their company in Spott, or skip")
if os.path.exists(f"{S}/metaview/apply_log.jsonl"):
    mlast = {}
    for l in open(f"{S}/metaview/apply_log.jsonl"):
        x = json.loads(l); mlast[x["conv"]] = x
    for x in mlast.values():
        if x["status"] in ("review", "error"):
            add("8. Metaview call not imported", "", "", f"{x['how'] or 'error'}: {x['issues'][:220]}",
                "Navin: who is this? (add full name) / older than 24 months: yes-no" if x["kind"] == "candidate" else "Which company?")
add("6. Small fix", "Aaron Shaw", "01a21d7d-45a6-7d8f-b3da-d28280f952ad / 01a21d7d-e7cc-726a-91a3-bae61d0b541e", "Two different people (different LinkedIn)", "Leave as is; never merge")
add("6. Small fix", "Sam Kenney-Herbert", "01a211d1-02fd-7403-94e7-fd5f2974faa8", "Two notes titled 2026-09-14 – Doc after the merge", "Delete one")
add("6. Small fix", "Ross Delahunty", "01a20d05-825c-71f0-b203-560ea87fd935", "Long pilot note in the old format", "Delete it (the new standard note is there)")
add("6. Small fix", "Edward Weeks", "01a211c8-e9c2-75e4-9eb6-ed2dca662bba / 01a211d8-585f-7884-9ae7-88bc71db53e8", "Two different people (Tipalti AE, Dataiku AE)", "Leave as is; never merge")
with open(f"{S}/review_list.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["section", "name", "spott_id", "issue", "action"]); w.writerows(rows)
if len(sys.argv) > 1:
    import shutil; shutil.copy(f"{S}/review_list.csv", sys.argv[1])
print(len(rows), dict(collections.Counter(r[0] for r in rows)))
