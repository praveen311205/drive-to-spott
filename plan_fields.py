#!/usr/bin/env python3
"""Bulk custom-field planner.

Reads every staged profile (state/profiles_*.jsonl), validates each value against the live Spott field
definitions (state/custom_fields.json, from spott_list_enums custom_fields_candidate), and groups candidates
by (field, value) so each group is ONE spott_set_custom_field call (<=100 recordIds per call).

Usage: plan_fields.py [--include-sector]
Writes state/field_plan.json  (list of calls: {definitionId, label, value, recordIds})
       state/field_plan_rejects.csv (values that don't match a field option — fix or ignore)
Idempotent: re-running after more batches finish just produces the full plan again; set_custom_field
with "replace" semantics makes re-applying safe.
"""
import csv, glob, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "state")
INCLUDE_SECTOR = "--include-sector" in sys.argv

# staging key -> Spott field label
FIELD_MAP = {
    "function": "Function", "seniority": "Seniority", "segment": "Segment Sold to",
    "rip_and_replace": "Rip-and-replace", "rip_and_replace_incumbent": "Rip-and-replace incumbent",
    "base": "Base", "ote": "OTE", "currency": "Currency", "notice_period": "Notice period",
    "work_setup": "Work setup", "work_rights": "Work rights", "languages": "Language",
    "status": "Status", "source": "Source", "last_contact_date": "Last contact date",
    "next_step": "Next step", "sector": "Sector sold to",
}
# tolerate label drift between the written standard and Spott's labels
ALIASES = {"Sales leader": "Sales Leader", "Team lead": "Team Lead", "Mid-Market": "Mid-market",
           "Swedish": "Nordic (Swedish/Danish/Norwegian)", "Danish": "Nordic (Swedish/Danish/Norwegian)",
           "Norwegian": "Nordic (Swedish/Danish/Norwegian)"}
# Spott full industry label -> consolidated "Sector sold to" bucket
SECTOR_BUCKETS = {
    "Software Development": "Software Development", "IT Services and IT Consulting": "IT Services and IT Consulting",
    "Technology, Information and Internet": "Technology and Internet", "Technology, Information and Media": "Technology and Internet",
    "Information Technology & Services": "IT Services and IT Consulting", "Computer and Network Security": "Computer and Network Security",
    "Data Infrastructure and Analytics": "Data Infrastructure and Analytics", "Financial Services": "Financial Services",
    "Banking": "Banking", "Insurance": "Insurance", "Capital Markets": "Capital Markets and Investment Management",
    "Investment Management": "Capital Markets and Investment Management", "Venture Capital and Private Equity Principals": "Venture Capital and Private Equity",
    "Human Resources Services": "Human Resources and Staffing", "Staffing and Recruiting": "Human Resources and Staffing",
    "Marketing Services": "Marketing and Advertising", "Advertising Services": "Marketing and Advertising",
    "Retail": "Retail and E-commerce", "Online and Mail Order Retail": "Retail and E-commerce",
    "Internet Marketplace Platforms": "Internet Marketplace Platforms", "Consumer Goods": "Consumer Goods",
    "Food and Beverage Services": "Food and Beverage", "Food and Beverage Manufacturing": "Food and Beverage",
    "Hospitality": "Hospitality and Travel", "Travel Arrangements": "Hospitality and Travel",
    "Transportation, Logistics, Supply Chain and Storage": "Transportation and Logistics", "Truck Transportation": "Transportation and Logistics",
    "Warehousing and Storage": "Transportation and Logistics", "Freight and Package Transportation": "Transportation and Logistics",
    "Automotive": "Automotive", "Manufacturing": "Manufacturing", "Industrial Machinery Manufacturing": "Manufacturing",
    "Industrial Automation": "Industrial Automation", "Construction": "Construction and Real Estate", "Real Estate": "Construction and Real Estate",
    "Utilities": "Energy and Utilities", "Renewable Energy Power Generation": "Energy and Utilities", "Oil and Gas": "Oil Gas and Mining",
    "Mining": "Oil Gas and Mining", "Telecommunications": "Telecommunications", "Hospitals and Health Care": "Hospitals and Health Care",
    "Pharmaceutical Manufacturing": "Pharma and Biotech", "Biotechnology": "Pharma and Biotech", "Medical Equipment Manufacturing": "Medical Devices",
    "Medical Device": "Medical Devices", "Education": "Education and E-learning", "E-Learning Providers": "Education and E-learning",
    "Higher Education": "Education and E-learning", "Government Administration": "Government and Public Sector", "Legal Services": "Legal Services",
    "Accounting": "Accounting", "Business Consulting and Services": "Business Consulting and Services",
    "Entertainment": "Media and Entertainment", "Media Production": "Media and Entertainment", "Non-profit Organizations": "Non-profit",
}


def main():
    # duplicate labels (e.g. an old and a rebuilt "Sector sold to"): the most recently created field wins
    items = sorted(json.load(open(os.path.join(STATE, "custom_fields.json")))["custom_fields_candidate"]["items"],
                   key=lambda d: d.get("createdAt") or "")
    defs = {d["label"]: d for d in items}
    groups = defaultdict(set)   # (label, json(value)) -> candidate ids
    rejects, seen = [], set()
    files = sorted(glob.glob(os.path.join(STATE, "profiles_*.jsonl")))
    for path in files:
        for line in open(path):
            p = json.loads(line)
            cid = p.get("candidate_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            for key, label in FIELD_MAP.items():
                if key == "sector" and not INCLUDE_SECTOR:
                    continue
                raw = p.get(key)
                if raw in (None, "", "unknown", "Unknown", [], ["unknown"]):
                    continue
                d = defs.get(label)
                if not d:
                    rejects.append([cid, p.get("key"), label, raw, "field missing in Spott"]); continue
                vt = d["viewType"]
                opts = d.get("definition", {}).get("options") or []
                if key == "source":
                    raw = "Drive import"
                if key == "sector":
                    raw = [SECTOR_BUCKETS.get(s, s) for s in (raw if isinstance(raw, list) else [raw])]
                if vt == "customSelect":
                    v = ALIASES.get(raw, raw)
                    if v == "Other" or v not in opts:
                        if isinstance(v, str) and v.startswith("other:") and "Other" in opts:
                            v = "Other"
                        elif v not in opts:
                            rejects.append([cid, p.get("key"), label, raw, "not an option"]); continue
                    value = {"kind": "select", "select": v}
                elif vt == "customMultiSelect":
                    vals = raw if isinstance(raw, list) else [raw]
                    vals = [ALIASES.get(x, x) for x in vals]
                    bad = [x for x in vals if x not in opts]
                    if bad and "Other" in opts:
                        vals = [x for x in vals if x in opts] + ["Other"]   # e.g. Turkish -> Other
                    elif bad:
                        rejects.append([cid, p.get("key"), label, bad, "not an option"])
                    # one append-call per option keeps the call count at <= number of options
                    for x in sorted(set(x for x in vals if x in opts)):
                        groups[(label, json.dumps({"kind": "multiSelect", "multiSelect": [x], "action": "append"}, sort_keys=True))].add(cid)
                    continue
                elif vt == "customCheckbox":
                    if raw not in ("yes", "no", True, False): continue
                    value = {"kind": "checkbox", "checked": raw in ("yes", True)}
                elif vt == "customNumber":
                    try: value = {"kind": "number", "number": float(raw)}
                    except (TypeError, ValueError):
                        rejects.append([cid, p.get("key"), label, raw, "not a number"]); continue
                elif vt == "customDate":
                    value = {"kind": "date", "date": str(raw)[:10]}
                elif vt == "customText":
                    value = {"kind": "text", "text": str(raw)}
                else:
                    rejects.append([cid, p.get("key"), label, raw, f"unsupported type {vt}"]); continue
                groups[(label, json.dumps(value, sort_keys=True))].add(cid)

    plan = []
    for (label, vjson), ids in sorted(groups.items()):
        ids = sorted(ids)
        for i in range(0, len(ids), 100):
            plan.append({"definitionId": defs[label]["id"], "label": label, "value": json.loads(vjson), "recordIds": ids[i:i + 100]})
    json.dump(plan, open(os.path.join(STATE, "field_plan.json"), "w"), indent=1)
    with open(os.path.join(STATE, "field_plan_rejects.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["candidate_id", "key", "field", "value", "reason"]); w.writerows(rejects)
    print(f"profiles files: {len(files)} | candidates: {len(seen)} | set_custom_field calls: {len(plan)} | rejects: {len(rejects)}")


if __name__ == "__main__":
    main()
