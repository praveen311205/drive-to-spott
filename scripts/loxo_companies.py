#!/usr/bin/env python3
"""Loxo companies + contacts -> Spott (REST API, no AI). Usage: loxo_companies.py [--dry]
Companies: match existing Spott companies by domain, then name (never overwrite; only lift the default stage "Lead").
  Stage: Customer = Loxo "Current Client" (Oper, Satispay); Lost Customer = a role was worked in Loxo; else Lead.
  Companies that only had test jobs (Google, Lovable, writer) are skipped. Companies only known from a contact's
  current company are created as Lead.
Contacts: attached to their company. People already in Spott as candidates (match by Loxo import, LinkedIn or email)
  become contacts of that record (keepShowingAsCandidate), others are created as new contacts. No company -> review.
Log: state/loxo/company_log.jsonl (resumable)."""
import json, os, re, sys, time, collections, urllib.request
from urllib.parse import urlparse
S = os.path.join(os.path.dirname(__file__), "..", "state"); L = os.path.join(S, "loxo")
API = "https://api.gospott.com"; NAVIN = "user_3LKSME63LBqHEQAVSj1tyQJCgyf"; DRY = "--dry" in sys.argv
STAGE = {"Lead": "b5d055dc-864b-4dc7-b04f-df7f4492667f", "Customer": "3879aeb6-23ff-4c3c-bbfd-3bdf5816d855",
         "Lost Customer": "51a601fd-32a2-4f0c-b931-2450b75373b4"}
TEST_ONLY = {"google", "lovable", "writer"}


def call(m, p, b=None):
    if DRY and m != "GET": return {"id": "DRY"}
    for a in range(7):
        try:
            r = urllib.request.urlopen(urllib.request.Request(API + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                                       headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"}), timeout=60).read()
            time.sleep(0.35)
            if not r: return {}
            try: return json.loads(r)
            except ValueError:
                mm = re.search(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r)
                return {"id": mm.group(0).decode()} if mm else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < 6: time.sleep(5 * 2 ** a); continue
            raise RuntimeError(f"{m} {p} -> {e.code} {e.read()[:250].decode(errors='ignore')}")


SUFFIX = r"(\.|\s|,)*(inc|incorporated|gmbh|ltd|limited|llc|bv|b\.v|sas|sa|ag|ab|as|oy|plc|co|corp|company|group|holding|io|ai|app|hq|tech|technologies|labs|com|de|fr|eu|net|org|nl|se|uk)\.?$"
def norm(s):
    s = (s or "").lower().strip()
    for _ in range(2): s = re.sub(SUFFIX, "", s).strip(" .,")
    return re.sub(r"[^a-z0-9]", "", s)
def dom(u):
    if not u: return None
    u = u if "://" in u else "http://" + u
    d = urlparse(u).netloc.lower().removeprefix("www.")
    return d if d and "." in d and "linkedin.com" not in d else None
def slug(u):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", u or "", re.I); return m.group(1).lower().rstrip("/") if m else None
def e164(p):
    d = re.sub(r"[^\d+]", "", p or ""); d = "+" + d[2:] if d.startswith("00") else d
    return d if d.startswith("+") and 10 <= len(d) <= 16 else None
def proper(s): return s.title() if s and (s.isupper() or s.islower()) else s

LC = json.load(open(f"{L}/companies.json")); LJ = json.load(open(f"{L}/jobs.json"))
SC = json.load(open(f"{S}/spott_clients.json"))
sp_dom = {(c.get("domain") or {}).get("domain"): c for c in SC if (c.get("domain") or {}).get("domain")}
sp_name = {norm(c["name"]["name"]): c for c in SC}
worked = {(j.get("company") or {}).get("id") for j in LJ if "test" not in (j.get("title") or "").lower()}
people = json.load(open(f"{L}/people.json"))
contacts = [p for p in people if any(t.get("name") == "Contact" for t in p.get("person_types") or [])]
cand_of = {}
for f in sorted(os.listdir(L)):
    if f.startswith("import_log") and "dry" not in f:
        for l in open(f"{L}/{f}"):
            x = json.loads(l)
            if x["status"] == "ok": cand_of[x["loxo_id"]] = x["candidate_id"]
SPC = [json.loads(l) for l in open(f"{S}/spott_candidates.jsonl")]
by_li = {slug(u): c["id"] for c in SPC for u in c["linkedin"] if slug(u)}
by_em = {e.lower(): c["id"] for c in SPC for e in c["emails"]}

logp = f"{L}/company_log{'_dry' if DRY else ''}.jsonl"
done = {}
if os.path.exists(logp):
    for l in open(logp):
        x = json.loads(l)
        if x["status"] == "ok": done[x["key"]] = x
log = open(logp, "a"); stats = collections.Counter()
def write(rec): log.write(json.dumps(rec) + "\n"); log.flush(); stats[f"{rec['kind']}:{rec['status']}:{rec.get('how','')}"] += 1

# 1. companies (Loxo list + contacts' companies)
targets = {}
for c in LC:
    if norm(c["name"]) in TEST_ONLY: continue
    st = (c.get("company_global_status") or {}).get("name")
    stage = "Customer" if st == "Current Client" else ("Lost Customer" if c["id"] in worked else "Lead")
    targets[norm(c["name"])] = {"name": c["name"], "domain": dom(c.get("url")), "description": (c.get("description") or "")[:1500] or None, "stage": stage, "src": "loxo company"}
for p in contacts:
    n = norm(p.get("current_company"))
    if n and n not in targets and n not in TEST_ONLY:
        targets[n] = {"name": p["current_company"].strip(), "domain": None, "description": None, "stage": "Lead", "src": "contact's company"}
client_id = {}
for n, t in targets.items():
    key = "co:" + n
    if key in done: client_id[n] = done[key]["id"]; continue
    rec = {"key": key, "kind": "company", "name": t["name"], "stage": t["stage"], "status": "ok", "how": None, "id": None, "issues": ""}
    try:
        ex = sp_dom.get(t["domain"]) or sp_name.get(n) or (sp_name.get(norm(t["domain"])) if t["domain"] else None)
        if ex:
            rec["id"], rec["how"] = ex["id"], "existing"
            cur = ((ex.get("stage") or {}).get("stage") or {}).get("name") if isinstance(ex.get("stage"), dict) else None
            if t["stage"] != "Lead" and cur in (None, "Lead"):
                call("PATCH", f"/clients/{ex['id']}", {"stageId": STAGE[t["stage"]]}); rec["how"] = f"existing, stage {cur}->{t['stage']}"
        else:
            body = {"name": t["name"], "description": t["description"] or "", "domain": t["domain"], "foundedYear": None,
                    "industry": None, "size": None, "specialties": []}   # the live API requires these keys
            try: rec["id"] = call("POST", "/clients", body).get("id")
            except RuntimeError as e:
                if "domain" in str(e): body["domain"] = None; rec["id"] = call("POST", "/clients", body).get("id"); rec["issues"] += " domain rejected;"
                else: raise
            rec["how"] = "created"
            if t["stage"] != "Lead": call("PATCH", f"/clients/{rec['id']}", {"stageId": STAGE[t["stage"]]})
        client_id[n] = rec["id"]
    except Exception as e: rec["status"] = "error"; rec["issues"] += str(e)[:250]
    write(rec)

# 2. contacts
for p in contacts:
    key = f"ct:{p['id']}"
    if key in done: continue
    n = norm(p.get("current_company"))
    rec = {"key": key, "kind": "contact", "name": p.get("name"), "company": p.get("current_company"), "status": "ok", "how": None, "id": None, "issues": ""}
    try:
        if not n or n in TEST_ONLY or not client_id.get(n):
            rec["status"], rec["issues"] = "review", "no company in Loxo"; write(rec); continue
        emails = [e["value"].strip() for e in p.get("emails") or [] if "@" in (e.get("value") or "")]
        cid = cand_of.get(p["id"]) or by_li.get(slug(p.get("linkedin_url"))) or next((by_em[e.lower()] for e in emails if e.lower() in by_em), None)
        role = (p.get("current_title") or "")[:200] or None
        if cid:
            body = {"clientId": client_id[n], "keepShowingAsCandidate": True}
            if role: body["role"] = role
            try: rec["id"] = call("POST", f"/candidates/{cid}/contacts", body).get("id"); rec["how"] = "existing candidate linked"
            except RuntimeError as e:
                if "409" in str(e) or "already" in str(e).lower(): rec["how"] = "already a contact"; rec["id"] = cid
                else: raise
        else:
            first, last = proper(p.get("first_name")), proper(p.get("last_name"))
            if not (first and last):
                parts = [x for x in (p.get("name") or "").split() if "@" not in x]
                if len(parts) >= 2: first, last = proper(parts[0]), proper(" ".join(parts[1:]))
            if not (first and last) or re.search(r"[\d@]", (first or "") + (last or "")):
                rec["status"], rec["issues"] = "review", "no usable name"; write(rec); continue
            body = {"firstName": first, "lastName": last, "mainContact": {"userId": NAVIN}}
            if role: body["role"] = role
            if emails: body["emails"] = [{"email": e, "purpose": "work" if not any(x in e for x in ("gmail", "hotmail", "yahoo", "outlook")) else "personal", "isPrimary": i == 0} for i, e in enumerate(emails[:3])]
            ph = [x for x in (e164(y.get("value")) for y in p.get("phones") or []) if x]
            if ph: body["phoneNumbers"] = [{"phoneNumber": x, "purpose": "work", "isPrimary": i == 0} for i, x in enumerate(ph[:2])]
            if slug(p.get("linkedin_url")): body["socialMedia"] = [{"url": "https://www.linkedin.com/in/" + slug(p["linkedin_url"]), "type": "LINKEDIN"}]
            try: rec["id"] = call("POST", f"/clients/contacts/{client_id[n]}", body).get("id"); rec["how"] = "created"
            except RuntimeError as e:
                if "409" in str(e):          # email/phone already on someone: create without the conflicting identifiers
                    body.pop("emails", None); body.pop("phoneNumbers", None)
                    rec["id"] = call("POST", f"/clients/contacts/{client_id[n]}", body).get("id"); rec["how"] = "created"
                    rec["issues"] += f" contact details already on another record, not added: {str(e)[60:200]};"
                elif "phoneNumber" in str(e):
                    body.pop("phoneNumbers", None); rec["id"] = call("POST", f"/clients/contacts/{client_id[n]}", body).get("id"); rec["how"] = "created"; rec["issues"] += " invalid phone dropped;"
                else: raise
    except Exception as e: rec["status"] = "error"; rec["issues"] += str(e)[:250]
    write(rec)
print(dict(stats))
