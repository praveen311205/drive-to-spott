# Spott AI-fill prompts (candidate attributes)

Shared rule for every prompt: use ONLY the CV, work experience and notes on this record. Never guess from the
company name, the web or general knowledge. If the evidence isn't there, choose "Unknown".

---

## Function  (single select)
Options: Founding AE, AE, SDR/BDR, AM/CSM, Sales Engineer, Partnerships, Marketing, RevOps, Sales Leader, Unknown

Prompt:
> Pick the candidate's function in their MOST RECENT role (if they are between jobs or on a break, use the last
> role before it). Read the job title AND the responsibilities in the CV work experience; the notes may clarify.
> Use only information on this record — do not infer from the company or the web.
> - Founding AE: the first or one of the first sales hires at a startup ("founding AE", "first sales hire", "built sales from 0").
> - AE: owns and closes new business (Account Executive, Sales Executive, new-business Account Manager).
> - SDR/BDR: prospecting and booking meetings for others (SDR, BDR, Lead Generation, Outbound Rep).
> - AM/CSM: manages existing customers — account management, customer success, renewals, upsell, onboarding.
> - Sales Engineer: pre-sales — Solutions Engineer/Consultant, Sales Engineer, Solution Architect supporting deals.
> - Partnerships: partner, channel, alliances or reseller management.
> - Marketing: demand gen, growth, product/field/content marketing.
> - RevOps: revenue/sales operations, GTM operations, CRM/systems, sales enablement.
> - Sales Leader: manages a sales team (Sales Manager with reports, Head of Sales, Sales Director, VP Sales, CRO).
> If the role is outside sales/marketing/GTM (engineer, designer, finance, consultant, investor) or is unclear, choose Unknown.

## Seniority  (single select)
Options: IC, Senior IC, Team Lead, Head of, VP or above, Unknown

Prompt:
> Pick the seniority of the candidate's MOST RECENT role, from the CV title, scope and number of direct reports.
> - IC: individual contributor, roughly under 4 years in GTM roles, no "Senior/Lead/Strategic/Enterprise" in the title.
> - Senior IC: individual contributor with a Senior/Lead/Principal/Strategic/Enterprise title or 4+ years in GTM roles; Directors with no direct reports also count here.
> - Team Lead: manages a small team (typically 2–8 people) while often still carrying a quota (Team Lead, Sales Manager).
> - Head of: runs a function or region and manages managers or a whole team (Head of Sales/CS/Marketing, Director with a team).
> - VP or above: VP, SVP, CRO, CMO, COO, CEO/founder running the company.
> Use only the CV and notes on this record. If the role or team size is unclear, choose Unknown.

## Segment sold to  (multi select)
Options: SMB, Mid-market, Enterprise, Unknown

Prompt:
> Which customer segments has the candidate SOLD TO in their current and previous sales/GTM roles? Look for
> segment words in titles ("Enterprise AE", "Mid-Market AE", "SMB"), the size of accounts named, deal sizes and
> phrases like "Fortune 500", "DAX", "1,000+ employees", "start-ups".
> - SMB: customers under ~100 employees, small businesses, start-ups.
> - Mid-market: ~100–1,000 employees.
> - Enterprise: 1,000+ employees, large corporates, strategic/named accounts, Fortune 500/FTSE/DAX.
> Pick every segment that is clearly evidenced. Use only the CV and notes on this record. If nothing indicates
> the customer size, choose Unknown.

## Sector sold to  (multi select — the 36 consolidated industries)
Prompt:
> Which industries are the candidate's CUSTOMERS in? This is the industry of the companies they SOLD TO, not the
> industry of their employer. Example: an AE at Samsara selling to trucking fleets → Transportation and Logistics
> (not Software Development); an AE at a bank-software vendor selling to banks → Banking.
> Look for named clients, target verticals and phrases like "sold to retailers", "worked with insurers", "public
> sector accounts", in the current and previous sales/GTM roles. Pick every industry that is clearly evidenced, using
> the option names exactly. Use only the CV and notes on this record. If customers are only described generically
> ("SaaS companies", "mid-market businesses") or not at all, choose Unknown.
(If "Unknown" can't be added to this field, leave the value empty rather than choosing "Other".)
