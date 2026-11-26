#!/usr/bin/env python3
"""Dry run: work out each candidate's ORIGINAL source (how we first came across them) from evidence, no AI.
Evidence, strongest first:
  1. note text says so: referral / inbound application / event
  2. Loxo activity shows we approached them (outreach email, InMail, 'Responded') -> headhunted;
     LinkedIn if the Loxo profile was added from LinkedIn, else Other (outbound, non-LinkedIn)
  3. Loxo profile added from LinkedIn with no other signal -> LinkedIn outreach
  else: unknown (left empty)
Writes state/source_plan.jsonl {candidate_id, source, evidence}."""
import json, re, glob, collections, os
S = os.path.join(os.path.dirname(__file__), "..", "state"); L = os.path.join(S, "loxo")
REF = re.compile(r"\b(referred (to us |to me |to navin )?by [A-Z][a-z]+|referral from [A-Z][a-z]+|recommended (to us |to me |to navin )?by [A-Z][a-z]+|(came|comes) (to us )?(via|through) (a )?referral|intro(duced)? (to us |to me |to navin )?by [A-Z][a-z]+|warm intro from [A-Z][a-z]+)")
INB = re.compile(r"\b(applied (to|for) (the|our|a|gtm|GTM)[^.\n]{0,40}(role|position|job|vacancy)|applied via (the )?(website|linkedin job|job post)|inbound application|reached out to (us|navin|gtm talent)|sent (us|navin) (his|her|their) cv|contacted (us|navin|gtm talent) (directly|about))", re.I)
EVT = re.compile(r"\b(met (him|her|them) at (an? )?(event|meetup|conference)|met at (an? )?(event|meetup|conference))", re.I)
OUT_EV = {"Sent Email", "Outreach™ Email Sent", "Sent InMail", "Responded", "Outreach™ Task Completed", "Sent LinkedIn Message", "Sent WhatsApp Message"}
P = {p["id"]: p for p in json.load(open(os.path.join(L, "people.json")))}
EV = collections.defaultdict(list)
for e in json.load(open(os.path.join(L, "person_events.json"))): EV[e["person_id"]].append(e)
plan = {json.loads(l)["loxo_id"]: json.loads(l) for l in open(os.path.join(L, "plan.jsonl"))}
texts = collections.defaultdict(list); loxo_of = {}
for f in sorted(glob.glob(os.path.join(L, "import_log*.jsonl"))):
    if "dry" in f: continue
    for l in open(f):
        x = json.loads(l)
        if x["status"] == "ok": loxo_of.setdefault(x["candidate_id"], []).append(x["loxo_id"])
for cid, lids in loxo_of.items():
    for lid in lids:
        texts[cid] += [n["text"] for n in plan[lid]["notes"]] + [plan[lid].get("loxo_description") or ""]
# Drive notes (screening docs + call notes): summary lines and extractor issues
q = {json.loads(l)["key"]: json.loads(l) for l in open(os.path.join(S, "attach_queue.jsonl"))}
for l in open(os.path.join(S, "attach_log.jsonl")):
    r = json.loads(l)
    if r.get("candidate_id") and r["key"] in q:
        it = q[r["key"]]; texts[r["candidate_id"]] += (it.get("note") or []) + [it.get("issues") or ""]
cands = [json.loads(l) for l in open(os.path.join(S, "spott_candidates.jsonl"))]
out, cnt, ex = [], collections.Counter(), collections.defaultdict(list)
for c in cands:
    cid = c["id"]; t = "\n".join(texts.get(cid, [])); src, why = None, ""
    m = REF.search(t)
    if m: src, why = "Referral", t[max(0, m.start()-60):m.end()+60]
    elif INB.search(t): m = INB.search(t); src, why = "Inbound application", t[max(0, m.start()-60):m.end()+60]
    elif EVT.search(t): m = EVT.search(t); src, why = "Event", t[max(0, m.start()-60):m.end()+60]
    else:
        lids = loxo_of.get(cid, [])
        outb = [e["activity_type"]["name"] for lid in lids for e in EV.get(lid, []) if e["activity_type"]["name"] in OUT_EV]
        li_added = any((P.get(lid, {}).get("source_type") or {}).get("name") == "LinkedIn" for lid in lids)
        if outb and li_added: src, why = "LinkedIn outreach", f"Loxo: added from LinkedIn + {len(outb)} outreach events"
        elif outb: src, why = "Other", f"Loxo: approached by us ({len(outb)} outreach events), not added from LinkedIn"
        elif li_added: src, why = "LinkedIn outreach", "Loxo: profile added from LinkedIn"
    cnt[src or "unknown (empty)"] += 1
    if src and len(ex[src]) < 4: ex[src].append(f"{c['first']} {c['last']}: …{re.sub(r'\\s+', ' ', why)[:150]}…")
    out.append({"candidate_id": cid, "name": f"{c['first']} {c['last']}", "source": src, "evidence": re.sub(r"\s+", " ", why)[:300]})
with open(os.path.join(S, "source_plan.jsonl"), "w") as fh:
    for r in out: fh.write(json.dumps(r) + "\n")
print(dict(cnt))
for k, v in ex.items():
    print("\n==", k); [print("  ", x) for x in v]
