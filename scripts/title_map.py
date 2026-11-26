#!/usr/bin/env python3
"""Rule-based mapping of a job title -> (Function, Seniority, Segment[]). Unknown when unclear.
Writes state/title_map.csv; titles in state/title_overrides.csv (title,function,seniority,segment) win."""
import csv, re, os, sys
S = os.path.join(os.path.dirname(__file__), "..", "state")
def has(t, *ws): return any(re.search(w, t) for w in ws)
def fn(t):
    if has(t, r"venture partner", r"\binvestor\b", r"board (member|observer)"): return "Unknown"
    if has(t, r"head of .*sales", r"sales lead(er)?ship"): return "Sales Leader"
    if has(t, r"founding (ae|account exec|sales)", r"first (ae|sales hire)", r"pioneer ae"): return "Founding AE"
    if has(t, r"\b(vp|vice president|cro|chief revenue|chief sales|head of sales|sales director|director of sales|director,? sales|sales manager|regional (sales )?manager|country (lead|manager)|general manager|managing director|gm\b|head of (growth|revenue|business development|new business|commercial)|commercial director|director,? (business development|strategic accounts|enterprise sales|commercial)|team lead.*(sales|account|ae|bdr|sdr)|(sales|ae|bdr|sdr).*team lead)"):
        if has(t, r"\b(sdr|bdr)\b") and has(t, r"team lead|manager"): return "SDR/BDR"
        if has(t, r"customer success|account management|\bcs\b"): return "AM/CSM"
        if has(t, r"partner"): return "Partnerships"
        if has(t, r"marketing"): return "Marketing"
        return "Sales Leader"
    if has(t, r"\b(sdr|bdr)\b", r"sales development", r"business development rep", r"lead generation", r"outbound (rep|specialist)"): return "SDR/BDR"
    if has(t, r"solutions? (engineer|consultant|architect)", r"sales engineer", r"pre-?sales", r"value engineer", r"technical account"): return "Sales Engineer"
    if has(t, r"partner(ship)?s?\b", r"channel", r"alliances?"): return "Partnerships"
    if has(t, r"rev ?ops", r"revenue operations", r"sales operations", r"gtm (ops|operations|engineer)", r"sales enablement", r"business operations", r"crm"): return "RevOps"
    if has(t, r"marketing", r"demand gen", r"growth (manager|marketer|lead)", r"\bpmm\b", r"brand", r"content"): return "Marketing"
    if has(t, r"customer success", r"\bcsm\b", r"account manag", r"client (success|partner|manager)", r"onboarding", r"renewals?", r"customer (manager|experience)", r"key account"): return "AM/CSM"
    if has(t, r"account exec", r"\bae\b", r"sales exec", r"sales (representative|rep)\b", r"business development (manager|executive)", r"new business", r"sales consultant", r"sales specialist", r"enterprise sales", r"inside sales", r"sales$", r"^sales\b"): return "AE"
    return "Unknown"
def sen(t, f):
    if has(t, r"\b(vp|vice president|svp|evp|cro|ceo|coo|cmo|cco|chief|president|managing director)\b"): return "VP or above"
    if has(t, r"head of", r"\bdirector\b", r"general manager", r"country (lead|manager)"):
        return "Head of" if f in ("Sales Leader", "Marketing", "AM/CSM", "Partnerships", "RevOps", "SDR/BDR") else "Senior IC"
    if has(t, r"team ?lead") and f != "Unknown": return "Team Lead"
    if has(t, r"\bmanager\b.*\b(sales|sdr|bdr|team)\b", r"sales manager", r"\blead\b") and f in ("Sales Leader", "SDR/BDR"): return "Team Lead"
    if f == "Unknown": return "Unknown"
    if has(t, r"senior|\bsr\.?\b|principal|strategic|enterprise|lead\b|staff|major|global account|key account"): return "Senior IC"
    if has(t, r"junior|associate|\bjr\b|intern|graduate|trainee"): return "IC"
    if f in ("AE", "SDR/BDR", "AM/CSM", "Sales Engineer", "Partnerships", "Marketing", "RevOps", "Founding AE"): return "IC"   # plain title, no seniority marker
    return "Unknown"
def seg(t):
    s = []
    if has(t, r"\bsmb\b", r"small business", r"\bsme\b", r"commercial ae"): s.append("SMB")
    if has(t, r"mid[- ]?market", r"\bmm\b", r"\bmid\b"): s.append("Mid-market")
    if has(t, r"enterprise", r"strategic", r"major accounts?", r"global accounts?", r"key accounts?", r"large accounts?", r"corporate accounts?"): s.append("Enterprise")
    return s
def main():
    over = {}
    p = os.path.join(S, "title_overrides.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p)): over[r["title"]] = r
    rows, unk = [], 0
    for line in open(os.path.join(S, "titles.tsv")):
        cnt, title = line.rstrip("\n").split("\t", 1)
        if title == "NONE": continue
        t = title.lower()
        if title in over:
            o = over[title]; f, s_, g = o["function"], o["seniority"], [x for x in o["segment"].split("|") if x]; src = "override"
        else:
            f = fn(t); s_ = sen(t, f); g = seg(t) if f in ("AE", "Founding AE", "SDR/BDR", "AM/CSM", "Sales Engineer", "Sales Leader") else []; src = "rule"
        unk += f == "Unknown"
        rows.append([title, cnt, f, s_, "|".join(g), src])
    with open(os.path.join(S, "title_map.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["title", "count", "function", "seniority", "segment", "source"]); w.writerows(rows)
    print("titles", len(rows), "| function unknown", unk)


if __name__ == "__main__":
    main()
