#!/usr/bin/env python3
"""Find duplicate candidates in state/spott_candidates.jsonl by LinkedIn slug, email, phone, then full name.
Writes state/dup_groups.csv (one row per group; oldest record = keep)."""
import json, re, csv, unicodedata, collections, os
S = os.path.join(os.path.dirname(__file__), "..", "state")
C = [json.loads(l) for l in open(os.path.join(S, "spott_candidates.jsonl"))]
def norm(s): return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()
def slug(u): m = re.search(r"linkedin\.com/in/([^/?#]+)", u or "", re.I); return m.group(1).lower().rstrip("/") if m else None
parent = {c["id"]: c["id"] for c in C}
def find(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
why = collections.defaultdict(set)
def union(ids, reason):
    ids = list(ids)
    for i in ids[1:]:
        a, b = find(ids[0]), find(i)
        if a != b: parent[b] = a
    for i in ids: why[i].add(reason)
keys = collections.defaultdict(list)
for c in C:
    for u in c["linkedin"]:
        if slug(u): keys[("linkedin", slug(u))].append(c["id"])
    for e in c["emails"]:
        if e and "example@" not in e: keys[("email", e.lower())].append(c["id"])
    for p in c["phones"]:
        d = re.sub(r"\D", "", p or "")
        if len(d) >= 9: keys[("phone", d[-9:])].append(c["id"])
    n = norm(f"{c['first']} {c['last']}").split()
    if len(n) >= 2: keys[("name", n[0] + " " + n[-1])].append(c["id"])
    if len(n) >= 2 and c.get("title"):   # nickname variants (Dan/Daniel) with the same current title
        keys[("name", n[0][:3] + " " + n[-1] + "|" + norm(c["title"]))].append(c["id"])
for (kind, v), ids in keys.items():
    if len(set(ids)) > 1: union(set(ids), kind)
groups = collections.defaultdict(list)
byid = {c["id"]: c for c in C}
for c in C: groups[find(c["id"])].append(c)
rows = []
for g in groups.values():
    if len(g) < 2: continue
    g.sort(key=lambda c: c["created"])
    reasons = set().union(*(why[c["id"]] for c in g))
    strength = "strong" if reasons & {"linkedin", "email", "phone"} else "name_only"
    rows.append([strength, "|".join(sorted(reasons)), f"{g[0]['first']} {g[0]['last']}", g[0]["id"],
                 ";".join(c["id"] for c in g[1:]), ";".join(f"{c['first']} {c['last']} / {c['title']} @ {c['company']}" for c in g)])
rows.sort()
with open(os.path.join(S, "dup_groups.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["strength", "matched_on", "name", "keep_id(oldest)", "duplicate_ids", "records"]); w.writerows(rows)
print("groups:", len(rows), collections.Counter(r[0] for r in rows), "extra records:", sum(len(r[4].split(";")) for r in rows))
