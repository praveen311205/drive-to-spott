#!/usr/bin/env python3
"""Dry run: match Metaview conversations (with 'Migration –' AI fields) to Spott records -> state/metaview/plan.jsonl.
Candidate calls -> candidate by email, else unique full name. Client calls / role intakes -> company by name.
Parses pay ('90K' -> 90000) only when a currency is stated."""
import json, re, collections, os, unicodedata
S = os.path.join(os.path.dirname(__file__), "..", "state"); D = os.path.join(S, "metaview")
AI = json.load(open(f"{D}/ai_fields.json")); C = json.load(open(f"{D}/ai_conversations.json"))
v = lambda c, n: ((c["fields"].get(AI[n]) or [{}])[0].get("value") or "").strip()
def norm(s): return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()
cands = [json.loads(l) for l in open(f"{S}/spott_candidates.jsonl")]
by_em = {e.lower(): c["id"] for c in cands for e in c["emails"]}
by_li = {re.search(r"/in/([^/?#]+)", u).group(1).lower(): c["id"] for c in cands for u in c["linkedin"] if re.search(r"/in/([^/?#]+)", u)}
by_nm = collections.defaultdict(set)
for c in cands:
    n = norm(f"{c['first']} {c['last']}").split()
    if len(n) >= 2: by_nm[n[0] + " " + n[-1]].add(c["id"])
clients = json.load(open(f"{S}/spott_clients.json"))
cn = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(r"\b(inc|gmbh|ltd|ai|io|hq|sas|bv|ag|group)\b", "", (s or "").lower()))
by_co = {cn(c["name"]["name"]): c["id"] for c in clients}
def money(s):
    m = re.search(r"([\d.,]+)\s*([kKmM])?", s or "")
    if not m: return None
    x = float(m.group(1).replace(",", "")); x *= 1000 if (m.group(2) or "").lower() == "k" else (1e6 if (m.group(2) or "").lower() == "m" else 1)
    return x if 10000 <= x <= 2000000 else None
out, st = [], collections.Counter()
for cid, c in C.items():
    typ = (v(c, "Migration – Call type").split() or ["EMPTY"])[0]
    date = ((c["fields"].get("default:start_time") or [{}])[0].get("value") or "")[:10]
    rec = {"conv": cid, "url": c.get("url"), "date": date, "type": typ, "title": ((c["fields"].get("default:calendar_event_title") or [{}])[0].get("label") or "")}
    if typ.startswith("CANDIDATE"):
        p = (c["fields"].get("default:candidate") or [{}])[0]
        name = (p.get("details") or {}).get("name") or p.get("label") or ""; emails = [e.lower() for e in (p.get("details") or {}).get("emails") or []]
        fn = v(c, "Migration – Candidate full name") if "Migration – Candidate full name" in AI else ""
        full, li = (fn.split("|") + ["", ""])[:2]
        full = full.strip(); li = li.strip()
        if full and full.upper() not in ("UNKNOWN", "N/A") and len(norm(full).split()) >= 2 and len(norm(name).split()) < 2: name = full
        rec["linkedin"] = li if "linkedin.com/in/" in li else None
        rec.update(name=name, emails=emails, note=[x.strip(" -•") for x in v(c, "Migration – CRM note").splitlines() if x.strip() and x.strip() != "N/A"][:5],
                   how=v(c, "Migration – How we found them"))
        det = {}
        for line in v(c, "Migration – Candidate details").splitlines():
            if ":" in line: k, val = line.split(":", 1); det[k.strip().lower()] = val.strip()
        cur = (det.get("currency") or "").upper()
        f = {}
        if cur in ("EUR", "GBP", "USD", "CHF", "SEK", "DKK", "NOK", "PLN"):
            f["currency"] = cur
            for a, b in (("current_base", "base"), ("current_ote", "ote")):
                if money(det.get(a)): f[b] = money(det[a])
        for k in ("notice_period", "work_setup", "work_rights", "status", "next_step", "languages"):
            if det.get(k) and det[k].upper() != "N/A": f[k] = det[k]
        if det.get("rip_and_replace", "").lower().startswith("yes"):
            f["rip_and_replace"] = True
            if det.get("incumbent"): f["rip_and_replace_incumbent"] = det["incumbent"]
        rec["fields"] = f
        hit = next((by_em[e] for e in emails if e in by_em), None); how = "email" if hit else None
        lm = re.search(r"/in/([^/?#]+)", rec.get("linkedin") or "")
        if not hit and lm and lm.group(1).lower() in by_li: hit, how = by_li[lm.group(1).lower()], "linkedin"
        n = norm(name).split()
        if not hit and len(n) >= 2 and len(by_nm.get(n[0] + " " + n[-1], ())) == 1: hit, how = next(iter(by_nm[n[0] + " " + n[-1]])), "name"
        rec.update(candidate_id=hit, matched_on=how)
        if hit: act = "candidate: matched by " + how
        elif len(n) >= 2 and emails: act = "candidate: new (full name + email)"
        elif emails: act = "candidate: new but first name only"
        else: act = "candidate: unidentified"
    elif typ in ("CLIENT_CALL", "ROLE_INTAKE"):
        cr = v(c, "Migration – Company and role"); co = cr.split("|")[0].strip()
        rec.update(company=co, company_note=cr, company_id=by_co.get(cn(co)))
        act = "company: matched" if rec["company_id"] else "company: not in Spott"
    else: act = f"skip: {typ}"
    rec["action"] = act; st[act] += 1; out.append(rec)
with open(f"{D}/plan.jsonl", "w") as fh:
    for r in out: fh.write(json.dumps(r) + "\n")
for k, n in sorted(st.items()): print(f"{n:5}  {k}")
