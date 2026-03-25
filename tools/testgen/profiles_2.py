"""Test profiles 5-8 for Talking Rock testgen (Finance and HR personas)."""

PROFILES_2 = [
    # =========================================================================
    # Profile 5: Catherine Liu — Chief Financial Officer (Finance)
    # =========================================================================
    {
        "id": "catherine_liu",
        "identity": {
            "full_name": "Catherine Liu",
            "department": "Finance",
            "title": "Chief Financial Officer",
        },
        "personality": "methodical",
        "your_story": """\
# Catherine Liu — Chief Financial Officer

I'm Catherine Liu, CFO at this company and a CPA with an MBA from Wharton. I've spent 28 years in finance,
the last 14 of which have been at the CFO level. Before joining here, I served as CFO at two earlier-stage
SaaS companies — one we took through a Series B and sold to a strategic acquirer, and one I helped IPO in 2019.

I grew up in Boston in a Chinese-American family that placed enormous value on precision and accountability.
Those values have shaped my entire career. I believe that every number tells a story, and that a CFO's job
is not just to report the story accurately, but to anticipate the next chapter before it happens.

**Professional Background**

I began my career at Deloitte in Boston's audit practice, where I spent seven years developing the discipline
that still defines how I work. From there I moved into corporate finance at a mid-size software company, and
eventually into the SaaS world in the early 2010s when the subscription model was still being standardized.

I hold a CPA license and completed my MBA at Wharton in 2001. I serve on the audit committees of two
portfolio companies and am a member of the CFO Leadership Council.

**How I Work**

I operate in structured sprints: Monday is planning, Thursday is review, and everything in between is
execution. I review materials before I meet — I do not learn in meetings. I give 48 hours advance notice
for any review I'm asked to lead, and I expect the same from my team.

I am risk-conscious but not risk-averse. I believe the best CFOs enable growth by making risk legible, not
by blocking it. My job is to make sure we understand the risks we're taking and that we're compensated for them.

**Current Focus**

We are in the middle of a Series C raise, an ASC 606 compliance overhaul tied to our shift to usage-based
pricing, and a complete modernization of our FP&A reporting stack. Three large, parallel efforts — which is
exactly the kind of environment I'm built for.
""",
        "acts": [
            {
                "title": "Series C Financial Planning",
                "color": "#059669",
                "notes": """\
We are targeting an $80M Series C at a $600M post-money valuation, with a close targeted for Q3. This is
the most complex capital raise I've managed since the IPO in 2019, and the preparation demands the same
level of rigor.

**The Narrative We're Building**

Investors at this stage are buying a financial story as much as a product story. Our headline metrics are
strong: ARR of $42M growing at 68% year-over-year, net dollar retention of 118%, and a burn multiple of
1.4x — which is well within the range that top-tier growth investors expect to see at our scale. Gross
margin sits at 74%, with improving leverage in both S&M and R&D as a percentage of revenue. The story
is efficient growth, and the numbers support it.

**Investor Materials**

I'm personally overseeing the financial narrative within the pitch deck and am owning the full financial
data room. This includes audited financials for FY2023 and FY2024, reviewed financials for the first two
quarters of FY2025, ARR waterfall analysis, cohort retention analysis (coordinated with Tomás), unit
economics by customer segment, and a detailed headcount and hiring plan through FY2027.

**Scenario Modeling**

I've built three financial models: bull, base, and bear case. The base case assumes continued 60%+ ARR
growth, a 12-month runway extension post-close, and a path to cash-flow breakeven in Q4 2027. The bull
case models 80% growth driven by upmarket expansion and international revenue inflecting in H2 2026. The
bear case stress-tests the model at 40% growth and reflects the playbook we'd run to extend runway by
adjusting hiring timing and non-critical vendor spend.

**Due Diligence Preparation**

We are setting up a tiered data room in Datasite. Tier 1 is available to all qualified investors post-NDA.
Tier 2 (detailed customer data, pipeline analytics) is gated to serious investors post-term sheet. Our
legal counsel is coordinating document preparation and will review everything before upload. I expect the
data room to be fully populated four weeks ahead of the first investor close.

**Board and Advisor Coordination**

I'm briefing the board monthly through this process, with a special August session planned for scenario
review. Our lead investor and two independents are actively involved in investor introductions. I've also
engaged our investment bank for targeted outreach to twelve strategic funds, with first meetings scheduled
for late Q2.

**Key Milestones**

Q2: Complete audited financials, finalize scenario models, data room Tier 1 complete.
Q3 Early: Begin formal investor process, first close targeted, legal documents drafted.
Q3 Close: Series C closed, wire received, 8-K filed within required window.

The timeline is tight but executable. Every week we slip costs us negotiating leverage as market conditions
evolve. I am tracking this daily.
""",
                "scenes": [
                    {
                        "title": "Finalize base/bull/bear scenario models",
                        "stage": "in_progress",
                        "notes": "Three-scenario Excel/Python model. Base case reviewed by board. Bull and bear cases under refinement with updated hiring plan sensitivity analysis.",
                    },
                    {
                        "title": "Tier 1 data room population",
                        "stage": "in_progress",
                        "notes": "Datasite environment configured. Audited FY2023 and FY2024 financials uploaded. FY2025 Q1-Q2 reviewed financials pending final legal sign-off.",
                    },
                    {
                        "title": "ARR waterfall and cohort analysis",
                        "stage": "awaiting_data",
                        "notes": "Awaiting Tomás's final cohort output before ARR waterfall narrative is locked. Blocking the investor summary appendix.",
                    },
                    {
                        "title": "Board August scenario review session",
                        "stage": "planning",
                        "notes": "Special board meeting planned to walk all three scenarios. Materials due two weeks prior. I will present; CFO deck template is drafted.",
                    },
                    {
                        "title": "Investment bank kick-off and fund targeting",
                        "stage": "in_progress",
                        "notes": "Bank engaged. Twelve target funds selected. First outreach emails scheduled for end of Q2. Tracking introduction pipeline in shared CRM.",
                    },
                    {
                        "title": "Legal coordination and NDA process",
                        "stage": "planning",
                        "notes": "Outside counsel coordinating standard NDA flow. Tier 2 data room access gating requires legal approval per investor. Process documented.",
                    },
                ],
            },
            {
                "title": "Revenue Recognition Overhaul",
                "color": "#047857",
                "notes": """\
The shift to usage-based pricing has made our previous revenue recognition approach — which was designed
for a simple seat-based SaaS model — no longer fit for purpose under ASC 606. This project is a full
compliance overhaul touching our ERP, our billing system, our financial reporting, and our audit
methodology. It is one of the most technically complex accounting projects I've managed.

**The Compliance Problem**

Under usage-based pricing, revenue is recognized as the customer consumes the service — not ratably over
a contract period. This means we need to be able to attribute each dollar of recognized revenue to a
specific period of consumption, at a granular level, and tie it back to the performance obligations defined
in the customer contract. Our current system can't do this reliably. It was built for ratable SaaS.

**System Changes Required**

We're implementing a dedicated revenue accounting sub-ledger (evaluating Zuora Revenue and Maxio as
candidates) that will integrate with our Salesforce CPQ for contract terms and our AWS Marketplace data
feeds for consumption telemetry. The sub-ledger will calculate period revenue, generate journal entries,
and pass recognized amounts to NetSuite. We also need to build reconciliation between the sub-ledger and
our billing system to catch any discrepancy between billed and recognized amounts.

**Audit Preparation**

Our external auditors have been engaged early in this process — I want no surprises at year-end. We've
shared the implementation spec with them and have agreed on a testing methodology for the new sub-ledger.
They will perform walkthrough procedures before we go live and will issue a memo confirming the accounting
treatment for our new pricing model. The audit committee has been briefed.

**Training Plan**

Not everyone in finance touches revenue recognition today, but they will need to after go-live. I'm
designing a three-session training program: one session on ASC 606 principles for non-accountants (sales,
legal), one for the finance team on the new system workflow, and one for accounting leadership on the
judgment calls embedded in the new treatment. External counsel is running the legal session.

**Cutover Timeline**

We are targeting a January 1 cutover to align with the fiscal year. This requires the sub-ledger to be
tested and signed off by November 30. We will run parallel: old system and new system simultaneously for
Q4, comparing output weekly. Any discrepancies above 0.5% of period revenue trigger immediate escalation
to me. I am not willing to cut over until the parallel run is clean for eight consecutive weeks.

**Risk Factors**

The primary risks are data quality in consumption telemetry (AWS Marketplace data has had latency issues
in the past) and contract interpretation edge cases for multi-year deals signed before the pricing change.
I've flagged both to the audit committee and am tracking mitigation plans for each.
""",
                "scenes": [
                    {
                        "title": "Sub-ledger vendor selection (Zuora vs Maxio)",
                        "stage": "in_progress",
                        "notes": "RFP issued. Zuora demo completed. Maxio demo scheduled next week. Decision committee: Catherine, Controller, VP Engineering. Decision by end of month.",
                    },
                    {
                        "title": "Auditor alignment on ASC 606 treatment",
                        "stage": "complete",
                        "notes": "External auditors engaged. Walkthrough memo agreed. Testing methodology confirmed for Q4 parallel run. Audit committee briefed.",
                    },
                    {
                        "title": "Consumption telemetry data quality remediation",
                        "stage": "in_progress",
                        "notes": "AWS Marketplace latency issue investigated. Engineering implementing webhook-based push vs polling. Target: 99.5% data completeness within 24 hours of consumption.",
                    },
                    {
                        "title": "ASC 606 training program design",
                        "stage": "planning",
                        "notes": "Three-session program outlined. External counsel confirmed for legal session. Internal finance trainer identified. Scheduling for Q3.",
                    },
                    {
                        "title": "Q4 parallel run (old vs new recognition)",
                        "stage": "planning",
                        "notes": "Parallel run protocol designed. Tolerance threshold set at 0.5%. Weekly reconciliation meeting with Controller and sub-ledger vendor. Eight clean weeks required before cutover.",
                    },
                ],
            },
            {
                "title": "FP&A Dashboard Modernization",
                "color": "#10b981",
                "notes": """\
Our current financial planning and analysis infrastructure is a collection of Excel workbooks that have
accumulated over five years. Some of them are masterpieces of spreadsheet engineering. They are also
completely unmaintainable, accessible only to the people who built them, and unable to provide the
real-time visibility that a company at our growth stage requires. This project replaces them with a
modern, connected BI platform.

**The Problem with Excel**

Our monthly close takes five business days. Three of those days are spent pulling data from NetSuite,
Salesforce, Rippling, and AWS into Excel, cleaning it, and formatting the output. The dashboards are
static — they show last month's numbers by the time they reach the leadership team. When the CEO asks
a question that requires slicing data a different way, it takes two days to answer. This is not
acceptable at our stage.

**Data Architecture**

We're building on top of our existing data warehouse (Snowflake). The warehouse already ingests from
NetSuite, Salesforce, AWS, and Rippling via Fivetran — but the finance-relevant models are underdeveloped.
We need to build a financial data layer: standardized revenue recognition tables, fully loaded headcount
cost models, departmental spend allocation, and a metrics layer that calculates our core KPIs
(ARR, NDR, CAC, LTV, burn multiple, magic number) on a daily refresh cadence.

**KPI Definitions**

Before we build any dashboards, we are locking KPI definitions in a shared metrics glossary. Every
metric will have a canonical formula, a data owner, a refresh frequency, and a defined audit trail.
I will not allow a world where the CEO's dashboard says ARR is $42.1M and my dashboard says $41.9M
because we're using different methodologies. One source of truth.

**Tool Selection: Looker vs Sigma**

We are in evaluation. Looker has stronger semantic layer capabilities and better governance controls,
which matters for a finance use case where metric definition consistency is paramount. Sigma is faster
to deploy and more approachable for non-technical finance users who want to do ad hoc analysis without
writing LookML. We've run demos with both vendors and are currently in a 30-day pilot with each, using
a representative data set. My team will score both on: governance, self-service capability, performance,
and total cost of ownership. Decision expected by end of Q2.

**Stakeholder Requirements**

I've gathered requirements from eight stakeholders: CEO, CRO, VP Engineering, VP People, three other
department heads, and my own team. The CEO wants pipeline coverage and burn rate on a single screen.
The CRO wants ARR waterfall and NRR by segment. Engineering wants cost-per-engineer and cloud spend
per product line. I've prioritized these into Phase 1 (exec-facing, 5 dashboards) and Phase 2
(department-facing, 12 dashboards).

**Rollout Phases**

Phase 1 (Q3): Executive dashboards live. Daily refresh. Excel-based monthly close retired for exec reporting.
Phase 2 (Q4): Department dashboards live. Self-service enabled for department heads.
Phase 3 (Q1 next year): Finance team fully migrated. Excel workbooks archived. Full close-time target: two business days.
""",
                "scenes": [
                    {
                        "title": "Metrics glossary and KPI definitions locked",
                        "stage": "in_progress",
                        "notes": "Draft glossary circulated to CEO, CRO, Catherine. 18 of 24 KPIs have agreed definitions. 6 still under discussion (magic number methodology, LTV discount rate). Targeting close by end of week.",
                    },
                    {
                        "title": "Snowflake financial data layer build",
                        "stage": "planning",
                        "notes": "Data engineering scoped the work: 6-week build, 2-person team. Requires finalized KPI definitions before starting. Fivetran connectors already in place.",
                    },
                    {
                        "title": "Looker vs Sigma 30-day pilot",
                        "stage": "in_progress",
                        "notes": "Both pilots running. Scoring rubric distributed to evaluation team (Catherine + 2 analysts + 1 data engineer). Pilot closes end of Q2. Procurement holds both vendor slots until decision.",
                    },
                    {
                        "title": "Phase 1 executive dashboard design",
                        "stage": "planning",
                        "notes": "Wireframes drafted for 5 exec dashboards. Pending tool decision before build begins. Design review with CEO and CRO scheduled post-tool selection.",
                    },
                    {
                        "title": "Department stakeholder requirements gathering",
                        "stage": "complete",
                        "notes": "All 8 stakeholder interviews complete. Requirements documented and prioritized into Phase 1 and Phase 2. Backlog of 12 department dashboards defined.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Walk me through the revenue recognition timeline for Q2. What are the key milestones I should be tracking?",
                    },
                    {
                        "role": "cairn",
                        "content": "For Q2, the revenue recognition overhaul has three milestones that matter most.\n\nFirst, the sub-ledger vendor decision is due by the end of the month. You have the Maxio demo next week, after which your evaluation committee makes the call. Everything downstream — integration timelines, the Q4 parallel run — depends on this decision not slipping.\n\nSecond, the consumption telemetry remediation is in progress. Engineering is targeting 99.5% completeness within 24 hours of consumption via the webhook implementation. You've flagged this as a risk factor, so it's worth a check-in on their delivery date.\n\nThird, the ASC 606 training program is in planning for Q3, but you'll want to finalize the schedule during Q2 so external counsel and the internal trainer can block time.\n\nThe auditor alignment scene is already marked complete, which removes one dependency. The open critical path item is vendor selection — everything else gates on that.",
                    },
                    {
                        "role": "user",
                        "content": "Good. What's the status of the data room for the Series C?",
                    },
                    {
                        "role": "cairn",
                        "content": "Tier 1 is partially populated. Audited FY2023 and FY2024 financials are uploaded. The FY2025 Q1–Q2 reviewed financials are pending final legal sign-off before they go in.\n\nThe ARR waterfall and cohort analysis appendix is blocked — you're waiting on Tomás's final cohort output before the investor summary narrative can be locked. That's the current dependency on the data room critical path.\n\nThe legal coordination and NDA process is in planning. Outside counsel has the Tier 2 gating protocol documented but hasn't started the investor-specific NDA flow yet.\n\nYou have four weeks before you said you wanted the data room fully populated ahead of the first investor close. The Tomás dependency is the one I'd resolve first.",
                    },
                    {
                        "role": "user",
                        "content": "Remind me — when do I need to have the board materials ready for the August scenario review session?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your notes say materials are due two weeks before the August board session. Your board meets the last Thursday of each month, so the August session is August 28th. That puts your materials deadline at August 14th.\n\nThe CFO deck template is drafted. The scenario models are still in progress — bull and bear cases are under refinement with the updated hiring plan sensitivity analysis. You'll want those finalized well before the 14th to give yourself review time.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What meetings do I have with investors this week?",
                    },
                    {
                        "role": "cairn",
                        "content": "You don't have any investor meetings on the calendar this week. Based on your Series C planning notes, the investment bank's first outreach to the twelve target funds is scheduled for end of Q2, so the formal investor meeting process hasn't begun yet.\n\nYou do have your regular board prep touchpoint and the Maxio demo this week, which is a prerequisite for the vendor decision that feeds into the data room timeline.",
                    },
                    {
                        "role": "user",
                        "content": "Correct. Flag me if anything investor-related lands on the calendar. What's the burn multiple tracking at currently?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your investor materials have it at 1.4x — that's the figure going into the Series C narrative. You've noted this as a key metric alongside ARR of $42M and NDR of 118%.\n\nYou've also flagged concern about burn rate acceleration in Q2. If the 1.4x is based on trailing data and Q2 is running hotter, you'll want the base case scenario model to reflect the updated figure before it goes to investors. Is Q2 tracking within the model's assumptions?",
                    },
                    {
                        "role": "user",
                        "content": "It's tracking slightly above. I'll update the model this week. Add a reminder for me to reconcile burn multiple in the base case model before investor outreach begins.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted. I've recorded a reminder: reconcile Q2 burn multiple in the base case scenario model before investor outreach begins. Given your outreach is targeted for end of Q2, I'd treat this as a this-week priority alongside the Maxio demo debrief.\n\nDo you want this linked to the Series C planning act, or tracked separately?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "The FP&A dashboard pilot ends at the end of the month. What's the decision process look like?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your evaluation team — you, two analysts, and one data engineer — scores both Looker and Sigma on four dimensions: governance, self-service capability, performance, and total cost of ownership. The 30-day pilot closes at end of Q2.\n\nYou've noted that Looker has stronger semantic layer and governance controls, which matter for finance use cases. Sigma is faster to deploy and more accessible for self-service analysis. The scoring rubric has been distributed to the full evaluation team.\n\nProcurement is holding slots with both vendors until the decision is made. Once you select, the Snowflake financial data layer build can begin — that's a 6-week effort that's currently in planning, gating on both the tool decision and the finalized KPI definitions. Six of your 24 KPIs are still under discussion.",
                    },
                    {
                        "role": "user",
                        "content": "The magic number methodology disagreement is with the CRO. Can you pull up what we agreed on for the other disputed KPIs?",
                    },
                    {
                        "role": "cairn",
                        "content": "From your metrics glossary notes, the six KPIs still under discussion are magic number methodology and LTV discount rate — those are the two your notes specifically call out. The other four disputed definitions aren't detailed in what I have.\n\nI don't have the resolution status of the other four. Do you want me to flag the metrics glossary review as a scene to track, so the open items are captured explicitly?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I need to send a note to Tomás about the cohort analysis. Remind me what he's working on and what's blocking the data room.",
                    },
                    {
                        "role": "cairn",
                        "content": "Tomás is building a cohort-based retention and expansion revenue model for the Series C narrative — an 8-quarter lookback covering customer retention and expansion revenue by cohort. He's been dealing with data quality issues in the Q3 data specifically.\n\nThe dependency for your data room: the ARR waterfall appendix and the investor summary narrative are both blocked until his final cohort output is ready. That's the piece holding up Tier 1 completion.\n\nHe works late on Wednesdays to prepare for your Thursday review, so this week's Thursday session may be the natural checkpoint. Do you want me to draft a note to him, or just use this as context for your message?",
                    },
                    {
                        "role": "user",
                        "content": "Draft a brief note. Professional but direct.",
                    },
                    {
                        "role": "cairn",
                        "content": "Here's a draft:\n\n---\n\nTomás,\n\nThe ARR waterfall appendix and investor summary narrative are both gating on your cohort analysis output. I need to know two things before Thursday: (1) what's the current status of the Q3 data quality issue, and (2) what's your realistic delivery date for the final output?\n\nIf there's a version I can work with that flags the Q3 data as provisional, that may be preferable to waiting. Let me know your read.\n\n— Catherine\n\n---\n\nWant me to adjust the tone or add anything?",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Catherine requires 48-hour advance review of any financial materials going to the board.",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Board material review lead time",
                    "decision": "48-hour advance review required for any financial materials going to the board",
                    "owner": "catherine_liu",
                },
            },
            {
                "narrative": "Catherine's board meeting is the last Thursday of each month.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Board meeting cadence",
                    "pattern": "Last Thursday of each month",
                    "relevance": "Drives all board material deadlines — materials due 2 weeks prior",
                },
            },
            {
                "narrative": "Catherine is concerned about burn rate acceleration in Q2 — it is tracking above the base case model assumption of 1.4x burn multiple.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Q2 burn rate",
                    "concern": "Burn rate accelerating above 1.4x model assumption",
                    "action_needed": "Reconcile Q2 actuals into base case model before investor outreach",
                },
            },
            {
                "narrative": "The Series C data room ARR waterfall appendix is blocked on Tomás Rivera's cohort analysis output, which has Q3 data quality issues.",
                "entity_type": "waiting_on",
                "entity_data": {
                    "waiting_for": "Tomás Rivera",
                    "deliverable": "Final cohort analysis output (8-quarter lookback)",
                    "blocker": "Q3 data quality issues unresolved",
                    "impact": "ARR waterfall appendix and investor summary narrative cannot be finalized",
                },
            },
            {
                "narrative": "Catherine is evaluating Looker vs Sigma for the FP&A dashboard modernization; tool decision gates the Snowflake financial data layer build (6-week effort).",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "FP&A BI tool selection",
                    "options": ["Looker", "Sigma"],
                    "decision_date": "End of Q2",
                    "downstream_dependency": "Snowflake financial data layer build",
                },
            },
            {
                "narrative": "Catherine's magic number methodology disagreement for the metrics glossary is with the CRO; 6 of 24 KPI definitions remain unresolved.",
                "entity_type": "waiting_on",
                "entity_data": {
                    "waiting_for": "CRO alignment",
                    "subject": "Magic number methodology and LTV discount rate",
                    "context": "KPI definitions must be locked before Snowflake data layer build begins",
                },
            },
            {
                "narrative": "Catherine is targeting a January 1 cutover for the ASC 606 revenue recognition sub-ledger; requires 8 consecutive clean weeks in Q4 parallel run.",
                "entity_type": "task",
                "entity_data": {
                    "task": "ASC 606 sub-ledger cutover",
                    "target_date": "January 1",
                    "gating_condition": "8 consecutive weeks with <0.5% revenue discrepancy in parallel run",
                    "parallel_run_start": "Q4",
                },
            },
            {
                "narrative": "Catherine served as CFO at two prior SaaS companies — one sold to a strategic acquirer post-Series B, one taken through IPO in 2019. She holds a CPA license and a Wharton MBA.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Catherine Liu",
                    "title": "CFO",
                    "credentials": ["CPA", "Wharton MBA"],
                    "prior_experience": ["CFO at Series B SaaS (sold to strategic)", "CFO at IPO (2019)"],
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },

    # =========================================================================
    # Profile 6: Tomás Rivera — Financial Analyst (Finance)
    # =========================================================================
    {
        "id": "tomas_rivera",
        "identity": {
            "full_name": "Tomás Rivera",
            "department": "Finance",
            "title": "Financial Analyst",
        },
        "personality": "anxious",
        "your_story": """\
# Tomás Rivera — Financial Analyst

I'm Tomás Rivera, Financial Analyst on the Finance team, reporting to Catherine Liu. I've been in finance
for four years, but this is my first role at a tech company — before joining here, I was in corporate banking
at a mid-size bank in New York, where I spent three years doing credit analysis and financial modeling for
middle-market clients.

I grew up in Puerto Rico and moved to New York for college. I'm 27 and I'm still figuring out the pace
of the tech world. It moves faster than I expected. The culture is different — nobody at the bank would
have asked me to automate my own job, but here, that's just called "being good at your job."

**My Background**

My financial modeling skills are strong — I built most of our customer cohort models from scratch using
nothing but Excel and a lot of late nights. I'm comfortable with pivot tables, complex VLOOKUP chains,
and scenario analysis. I'm learning Python because I want to replace those VLOOKUP chains with something
I don't have to rebuild from scratch every quarter.

I have a bachelor's in economics from Fordham and passed my Series 7 at the bank, though that's not
really relevant here. I'm working toward my CFA Level 1.

**How I Work**

I tend to go deep and stay late rather than ask for help early. I know that's not always the right
call — Catherine has told me twice that she'd rather have a heads-up on a problem two days before
her deadline than a perfect answer the night before. I'm working on that.

Wednesday nights are my catch-up window. I stay late to make sure I'm ready for Catherine's Thursday
morning review. If something is going to slip, Wednesday night is when I find out.

**What I'm Working On**

Three active projects: the customer cohort analysis for the Series C, automating our budget vs actuals
reporting to cut the close from five days to two, and building a vendor contract renewal database for
47 active contracts. The cohort work is the most visible — Catherine needs it for the investor narrative
and I have a data quality problem in the Q3 cohort that I haven't fully resolved yet.
""",
        "acts": [
            {
                "title": "Customer Cohort Analysis",
                "color": "#f59e0b",
                "notes": """\
The cohort analysis is the most important thing I'm working on right now. It feeds directly into the
Series C investor narrative — Catherine needs it to build the ARR waterfall appendix and finalize the
investor summary. If this slips, the data room slips, and she's made very clear that is not acceptable.

**What the Analysis Covers**

I'm building an 8-quarter lookback of customer cohorts, tracking three things per cohort: logo retention
rate, gross revenue retention, and net revenue retention (expansion included). The goal is to show
investors a consistent pattern of strong retention and expansion across cohorts — which, when the data
is clean, is actually a compelling story. Our NDR of 118% is real, and the cohort data should prove it.

**Methodology**

I'm defining cohorts by the quarter a customer first reached $1 in recognized revenue. For each
subsequent quarter, I calculate what percentage of that cohort's original ARR is still active (GRR)
and what the total revenue from the cohort has grown to, including expansions (NRR). I'm sourcing
from NetSuite for recognized revenue and Salesforce for contract dates and upsell events.

**Data Sources and the Q3 Problem**

The data quality issue is in Q3 of our FY2024 cohort. During that quarter, we had a billing system
migration that created about 40 accounts where the revenue recognition date in NetSuite doesn't match
the contract start date in Salesforce. The delta is small — less than 2% of that cohort's ARR — but
it creates a discontinuity in the retention calculation. If I include those accounts as-is, the Q3
GRR dips below the trailing 8-quarter average in a way that looks like a blip, not a trend, but
investors might ask about it.

My current options: (1) flag the 40 accounts as a data quality footnote and present the adjusted
figure; (2) manually reconcile each of the 40 accounts by pulling their original contracts from
Salesforce; or (3) exclude Q3 from the cohort chart and note the exclusion. Option 2 is the most
defensible but would take another two to three days. Catherine may prefer option 1 for speed.

**Where I Am**

Quarters 1, 2, 4, 5, 6, 7, and 8 are clean. Q3 is the blocker. The visual is built — I have the
waterfall chart, the retention curves, and the expansion revenue breakdown. It just needs clean Q3 data
or a documented decision about how to handle the gap.

**Deadline Pressure**

Catherine needs the final output before her investor summary narrative can be locked. That's the
dependency she mentioned in the data room update. I know she sent a note asking about my timeline.
I need to make a decision on the Q3 approach by Wednesday so I can either finish the reconciliation
or document the footnote and hand her a completed analysis by Thursday morning.
""",
                "scenes": [
                    {
                        "title": "Q1–Q2, Q4–Q8 cohort data validated and charted",
                        "stage": "complete",
                        "notes": "Seven of eight quarters are clean. Waterfall chart, retention curves, and expansion breakdown all built. Q3 is the only remaining blocker.",
                    },
                    {
                        "title": "Q3 FY2024 data quality issue — 40-account reconciliation",
                        "stage": "in_progress",
                        "notes": "Billing migration created 40 accounts with NetSuite/Salesforce date mismatch. Decision needed: footnote and adjust (fast) vs manual reconciliation (2-3 days, most defensible). Escalating to Catherine Wednesday.",
                    },
                    {
                        "title": "Final cohort analysis delivery to Catherine",
                        "stage": "in_progress",
                        "notes": "Targeting Thursday morning delivery for Catherine's review. Blocking the Series C ARR waterfall appendix. Must resolve Q3 approach by Wednesday night.",
                    },
                    {
                        "title": "Investor summary narrative support",
                        "stage": "awaiting_data",
                        "notes": "Catherine's investor summary appendix cannot be finalized until cohort output is delivered. Downstream dependency of this act.",
                    },
                ],
            },
            {
                "title": "Budget vs Actuals Automation",
                "color": "#d97706",
                "notes": """\
Right now, every monthly close takes five business days. Three of those days are me pulling data from
four systems — NetSuite for actuals, Rippling for payroll, AWS Cost Explorer for cloud spend, and
Salesforce for pipeline-to-revenue reconciliation — cleaning it in Excel, and formatting the output
for Catherine's review. It's repetitive, it's error-prone, and it doesn't have to be this way.

This project automates the data pull, the reconciliation, and the formatting. The goal is a two-day
close, which is what Catherine wants for Phase 3 of the FP&A dashboard modernization. But I'm not
waiting for the dashboard project to finish — I can build the automation pipeline now and plug it
into whatever BI tool they select later.

**API Integrations**

NetSuite has a REST API. I've already gotten API credentials and am testing the endpoints for
transaction-level actuals pulls. Rippling also has an API — payroll data comes out by department
and cost center, which is exactly what I need for headcount cost allocation. AWS Cost Explorer
has an API that I'm less familiar with, but there's good Python documentation for it. Salesforce
is the messiest — the SOQL queries I need to match pipeline stage to recognized revenue aren't
trivial, but I've gotten help from our RevOps analyst who already knows the schema.

**Reconciliation Logic**

The hardest part isn't the data pull — it's the reconciliation. The budget is in Excel (for now),
the actuals are in NetSuite, and the variance needs to be explained at the GL account level. I'm
building a Python script that reads the budget from a structured CSV export, pulls actuals via the
NetSuite API, and produces a variance report by department and GL account. Any variance above 5%
of budget at the account level gets flagged automatically for review.

**Error Handling**

Catherine's requirements are specific: if any API call fails, the script should log the failure
with a timestamp and the failed endpoint, send an alert to my email, and produce a partial report
that clearly marks which sections are incomplete. No silent failures. She reviewed the error
handling spec and signed off on it.

**Where I Am**

NetSuite integration is working in development. Rippling is in progress. AWS and Salesforce are
still in planning. I'm doing this in parallel with the cohort work, which means I'm mostly working
on it in evenings and during the parts of the day when I'm waiting on data from other people.
I'm learning Python as I go — using the cohort work as simpler practice and saving the harder
API logic for when I have more confidence.

**Timeline**

Catherine wants a two-day close by Q4. I think I can have the automation running for a trial close
in Q3 if the cohort crunch doesn't push everything back. The parallel run — automated vs manual —
will take two months before I'd trust it for a real close.
""",
                "scenes": [
                    {
                        "title": "NetSuite REST API integration",
                        "stage": "in_progress",
                        "notes": "API credentials obtained. Pulling transaction-level actuals in development environment. GL account mapping to budget categories in progress.",
                    },
                    {
                        "title": "Rippling payroll API integration",
                        "stage": "in_progress",
                        "notes": "API access granted. Department and cost center pull tested. Payroll allocation logic for headcount cost model being built.",
                    },
                    {
                        "title": "AWS Cost Explorer API integration",
                        "stage": "planning",
                        "notes": "API documentation reviewed. Waiting until NetSuite and Rippling integrations are stable before starting. RevOps analyst may help with Salesforce SOQL queries.",
                    },
                    {
                        "title": "Variance report and error handling framework",
                        "stage": "in_progress",
                        "notes": "Python variance report script drafted. 5% threshold flagging logic built. Error handling spec reviewed and approved by Catherine. Alert email integration pending.",
                    },
                    {
                        "title": "Q3 trial close — automated vs manual parallel run",
                        "stage": "planning",
                        "notes": "Targeting Q3 trial if cohort work doesn't push back schedule. Two-month parallel run required before real close. Catherine's target is a two-day close by Q4.",
                    },
                ],
            },
            {
                "title": "Vendor Contract Renewal Schedule",
                "color": "#b45309",
                "notes": """\
We have 47 active vendor contracts and, until I started this project, no centralized system to track
them. Some of them auto-renew. Some of them have 30-day cancellation windows. A few of them have
price escalators that nobody had flagged. I found out about this problem when a $180K software contract
auto-renewed in March because nobody caught the 60-day cancellation window. Catherine was not happy.

This project builds a centralized vendor contract database with automated renewal alerts so that
never happens again.

**The Inventory**

I've collected all 47 contracts from Legal, Procurement, and my own email. They exist as PDFs across
three different shared drives and two people's email inboxes. I've built a master spreadsheet with
the key fields: vendor name, contract value, renewal date, cancellation window, auto-renewal flag,
cost center owner, and the path to the actual contract document. That spreadsheet is now the source
of truth while I build the actual database.

**Auto-Renewal Risk**

Of the 47 contracts, 31 have auto-renewal clauses. Of those, 12 have cancellation windows of 60
days or less — meaning I need to flag them at least 90 days before renewal to give stakeholders
time to evaluate and decide. Three contracts are coming up for renewal in the next 90 days. I'm
tracking those manually right now and will send the owners a review request this week.

**Optimization Opportunities**

While building the inventory, I found three categories of potential savings. First, duplicate tooling:
we have two vendors providing overlapping functionality in the design tool category — I've flagged
this to the relevant department heads. Second, underutilized contracts: two SaaS tools have active
seat licenses where usage data shows fewer than 20% of seats are being used. Third, pricing escalators:
four contracts have 5–8% annual price increases baked in that nobody was tracking.

Total estimated annual savings if we rationalize the duplicate tools and renegotiate the escalators:
$340K, or about 0.8% of ARR. Not huge, but worth doing.

**Negotiations in Progress**

I'm currently in conversation with two vendors: one SaaS security tool (negotiating a flat renewal
instead of the 7% escalator) and one cloud monitoring vendor (evaluating whether to consolidate
their contract with AWS native tooling). Both renewals are in the next 60 days. Catherine is looped
in on both — she wants to see the final negotiated terms before I sign off.

**Tracking System**

I'm evaluating whether to use a lightweight AirTable base or just a well-structured Google Sheet
with a scheduled Apps Script to send Slack alerts. Given that this is mostly a tracking and alerting
problem rather than a workflow problem, I'm leaning toward the simpler option. Catherine wants
something that anyone on the team can update without training.
""",
                "scenes": [
                    {
                        "title": "Master contract inventory spreadsheet",
                        "stage": "complete",
                        "notes": "All 47 contracts inventoried. Key fields captured: value, renewal date, cancellation window, auto-renewal flag, cost center owner, document path. Three at-risk renewals flagged.",
                    },
                    {
                        "title": "Auto-renewal risk — 3 contracts in 90-day window",
                        "stage": "in_progress",
                        "notes": "Three contracts renewing in next 90 days. Owner review requests going out this week. Two in active negotiation (security tool, cloud monitoring vendor).",
                    },
                    {
                        "title": "Savings opportunity analysis",
                        "stage": "complete",
                        "notes": "$340K estimated annual savings identified: duplicate tooling, underutilized seats, pricing escalators. Flagged to department heads and Catherine.",
                    },
                    {
                        "title": "Tracking system build (AirTable vs Google Sheet)",
                        "stage": "in_progress",
                        "notes": "Evaluating AirTable vs Google Sheet + Apps Script. Leaning toward simpler option. Catherine wants something the full team can update without training.",
                    },
                    {
                        "title": "SaaS security tool renewal negotiation",
                        "stage": "in_progress",
                        "notes": "Negotiating flat renewal vs 7% escalator. Renewal in 60 days. Catherine reviewing final terms before sign-off.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I'm behind on the cohort analysis — Catherine needs it by Thursday and I still have data quality issues in Q3 data. What should I prioritize?",
                    },
                    {
                        "role": "cairn",
                        "content": "You have two decisions to make, and making them fast is more important than making them perfect right now.\n\nFirst decision: the Q3 reconciliation approach. Your three options are (1) footnote the 40 accounts and present the adjusted figure — fast, defensible with documentation; (2) manually reconcile all 40 accounts — two to three more days, most defensible, but blows your Thursday deadline; or (3) exclude Q3 from the chart with a note — riskiest from an investor optics standpoint. Given your deadline, option 1 is probably right. But this is Catherine's call to make, not yours.\n\nSecond decision: tell Catherine now, not Wednesday night. Your notes say she'd rather hear about a problem two days before her deadline than a perfect answer the night before. Today is Monday. That's two days. Send her a message explaining the Q3 issue and ask which approach she prefers. Let her choose.\n\nIf she picks option 1, you can finish the analysis today or tomorrow. If she picks option 2, you renegotiate the Thursday deadline now, not Thursday morning.",
                    },
                    {
                        "role": "user",
                        "content": "You're right. I'll message her now. What else is on my plate this week that could wait if I need to focus on the cohort work?",
                    },
                    {
                        "role": "cairn",
                        "content": "The things that can wait: the Rippling API integration for the budget automation — it's in progress but has no hard deadline this week. The tracking system decision for vendor contracts (AirTable vs Google Sheet) — that's evaluation work, not execution.\n\nThe things that cannot wait: the three vendor contracts with renewals in the next 90 days — you said you were sending owner review requests this week, and if you haven't yet, those go out today or tomorrow before you go into cohort focus mode. The security tool and cloud monitoring negotiations are in the 60-day window, so those also need attention before Thursday.\n\nEverything else is either longer-horizon planning or blocked on something external.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Did I miss any meetings today? I was heads down on the model.",
                    },
                    {
                        "role": "cairn",
                        "content": "No missed meetings on your calendar today. Your next scheduled meeting is your weekly sync with Denise on Tuesday at 11am — that's tomorrow.\n\nYou also have Catherine's Thursday review, which you're currently trying to prepare for. Nothing else flagged for today.",
                    },
                    {
                        "role": "user",
                        "content": "Okay good. Did Catherine respond to my message about the Q3 issue?",
                    },
                    {
                        "role": "cairn",
                        "content": "I don't have visibility into your email or messages directly. I can see what you've told me and what's in your notes, but I can't check your inbox.\n\nIf she hasn't responded and it's been a few hours, it might be worth a quick follow-up or a Slack message if that's faster for her. The sooner you have her decision on the Q3 approach, the more time you have to execute before Thursday.",
                    },
                    {
                        "role": "user",
                        "content": "She said option 1 — footnote and adjust. That means I can finish tonight. Can you remind me to run a final sanity check on the Q3 adjusted figures before I send the file tomorrow morning?",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted. I'll flag a reminder: run sanity check on Q3 adjusted figures before sending the cohort analysis to Catherine tomorrow morning.\n\nGood call on the footnote approach. Getting her a complete, documented analysis tomorrow morning gives her time to review before the Thursday session rather than the night before.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I feel like I'm always the last to understand how things work here compared to everyone else on the team. Is that normal for someone who came from banking?",
                    },
                    {
                        "role": "cairn",
                        "content": "It's a very common experience, and it makes sense given the context. You came from a bank — a slower-moving, more structured environment where processes were formalized and the learning curve was steep but well-defined. Tech companies, especially at growth stage, are deliberately informal and move fast. The implicit knowledge — how decisions get made, who to ask about what, what 'done' looks like — isn't written down.\n\nYour modeling skills are strong. The cohort analysis you're building is genuinely complex work, and you built it from scratch. The parts that feel unfamiliar are mostly about pace and communication norms, not capability.\n\nIs there a specific thing that's making you feel behind right now, or is it more general?",
                    },
                    {
                        "role": "user",
                        "content": "Mostly the Python stuff. Everyone assumes I know it and I'm learning it on the job.",
                    },
                    {
                        "role": "cairn",
                        "content": "That's a reasonable thing to feel uncomfortable with, and also a very fixable problem. You're already doing the right thing — using the budget automation project as a real-world Python project, not just tutorials.\n\nThe NetSuite API integration you have working in dev is real code. That's not a beginner exercise. Most people learning Python on the side aren't building API integrations with production financial data.\n\nIf there's a specific skill gap — error handling patterns, pandas for data manipulation, working with REST APIs — it might be worth naming it concretely so you can target it. What part of the Python work feels shakiest right now?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Quick question — the cloud monitoring vendor contract. Should I push to consolidate with AWS native tooling or just negotiate a flat renewal?",
                    },
                    {
                        "role": "cairn",
                        "content": "Based on what you've noted, the consolidation option is the more thorough play — if the AWS native tooling covers the same functionality, you eliminate a vendor, simplify the stack, and potentially reduce cost. But it's higher effort: you'd need Engineering to validate that AWS native tools meet their requirements before you can drop the vendor, and that evaluation might take longer than the 60-day renewal window you're in.\n\nThe flat renewal is lower risk and faster. It buys you another year to do the consolidation evaluation properly without deadline pressure.\n\nThe question is whether Engineering can give you a reliable answer on AWS native feasibility in the next three to four weeks. If yes, consolidation. If no, flat renewal and revisit next cycle.\n\nHas Engineering weighed in on this yet?",
                    },
                    {
                        "role": "user",
                        "content": "Not yet. I'll ask them this week. Good framing, thanks.",
                    },
                    {
                        "role": "cairn",
                        "content": "Makes sense. One thing to note: Catherine wants to review the final negotiated terms before you sign off on either path. Loop her in once you have Engineering's read and a proposed direction, not just the final document. She'll want to weigh in on the consolidation vs renewal decision itself if you're recommending consolidation.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Tomás works late on Wednesdays to prepare for Catherine's Thursday review sessions.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Tomás's weekly work pattern",
                    "pattern": "Late Wednesday prep for Thursday review",
                    "relevance": "Wednesday night is when he discovers deadline problems — escalation should happen before Wednesday",
                },
            },
            {
                "narrative": "Tomás is learning Python to automate his Excel workflows; he is building the budget vs actuals automation as his primary learning project.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Python skill development",
                    "approach": "Learning on the job via budget automation project",
                    "current_status": "NetSuite API working in dev; Rippling in progress",
                },
            },
            {
                "narrative": "Tomás experiences imposter syndrome about being at a tech company after transitioning from banking; he tends to go deep alone rather than escalate problems early.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Working style and mindset",
                    "pattern": "Heads-down before escalation; Catherine has explicitly asked him to escalate earlier",
                    "context": "First tech company role after 3 years in corporate banking",
                },
            },
            {
                "narrative": "Tomás has a weekly sync with Denise Washington (VP People) on Tuesdays at 11am.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Denise Washington",
                    "relationship": "Weekly sync partner",
                    "meeting": "Tuesdays at 11am",
                },
            },
            {
                "narrative": "The Q3 FY2024 cohort data has 40 accounts with a NetSuite/Salesforce date mismatch from the billing migration, creating a GRR discontinuity; Catherine approved option 1 (footnote and adjust).",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Q3 cohort data quality resolution",
                    "decision": "Footnote the 40 affected accounts and present adjusted figure",
                    "decided_by": "Catherine Liu",
                    "impact": "Cohort analysis can now be completed",
                },
            },
            {
                "narrative": "Tomás discovered $340K in annualized vendor savings: duplicate design tooling, underutilized seat licenses, and untracked pricing escalators across 47 contracts.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Vendor contract savings opportunities",
                    "estimated_savings": "$340K/year",
                    "categories": ["Duplicate tooling", "Underutilized seats", "Price escalators"],
                },
            },
            {
                "narrative": "Catherine must review final negotiated terms for vendor contracts before Tomás signs off — she is looped in on both the security tool and cloud monitoring renewal negotiations.",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Vendor negotiation approval process",
                    "requirement": "Catherine reviews final terms before sign-off",
                    "active_negotiations": ["SaaS security tool (vs 7% escalator)", "Cloud monitoring vendor (vs AWS native consolidation)"],
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },

    # =========================================================================
    # Profile 7: Denise Washington — VP of People Operations (HR)
    # =========================================================================
    {
        "id": "denise_washington",
        "identity": {
            "full_name": "Denise Washington",
            "department": "People Operations",
            "title": "VP of People Operations",
        },
        "personality": "verbose",
        "your_story": """\
# Denise Washington — VP of People Operations

I'm Denise Washington, VP of People Operations. I've spent 20 years building HR functions at startups
and scale-ups, and I've been through the 50-to-200 employee scaling journey three times now. Each time
I've learned something new — about org design, about the stories people tell themselves about performance,
about what makes a culture resilient versus just pleasant to work in.

I grew up in Atlanta and I still live there, though this role is fully remote. My family has been in
Atlanta for three generations, and I feel that history — of community, of building institutions — in
how I think about organizational culture. A company's culture is an institution. It shapes people. The
people doing the shaping have a moral responsibility to do it thoughtfully.

**My Background**

I have a bachelor's in organizational psychology from Spelman College and an MS in HR Management from
Georgia State. I'm a SHRM-CP currently working toward my SHRM-SCP certification, which I'm targeting
to complete in the next 18 months. I've been a SHRM member for 15 years and serve on the board of
the Atlanta HR Association.

My career started in talent acquisition, moved into HR business partnering, and eventually landed in
People leadership when the third company I worked at asked me to build the whole function from scratch
as we scaled from 60 to 220 employees. That experience — building from scratch — is what I love most.

**How I Work**

I write long messages. I think through my reasoning in writing, and I've found that sharing that
reasoning openly builds trust with the people I work with. Some people prefer short and direct — I
respect that, and I can adapt. But given the choice, I'll always give you the full context.

I host a monthly People Team Lunch & Learn that's open to the whole company. Topics rotate: sometimes
it's a deep dive on a People initiative, sometimes it's a guest speaker on leadership, sometimes it's
an AMA. It's one of the things I'm most proud of.

**Current Focus**

Three large initiatives: redesigning our performance review system from annual reviews to continuous
feedback (which I think of as the most important culture change we can make right now), a comprehensive
DEI strategic plan for 2026, and analyzing and acting on our biannual employee engagement survey.
These aren't separate projects to me — they're three facets of the same commitment to building a place
where people can do the best work of their lives.
""",
        "acts": [
            {
                "title": "Performance Review Cycle Redesign",
                "color": "#7c3aed",
                "notes": """\
This is the initiative I care most about right now, and also the one that makes me most nervous —
not because I doubt the direction, but because I know how deeply ingrained annual performance reviews
are in how most managers understand accountability and career development. We're asking people to
change a mental model, not just a process.

**The Problem with Annual Reviews**

Annual reviews encode a fiction: that performance is a once-a-year conversation. In practice, the
moments that most shape someone's development — a stretch assignment, a difficult client interaction,
a skill gap that's showing up in their work — happen throughout the year. When we wait twelve months
to have a structured conversation about those moments, we're too late. The feedback isn't useful. The
memory is incomplete. And the employee experience of "being evaluated" creates defensiveness rather
than openness.

**The Framework We're Building**

I'm designing what I'm calling "Quarterly Growth Conversations" — structured, forward-looking check-ins
between an employee and their manager that focus on three questions: What's going well? What's one
area for growth this quarter? What does the employee need from their manager to succeed?

Alongside the QGCs, we're implementing a lightweight peer feedback process — two to three peer inputs
per person per year, using a structured template focused on specific behaviors, not general impressions.
Peer feedback is collected asynchronously and summarized by the manager before the QGC.

We're also building skills-based career ladders for every function. Right now, career progression is
too manager-dependent and too vague. If an engineer doesn't know what "senior" looks like in concrete,
behavioral terms, they can't develop toward it. The career ladders will define levels by observable
skills and contributions, not tenure.

**Change Management**

The hardest part of this project is not the framework design — it's the change management. I'm
approaching it as a communication and trust problem. Managers need to feel like this system is
empowering them, not adding administrative burden or replacing their judgment. My framing: the annual
review was designed to hold managers accountable for having *one* conversation. The new system is
designed to make *many* conversations easier.

I'm piloting with the engineering team first. Engineering leadership was receptive, and engineers tend
to be direct feedback-givers and receivers, which makes them a good pilot cohort. I'll run one full
quarter with Engineering, collect structured feedback from managers and employees, and iterate before
the company-wide rollout.

**Manager Training**

I'm building a three-module training program for managers: (1) the philosophy and why we're changing,
(2) how to run a Growth Conversation in practice (with role-play exercises), and (3) how to receive
and deliver peer feedback effectively. Training will be delivered before the pilot launches and again
before company-wide rollout.

**Success Metrics**

Participation rate in QGCs (target: 90% completion per quarter), manager and employee satisfaction
scores from post-QGC surveys, and a reduction in regrettable attrition over four quarters. I'll also
track whether employees report clearer career direction in our biannual engagement survey.
""",
                "scenes": [
                    {
                        "title": "QGC framework and peer feedback template design",
                        "stage": "in_progress",
                        "notes": "Framework drafted. Three QGC questions defined. Peer feedback template being reviewed with HR business partner. Targeting finalization before engineering pilot launch.",
                    },
                    {
                        "title": "Skills-based career ladders — Engineering (pilot function)",
                        "stage": "in_progress",
                        "notes": "Working with VP Engineering to define levels by observable skills. IC ladder (L1–L5) drafted. Manager ladder in progress. Targeting completion before pilot launch.",
                    },
                    {
                        "title": "Manager training program — three modules",
                        "stage": "planning",
                        "notes": "Outline drafted. Module 1 (philosophy), Module 2 (practice), Module 3 (peer feedback). Delivery format: live 90-minute sessions + recorded async version. Scheduling for Q3.",
                    },
                    {
                        "title": "Engineering pilot — Q3 launch",
                        "stage": "planning",
                        "notes": "Engineering leadership confirmed as pilot cohort. One full quarter of QGCs. Structured feedback collection at end of pilot. Company-wide rollout planned for Q4 based on learnings.",
                    },
                    {
                        "title": "Post-pilot iteration and company-wide rollout plan",
                        "stage": "planning",
                        "notes": "Rollout plan outline complete. Iteration cycle depends on pilot feedback. Company-wide launch targeted for Q4. Communication plan being drafted.",
                    },
                ],
            },
            {
                "title": "DEI Strategic Plan 2026",
                "color": "#6d28d9",
                "notes": """\
I want to be honest about what DEI strategy often is: a collection of well-intentioned programs that
aren't connected to a theory of change. We've had some of that here. The DEI work I'm building for
2026 is designed to be different — rooted in data, tied to business outcomes, and owned by the whole
leadership team, not just People Ops.

**Hiring Pipeline Analysis**

The foundation of any serious DEI effort is understanding where the gaps are. I've been working with
our recruiting team (Kai specifically) to pull three years of hiring data: application rates, phone
screen pass rates, offer rates, and acceptance rates — broken down by role, level, and the demographic
data we have available. The goal is to identify where in the funnel we're losing candidates from
underrepresented groups, because the intervention has to match the drop-off point. If the drop-off
is at application, the problem is sourcing and employer brand. If it's at the interview stage, the
problem is interview process or bias. If it's at offer acceptance, the problem may be compensation
or culture signals.

**Employee Resource Groups**

We currently have two ERGs — a women's network and an LGBTQ+ alliance — that were started organically
by employees. They're valuable but underfunded and operating without formal support structures. I'm
developing an ERG charter framework that gives each group a budget, a liaison in People Ops, a clear
mandate, and access to executive sponsors. I'm also working with three employee groups who've expressed
interest in starting new ERGs: a BIPOC employee network, a parents and caregivers group, and a
disability and neurodiversity alliance.

**Pay Equity Audit**

This is the piece I'm most nervous about politically, and also the piece I consider most essential.
We've engaged an outside compensation consultant to run a regression-based pay equity analysis
controlling for role, level, tenure, and performance rating. The analysis will surface unexplained
pay gaps — if a gap exists after controlling for legitimate factors, it's a problem we need to fix,
full stop. The CEO and board are aware this is happening. I've committed to sharing the findings and
the remediation plan with the full company.

**Inclusive Leadership Training**

I'm designing a six-module inclusive leadership curriculum for all managers. Topics: unconscious bias
in decision-making, inclusive meeting facilitation, sponsorship vs mentorship, giving feedback across
difference, psychological safety, and allyship in practice. The curriculum will be delivered over
six months, one module per month. External facilitators will run modules 1, 4, and 6 because those
are the ones where outside expertise adds credibility.

**Metrics Dashboard**

None of this matters if we can't measure it. I'm building a DEI metrics dashboard that tracks: hiring
funnel diversity by stage, representation by level and function, promotion rates by demographic group,
engagement survey scores by demographic cohort, and pay equity gap trends over time. The dashboard
will be reviewed quarterly by the leadership team and annually by the board.

**Budget Allocation**

DEI budget for 2026 is $340K, which covers: pay equity audit and remediation reserves ($120K), ERG
program budgets ($60K), inclusive leadership training facilitation ($80K), recruiting tools and
sourcing for underrepresented pipelines ($50K), and metrics and analytics infrastructure ($30K).
""",
                "scenes": [
                    {
                        "title": "Hiring pipeline diversity analysis (3-year lookback)",
                        "stage": "in_progress",
                        "notes": "Working with Kai to pull funnel data by role, level, and demographic group. Identifying drop-off points. Three years of data pulled; analysis in progress.",
                    },
                    {
                        "title": "ERG charter framework and new group launches",
                        "stage": "in_progress",
                        "notes": "Charter framework drafted. Three new ERGs in formation: BIPOC network, parents/caregivers, disability/neurodiversity alliance. Budget and executive sponsor assignments in progress.",
                    },
                    {
                        "title": "Pay equity audit — external compensation consultant",
                        "stage": "in_progress",
                        "notes": "Consultant engaged. Regression analysis methodology agreed. Data export from Rippling in progress. CEO and board informed. Findings and remediation plan will be shared company-wide.",
                    },
                    {
                        "title": "Inclusive leadership training curriculum",
                        "stage": "planning",
                        "notes": "Six-module curriculum designed. External facilitators confirmed for modules 1, 4, 6. Scheduling for monthly delivery starting Q3. All people managers required to attend.",
                    },
                    {
                        "title": "DEI metrics dashboard build",
                        "stage": "planning",
                        "notes": "Dashboard spec completed. Working with data team on Snowflake models for hiring funnel and promotion rate tracking. Quarterly leadership review and annual board review planned.",
                    },
                ],
            },
            {
                "title": "Employee Experience Survey & Action Plan",
                "color": "#5b21b6",
                "notes": """\
We run a biannual employee engagement survey, and I want to be honest about something: most companies
run engagement surveys and then do very little with them. The survey becomes a ritual, the results
get presented to leadership, a few action items get captured, and six months later when the next
survey comes around, employees have largely forgotten anything changed. That pattern destroys
trust. People stop responding honestly because they've learned nothing happens.

I'm committed to breaking that pattern. Every finding from this survey will have an owner and a
visible action tied to it. Employees will be able to see, in a public internal document, what we
heard and what we're doing about it.

**Survey Design**

We're using a validated 40-question survey covering seven dimensions: sense of purpose, manager
effectiveness, growth and development, belonging and inclusion, work-life integration, cross-functional
collaboration, and trust in leadership. We're including the eNPS question as a single headline metric.
The survey is anonymous and administered through Culture Amp.

I've added six open-text questions this cycle, more than we've had before. Quantitative data tells
you what's happening; qualitative data tells you why. I want both.

**Response Rate Strategy**

Our last survey got a 71% response rate. I want 85% this cycle. The strategy: CEO sends a kickoff
message explaining why the survey matters and what we did with the last one, managers are trained
to encourage participation without pressuring for specific responses, and we close the survey on a
Friday to capture people who need a full week to find time. Reminders go out at day 3 and day 7.
The survey window is 10 days.

**Analysis Approach**

I'll analyze results by three cuts: team/department, tenure cohort (under 1 year, 1–3 years, 3+
years), and demographic group (to the extent sample sizes allow statistical significance). The
tenure cut often reveals the most interesting signal — new employees rate things differently than
veterans, and the gap can tell you whether your onboarding experience is setting people up for success
or failure.

**Previous Survey Findings**

The last survey (eight months ago) surfaced three themes: growth and development rated lowest of all
seven dimensions (3.4/5.0 average), cross-functional collaboration scored high in aspiration but
low in actual experience (lots of "we want to collaborate but don't know how"), and trust in
leadership scored well at the CEO level but dropped significantly at the VP and director level.

Those three findings are driving three of our active initiatives: the performance review redesign
(addresses growth and development), a new cross-functional project pod framework I'm piloting with
Engineering and Product, and the inclusive leadership training (addresses mid-level leadership gaps).

**Action Planning with Department Leads**

After the results are in, I run a structured action planning session with each department lead. The
format: I present their team's results, we identify two to three team-specific themes, and they own
drafting an action plan with me as a thought partner. The plans are shared with their teams and
tracked in a shared doc. Progress is reviewed at the 90-day mark.
""",
                "scenes": [
                    {
                        "title": "Survey design and Culture Amp configuration",
                        "stage": "complete",
                        "notes": "40-question survey finalized. Six open-text questions added. Culture Amp configured. eNPS included as headline metric. Survey window: 10 days, closing on a Friday.",
                    },
                    {
                        "title": "Response rate campaign — CEO kickoff and manager training",
                        "stage": "in_progress",
                        "notes": "CEO kickoff message drafted and scheduled. Manager training session on participation encouragement completed. Day 3 and Day 7 reminder templates ready.",
                    },
                    {
                        "title": "Survey launch and data collection",
                        "stage": "in_progress",
                        "notes": "Survey live. Tracking daily response rate. Current rate at day 4: 58%. On track for 85% target if momentum holds through weekend.",
                    },
                    {
                        "title": "Results analysis (by team, tenure, demographic)",
                        "stage": "planning",
                        "notes": "Three-cut analysis planned: team/department, tenure cohort, demographic group. Culture Amp will surface quantitative data; qualitative themes will be coded manually by Denise and one HR BP.",
                    },
                    {
                        "title": "Department lead action planning sessions",
                        "stage": "planning",
                        "notes": "Structured action planning sessions scheduled with each department lead after results are finalized. Each lead owns a 2-3 item action plan. 90-day progress review built in.",
                    },
                    {
                        "title": "90-day action plan progress reviews",
                        "stage": "planning",
                        "notes": "Progress review cadence set. Plans shared with teams publicly. Tracking document template built. Intended to close the 'we said something would happen and nothing did' loop.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Good morning, Cairn! I've been thinking a lot about how we can make the performance review transition feel less threatening to managers. Many of them grew up with annual reviews and see them as the only way to hold people accountable. I want to frame our new continuous feedback model as empowering rather than replacing — but I'm wrestling with how to get that message right. What are the key things I should be thinking about as I design the manager training?",
                    },
                    {
                        "role": "cairn",
                        "content": "Good morning, Denise. The framing challenge you're describing is exactly the right thing to spend time on before the training design is locked.\n\nThe underlying anxiety for most managers is that annual reviews provide cover: one structured, documented conversation per year that proves they 'did the thing.' If you remove that ritual without replacing the sense of accountability it provided, managers will feel exposed — like they're being asked to do something harder without a safety net.\n\nThe reframe that tends to work: annual reviews hold managers accountable for having *one conversation*. The new system makes *continuous* conversations easier, shorter, and lower-stakes. A quarterly check-in isn't an evaluation — it's a 30-minute calibration. The cumulative effect is more accountability, not less, because nothing is being stored up for the year-end conversation.\n\nFor the training design specifically, Module 2 (how to run a Growth Conversation in practice) will do the most work here. Role-play exercises that let managers experience receiving a QGC as an employee — not just delivering one — can shift the felt sense quickly. What's your current thinking on that module's structure?",
                    },
                    {
                        "role": "user",
                        "content": "That's a really helpful reframe. I'm thinking Module 2 should have a live role-play component where managers pair up, one plays the manager and one plays the employee, and then they debrief together about what it felt like from both sides. I want them to notice how different it is from the evaluative tone of a traditional review.",
                    },
                    {
                        "role": "cairn",
                        "content": "That's a strong design choice. The debrief after the role-play is the highest-leverage moment — that's where the insight often lands. A few things that tend to make these debriefs more effective:\n\nAsk the person who played the *employee* to speak first. They'll often name things the person who played the manager didn't notice they were doing — tone shifts, leading questions, moments where the conversation felt evaluative rather than curious. Starting from the employee's experience grounds the debrief in impact, not intent.\n\nGive them a structured debrief prompt, not an open question. Something like: 'What moment in the conversation felt most like a Growth Conversation? What moment felt most like a traditional review?' Contrast helps people locate the specific behaviors to change, rather than just a general feeling.\n\nAre you planning to have people role-play with their actual direct reports in the exercise, or with peers across teams? Peers across teams tends to create more psychological safety for the exercise, though it loses some of the relationship specificity.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Can you give me an overview of what my week looks like? I want to make sure I'm spacing my energy well — I have a lot of emotionally demanding work this week.",
                    },
                    {
                        "role": "cairn",
                        "content": "Looking at what you've shared with me about your current projects and cadences, here's how the week maps out:\n\nYour People Team Lunch & Learn is a monthly commitment — if that's this week, that's a preparation and facilitation load on top of everything else. The pay equity audit data is in progress with the external consultant, so you may get questions or data requests. The engagement survey is currently live (day 4, at 58% response rate), so you're likely checking in on that daily and may be nudging managers to encourage participation.\n\nThe emotionally demanding thread this week is probably the pay equity work. That conversation — both internally and with the consultant — tends to surface uncomfortable findings and requires you to hold both the data and the political weight of what to do with it.\n\nWhat would it help to think through this morning? I can hold the logistical picture while you focus on where to direct your attention.",
                    },
                    {
                        "role": "user",
                        "content": "The Lunch & Learn is next week, so that's off the plate. The pay equity meeting is Thursday. What I'm most worried about is the response rate — if it's still at 58% by Thursday, we're going to miss the 85% target. What's my lever there?",
                    },
                    {
                        "role": "cairn",
                        "content": "At day 4 with a 10-day window and 58% response, you still have time — most surveys see a second surge in the final two days, especially if there's a visible reminder and the CEO's message has been internalized.\n\nYour levers in order of likely impact:\n\nFirst, manager activation. If your managers haven't personally encouraged their teams to respond — not just forwarded the reminder email, but actually said in a team meeting or Slack 'I care about this, please take it' — that's your highest-leverage action. Employees respond to manager signals more than company-wide messages. A short message to all managers today asking them to personally encourage their teams between now and Thursday would move the needle.\n\nSecond, the day 7 reminder. Your template is ready — if day 7 falls Thursday or Friday, you'll want to time the send for mid-morning when people are most likely to have 10 minutes.\n\nThird, identify which teams have the lowest response rates in Culture Amp and target those team leads specifically for a personal nudge. Low-response teams are usually either very busy or have lower trust — a direct conversation from you or their manager can help.\n\nDo you want help drafting a manager activation message for today?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I've been working toward my SHRM-SCP for a while now. What do I have going on in that space?",
                    },
                    {
                        "role": "cairn",
                        "content": "From what you've shared, you're targeting SHRM-SCP completion in the next 18 months. You're currently a SHRM-CP and have been a SHRM member for 15 years, so the credential knowledge base is there.\n\nI don't have specifics on your study schedule or exam prep status beyond the 18-month target. Is this something you're actively tracking, or has it been on the back burner with everything else going on? If it matters to you this week, I can help you think about where to carve out time for it.",
                    },
                    {
                        "role": "user",
                        "content": "It's been on the back burner, honestly. I keep telling myself I'll get to it once the performance review redesign is off the ground. But I know that's not how it works — there's always another initiative.",
                    },
                    {
                        "role": "cairn",
                        "content": "You're naming the pattern accurately. 'Once X is done' is a structure that tends to preserve the status quo indefinitely, because X is never fully done — it evolves into the next thing.\n\nThe SHRM-SCP matters to you. If it didn't, you wouldn't have set an 18-month target. The question isn't whether to do it — it's how to protect enough time for it given everything else.\n\nOne approach that works for some people: treat exam prep like a recurring meeting with yourself. Block 90 minutes twice a week on the calendar, give it a location (your desk, not a meeting room), and let it be non-negotiable for three months to see if the habit holds. The first few weeks feel forced. After that, the rhythm often becomes self-sustaining.\n\nWould it help to look at your calendar and identify two recurring slots that are genuinely protectable?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I'm preparing for my action planning session with the Engineering department lead after the survey closes. The last survey showed Engineering scored particularly low on growth and development. I want to go into that conversation prepared. What should I be thinking about?",
                    },
                    {
                        "role": "cairn",
                        "content": "Engineering's low score on growth and development from the last survey (3.4/5.0 was the company average — if Engineering was below that, it's a meaningful signal) is especially relevant right now because you're also piloting the performance review redesign with Engineering. Those two threads are going to intersect in the action planning conversation.\n\nA few things worth thinking through before you go in:\n\nThe Engineering lead may interpret the survey result as a skills training problem — 'we need more learning and development budget.' That's the most common first read. Before accepting that frame, it's worth asking whether the underlying issue is clarity of career path (which the career ladders you're building directly address), or access to growth opportunities, or recognition for the growth that's already happening. Those have different interventions.\n\nThe pilot launch of the QGC system gives you a natural frame for the action planning session: some of what Engineering is asking for through the survey — clearer development direction, more regular feedback — is exactly what the pilot is designed to provide. You can name that explicitly and ask the department lead to treat the pilot as one of the action items.\n\nWhat's your relationship with the Engineering department lead like? That context shapes how directive versus facilitative you'll want to be in the session.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Denise believes performance reviews should be developmental, not evaluative — the design of the continuous feedback system is built on this principle.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Performance review philosophy",
                    "belief": "Reviews should develop people, not judge them",
                    "implication": "Framing of QGC system as 'growth conversations' is intentional",
                },
            },
            {
                "narrative": "Denise hosts a monthly People Team Lunch & Learn open to the whole company — topics rotate among People initiatives, guest speakers on leadership, and AMAs.",
                "entity_type": "task",
                "entity_data": {
                    "task": "Monthly People Team Lunch & Learn",
                    "cadence": "Monthly",
                    "audience": "Company-wide",
                    "format": "Rotating: initiative deep dive, guest speaker, AMA",
                },
            },
            {
                "narrative": "Denise is working toward her SHRM-SCP certification with an 18-month target; it has been deprioritized behind active initiatives and she is aware of the pattern.",
                "entity_type": "task",
                "entity_data": {
                    "task": "SHRM-SCP certification",
                    "target": "Within 18 months",
                    "status": "On back burner — active initiatives taking priority",
                    "note": "Denise acknowledges this is a recurring avoidance pattern",
                },
            },
            {
                "narrative": "The previous engagement survey found Growth & Development rated lowest (3.4/5.0), cross-functional collaboration low in actual experience, and VP/Director-level trust lower than CEO-level trust.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Engagement survey findings (8 months ago)",
                    "findings": [
                        "Growth & Development: 3.4/5.0 (lowest dimension)",
                        "Cross-functional collaboration: high aspiration, low actual experience",
                        "Leadership trust: high at CEO level, drops at VP/Director level",
                    ],
                    "actions_driven": ["Performance review redesign", "Cross-functional project pod pilot", "Inclusive leadership training"],
                },
            },
            {
                "narrative": "Denise has committed to sharing the pay equity audit findings and remediation plan with the full company; the CEO and board are aware.",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Pay equity audit transparency commitment",
                    "decision": "Full company disclosure of findings and remediation plan",
                    "stakeholders_informed": ["CEO", "Board"],
                },
            },
            {
                "narrative": "The engineering team is the pilot cohort for the QGC performance review system; one full quarter of pilot data is required before company-wide rollout.",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Performance review redesign pilot",
                    "pilot_cohort": "Engineering team",
                    "duration": "One full quarter",
                    "rollout_target": "Q4 company-wide, contingent on pilot learnings",
                },
            },
            {
                "narrative": "Denise's DEI budget for 2026 is $340K, allocated across pay equity audit/remediation, ERG programs, inclusive leadership training, recruiting tools, and metrics infrastructure.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "DEI budget 2026",
                    "total": "$340K",
                    "allocations": {
                        "pay_equity_audit_and_reserves": "$120K",
                        "erg_programs": "$60K",
                        "inclusive_leadership_training": "$80K",
                        "recruiting_tools_and_sourcing": "$50K",
                        "metrics_and_analytics": "$30K",
                    },
                },
            },
            {
                "narrative": "Denise works with Kai Nakamura on hiring pipeline diversity analysis, coordinating three-year funnel data for the DEI strategic plan.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Kai Nakamura",
                    "relationship": "Collaborator on DEI hiring pipeline analysis",
                    "collaboration": "Three-year hiring funnel data by role, level, and demographic group",
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },

    # =========================================================================
    # Profile 8: Kai Nakamura — Technical Recruiter (HR)
    # =========================================================================
    {
        "id": "kai_nakamura",
        "identity": {
            "full_name": "Kai Nakamura",
            "department": "People Operations",
            "title": "Technical Recruiter",
        },
        "personality": "terse",
        "your_story": """\
# Kai Nakamura — Technical Recruiter

Technical recruiter focused on engineering hiring. 7 years in recruiting, 3 as a software engineer
before that. Japanese-American, based in Seattle.

Switched from engineering to recruiting after realizing I was better at finding great engineers than
being one. Use that background every day — I can read a resume technically, talk shop with candidates,
and spot when a job description is bullshit. Candidates notice when the recruiter knows what they're
talking about.

**Background**

B.S. in Computer Science from UW. Spent 3 years as a backend engineer at a mid-size startup before
making the switch. Got my first recruiting role at a technical staffing agency, moved in-house after
18 months. This is my third in-house role.

I prefer referrals over cold outreach. A warm intro converts at 4x the rate of a LinkedIn message
and the candidate experience is better from the start. I track everything in a personal spreadsheet
updated daily — pipeline by role, source, stage, and rejection reason. I don't trust ATS reporting.

**How I Work**

Short messages. Fast responses. I expect the same. If I send you a one-line Slack, a one-line reply
is fine. I'm not being rude — I'm being efficient.

I track metrics obsessively: time-to-offer, offer acceptance rate, pipeline velocity by stage,
source conversion rate. I know where every bottleneck is. I know which hiring managers are slow to
schedule and which interview panels are inconsistent. I have opinions about how to fix all of it.

**Current Focus**

Three things: filling 8 engineering roles by end of Q2 (the most important thing), cutting time-to-hire
from 45 to 28 days by fixing the interview process, and refreshing our employer brand so that engineers
actually want to talk to us.
""",
        "acts": [
            {
                "title": "Q2 Engineering Hiring Sprint",
                "color": "#dc2626",
                "notes": """\
8 engineering roles to fill by end of Q2. This is the primary objective. Everything else is secondary.

**Role Breakdown**

The 8 roles: 3 Senior Backend Engineers, 2 Mid-level Backend Engineers, 2 Frontend Engineers (React),
1 ML Engineer. The ML role is the hardest — it's a specialized skill set and we're competing with
FAANG, which means our comp has to be competitive and our speed has to be better than theirs. Most
candidates with ML experience at the level we need are getting multiple offers within 3 weeks of
starting a job search. If we're slow, we lose.

**Pipeline Status by Role**

Senior Backend (3 roles): 12 active candidates total across the three openings. 4 in final-round
interviews, 2 have offers extended and are in decision, 6 at earlier stages. On track for 2 of 3
roles closing this quarter; the third may slip to Q3 depending on offer decisions this week.

Mid-level Backend (2 roles): 8 active candidates. 3 in final rounds. Both roles have realistic paths
to close this quarter.

Frontend (2 roles): 6 active candidates. Pipeline is thinner than I'd like. Sourcing is the bottleneck —
React engineers at this level are heavily recruited. Increased LinkedIn Recruiter usage for this
specifically and activated two employee referral incentives. Offer for role 1 possible end of Q2.
Role 2 may slip.

ML Engineer (1 role): 4 candidates, 1 in final round, 1 declined to interview, 2 in process. The
finalist is currently evaluating three other offers. We need to move faster on the debrief and get
an offer out this week if we want a chance. I've escalated urgency to the hiring manager.

**Sourcing Channels**

Primary: employee referrals (highest conversion rate, best candidate quality). Secondary: LinkedIn
Recruiter for targeted outreach. Tertiary: job boards (Greenhouse-sourced, lower conversion but
volume). For ML specifically: university research networks and conference speaker lists from NeurIPS
and ICML.

**Competitive Landscape**

FAANG is the main competition for the Senior Backend and ML roles. Our advantages: faster process
(when we execute it correctly — which is exactly what the process optimization act is designed to
fix), more engineering ownership in smaller org, no totem-pole career progression timelines. I
use those points explicitly in every sourcing message and recruiter screen.

**Offer Acceptance Rate**

Current Q2 acceptance rate: 73%. Target: 85%. The gap is mostly from two declines — one Frontend
candidate who took a remote-first offer over ours (we're hybrid), one Senior Backend candidate who
got a higher comp offer from a late-stage startup. I'm tracking decline reasons explicitly.

**Blockers**

Scheduling latency is the main process blocker — some hiring managers take 48–72 hours to confirm
interview slots. This is directly addressed in the process optimization act. The ML role is also
hampered by a comp band that I believe is below market; I've flagged this to Denise and Catherine
for review.
""",
                "scenes": [
                    {
                        "title": "Senior Backend — 2 offers in decision",
                        "stage": "awaiting_data",
                        "notes": "Two candidates evaluating offers. Decision expected this week. Third role has 4 candidates in final round. All three roles are on track but margin is thin.",
                    },
                    {
                        "title": "ML Engineer — finalist with 3 competing offers",
                        "stage": "in_progress",
                        "notes": "Finalist in final round. Has three other offers. Need debrief completed and offer extended this week. Escalated urgency to hiring manager. Comp band may be a blocker.",
                    },
                    {
                        "title": "Frontend — pipeline depth insufficient",
                        "stage": "in_progress",
                        "notes": "Only 6 active candidates for 2 roles. Increased LinkedIn Recruiter usage. Two employee referral incentives activated. Role 1 may close Q2; Role 2 likely slips.",
                    },
                    {
                        "title": "Q2 close tracking — all 8 roles",
                        "stage": "in_progress",
                        "notes": "Daily tracking in personal spreadsheet. Current projection: 5 of 8 roles close Q2, 3 slip to Q3 (1 Senior Backend, 1 Frontend, possible slip on ML depending on offer decision).",
                    },
                    {
                        "title": "ML comp band review with Denise and Catherine",
                        "stage": "awaiting_data",
                        "notes": "Flagged ML comp band as likely below market. Pending comp review. If not adjusted, ML hire risk increases significantly given candidate's competing offers.",
                    },
                ],
            },
            {
                "title": "Interview Process Optimization",
                "color": "#b91c1c",
                "notes": """\
Current time-to-hire: 45 days from first recruiter contact to offer accepted. Target: 28 days.
That's a 38% reduction. I know where the days are going — I've traced every stage of the funnel
for the last 12 months.

**Current Bottlenecks**

Biggest time sink: scheduling. Average of 4.2 days between each stage due to hiring manager and
panel availability. This alone accounts for 12–14 days of lost time across a typical 3-stage process.
Second: technical assessment — we currently use live coding interviews which require simultaneous
engineer and candidate availability. Live coding adds scheduling complexity on top of an already
slow system. Third: debrief to offer. Average of 3.8 days from final interview to offer letter sent.
This should be 24 hours for competitive candidates.

**Proposed Changes**

Async coding assessments: replace live coding interviews with a take-home assessment for the first
technical screen. Candidates complete it on their own schedule within a 5-day window. Reviewers
grade async. This eliminates 2–3 days of scheduling friction per candidate. Trade-off: some
candidates dislike take-home tests; we'll monitor candidate satisfaction scores to track any drop.

Restructured panels: current interview panels are ad hoc — whoever is available. Moving to fixed
interview panels per role, assigned at role launch. Panel members are expected to hold blocks for
interviews. No more Frankensteining a panel the day before.

Automated scheduling: Calendly for all interview scheduling, integrated with Greenhouse. Candidates
book directly. Eliminates the recruiter-as-scheduler bottleneck entirely for stages 1 and 2.

Debrief to offer SLA: 24-hour SLA from final interview to debrief completion, 24-hour SLA from
debrief to offer sent. Total: offer within 48 hours of final interview for candidates we want.
Hiring managers have been briefed.

**A/B Test Results**

I've been running the async assessment change with 40% of candidates for the past 6 weeks. Results:
time-to-first-technical-screen reduced by 2.9 days on average. Candidate satisfaction score on
that stage unchanged (4.2/5.0 in both groups). No measurable change in technical screen pass rate.
Shipping the change to all candidates next month.

Automated scheduling is live for Stage 1 (recruiter screen). Stage 2 rollout pending panel
restructuring being in place — don't want to create a scheduling system that feeds into a broken panel.

**Candidate Experience Scores**

Overall candidate experience NPS: 42. Industry benchmark: ~35. Good but I want 55+. Main friction
point candidates name: time between stages (consistent with my bottleneck analysis), and unclear
timeline communication. Building a candidate-facing timeline template that gets sent automatically
at each stage transition to address the communication gap.
""",
                "scenes": [
                    {
                        "title": "Async coding assessment — full rollout",
                        "stage": "in_progress",
                        "notes": "A/B test complete. 2.9-day reduction in time-to-technical-screen. No candidate satisfaction drop. Shipping to all candidates next month.",
                    },
                    {
                        "title": "Fixed panel structure — all engineering roles",
                        "stage": "in_progress",
                        "notes": "Panel assignments per role being defined with hiring managers. Calendar blocks for panel members being set. Required before Stage 2 automated scheduling rollout.",
                    },
                    {
                        "title": "Automated scheduling — Stage 2 rollout",
                        "stage": "awaiting_data",
                        "notes": "Waiting on fixed panel structure to be in place before expanding Calendly to Stage 2. Stage 1 automated scheduling already live.",
                    },
                    {
                        "title": "24-hour debrief-to-offer SLA enforcement",
                        "stage": "in_progress",
                        "notes": "SLA defined and hiring managers briefed. Tracking compliance in spreadsheet. Three violations in past 4 weeks — all from same hiring manager. Escalated to Denise.",
                    },
                    {
                        "title": "Candidate-facing timeline communication template",
                        "stage": "planning",
                        "notes": "Template drafted. Auto-send at each stage transition via Greenhouse. Addresses 'unclear timeline' feedback in candidate NPS qualitative data.",
                    },
                ],
            },
            {
                "title": "Employer Brand Refresh",
                "color": "#991b1b",
                "notes": """\
Engineers Google us before they respond to our outreach. What they find is a careers page that
hasn't been updated in two years, job descriptions that read like compliance documents, and no
social proof from actual engineers at the company. That has to change.

**Content Pipeline**

The plan: six engineer spotlights (written Q&A format, one published per month), two video pieces
(office tour and a 'day in the life' of an engineer), updated careers page copy, and a complete
rewrite of all engineering job descriptions. I have four engineers who've agreed to participate
in spotlights — need two more, specifically from frontend and ML backgrounds for representation.

Engineer spotlights will be published on the careers page and cross-posted to LinkedIn. Each
one is short — 400–600 words, three to four questions, engineer's own voice. I'm not doing PR
polish. Candidates see through that.

**Photographer and Videographer Coordination**

I've identified two vendors: one local photographer (for headshots and office stills), one
video production company for the two video pieces. Photographer is confirmed, shooting next week.
Videographer proposal received — budget is within range, awaiting sign-off. Both will require
engineer participants for the video pieces; I'm coordinating with engineering managers to
identify willing volunteers who are comfortable on camera.

**Job Description Rewrites**

Current JDs are a mess — pasted from old versions, inconsistent formatting, requirements inflation
(every role asks for 8+ years experience in technologies that didn't exist 8 years ago). I'm
rewriting all 12 active engineering JDs using a template: what you'll build, what you'll learn,
what we're looking for (split into must-haves and nice-to-haves), and what we offer. Short.
Specific. No buzzwords.

**Inclusive Language Audit**

Running every JD through Textio before final publish. I'm also removing the "culture fit"
language that's crept into some of our descriptions — that phrase is a red flag for candidates
who've experienced discrimination and it signals the wrong things to anyone who knows how
sourcing bias research works. Replacing with "collaborative and direct working style" plus
specific behavioral examples.

**Metrics**

Tracking: careers page unique visitors (baseline: 1,200/month), job application conversion rate
from careers page (baseline: 2.4%), inbound application rate per open role, and source attribution
for new applicants from employer brand content. 90-day targets: 30% increase in page visitors,
application conversion rate to 3.5%, one attributable hire sourced from employer brand content.
""",
                "scenes": [
                    {
                        "title": "Engineer spotlight content — 4 of 6 confirmed",
                        "stage": "in_progress",
                        "notes": "Four engineers confirmed. Need one frontend, one ML. Coordinating with engineering managers for introductions. First spotlight published next month.",
                    },
                    {
                        "title": "Photographer shoot — next week",
                        "stage": "in_progress",
                        "notes": "Photographer confirmed. Shooting office and headshots next week. Shot list sent. 12 engineer participants identified and briefed.",
                    },
                    {
                        "title": "Videographer sign-off and shoot scheduling",
                        "stage": "awaiting_data",
                        "notes": "Proposal received. Budget within range. Awaiting sign-off (Denise / Finance). Two video pieces: office tour and day-in-the-life. On-camera volunteers needed from engineering.",
                    },
                    {
                        "title": "JD rewrites — all 12 engineering roles",
                        "stage": "in_progress",
                        "notes": "New JD template finalized. 7 of 12 rewrites complete. 5 remaining. Textio inclusive language check on all before publish. Removing 'culture fit' language throughout.",
                    },
                    {
                        "title": "Careers page update and go-live",
                        "stage": "planning",
                        "notes": "New copy drafted. Waiting on final engineer spotlights and photography before page goes live. Target: end of Q2. Tracking baseline metrics now for 90-day comparison.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {"role": "user", "content": "Open reqs status?"},
                    {
                        "role": "cairn",
                        "content": "8 open roles. Current snapshot:\n\n- Senior Backend (3): 2 offers out, 1 in final rounds\n- Mid-level Backend (2): 3 in final rounds, on track\n- Frontend (2): thin pipeline, 6 candidates, sourcing active\n- ML Engineer (1): 1 finalist with 3 competing offers, needs offer this week\n\nProjected Q2 close: 5 of 8. ML and 1 Frontend most at risk.",
                    },
                    {"role": "user", "content": "ML offer — where's the holdup?"},
                    {
                        "role": "cairn",
                        "content": "Debrief not done yet. Hiring manager is the bottleneck. Candidate has competing offers and is deciding this week. You escalated urgency to the hiring manager — still waiting on response.\n\nAlso: comp band may be the issue even if you move fast. You flagged it to Denise and Catherine for review. That's still pending.",
                    },
                    {"role": "user", "content": "I'm pinging the hiring manager now. Flag me if comp review comes back."},
                    {
                        "role": "cairn",
                        "content": "Noted. Will flag when comp review responds. Good luck on the ping — candidate has maybe 3–4 days before they decide.",
                    },
                ],
            },
            {
                "messages": [
                    {"role": "user", "content": "Calendar tomorrow."},
                    {
                        "role": "cairn",
                        "content": "Tuesday:\n\n- 11:00am — Weekly sync with Denise\n- 2:00pm — Senior Backend panel debrief (Hiring Manager + 2 interviewers)\n- 4:30pm — Candidate call, Frontend Engineer (Role 1), Stage 2 prep\n\nNothing else scheduled.",
                    },
                    {"role": "user", "content": "Debrief needs to end with offer or no-offer decision. Make sure that's clear in the invite."},
                    {
                        "role": "cairn",
                        "content": "Will add to the debrief invite: 'Meeting must conclude with offer/no-offer decision. Come prepared.' Want me to note who's the decision owner if there's disagreement?",
                    },
                    {"role": "user", "content": "Hiring manager owns the decision. Put that in too."},
                    {
                        "role": "cairn",
                        "content": "Updated. Invite now reads: 'Must end with offer/no-offer decision. Hiring manager owns the final call. Come prepared with your recommendation.'",
                    },
                ],
            },
            {
                "messages": [
                    {"role": "user", "content": "Any updates on the ML hire pipeline?"},
                    {
                        "role": "cairn",
                        "content": "One update: hiring manager responded to your ping. Debrief scheduled for tomorrow at 10am. That's tight but possible if the candidate's decision timeline holds.\n\nComp review: still pending from Catherine and Denise. No response yet.\n\nThe other three ML candidates: one declined to interview (no reason given), two still in process at earlier stages. Backup pipeline is thin if the finalist walks.",
                    },
                    {"role": "user", "content": "If the finalist declines, what's the realistic path?"},
                    {
                        "role": "cairn",
                        "content": "Two candidates at earlier stages. Neither is as strong as the finalist based on your notes — you haven't flagged either as likely to close this quarter.\n\nRealistic path if finalist declines: 4–6 week reset on sourcing. ML role probably slips to Q3. You may need to reopen sourcing with a broader comp band if Catherine approves the range adjustment.\n\nReferrals are your best shot at a faster path — anyone on the engineering team who could make an intro worth activating?",
                    },
                    {"role": "user", "content": "One lead. Following up today."},
                    {"role": "cairn", "content": "Good. That's the play. Let me know how it goes."},
                ],
            },
            {
                "messages": [
                    {"role": "user", "content": "Textio check on the ML job description came back. 'Rockstar' is in there. Who wrote this?"},
                    {
                        "role": "cairn",
                        "content": "The ML JD is one of the 5 still in your rewrite queue — looks like the old version is still live. That one's on your list, not yet done.\n\nWant to prioritize it before the photographer shoot? Engineers who look at the careers page during that window will see the old copy.",
                    },
                    {"role": "user", "content": "Yeah. Moving it to today. 'Rockstar' and 'ninja' both have to go."},
                    {
                        "role": "cairn",
                        "content": "Makes sense. Textio flags both as exclusionary — candidates from underrepresented groups respond negatively to that language at measurable rates. Run the full Textio pass when you're done and I'd check for '8+ years experience' requirements on anything that could reasonably be done with 4–5.",
                    },
                    {"role": "user", "content": "Already on it. Thanks."},
                    {"role": "cairn", "content": "Copy."},
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Kai tracks hiring metrics in a personal spreadsheet updated daily — pipeline by role, source, stage, and rejection reason. He does not trust ATS reporting.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Kai's tracking methodology",
                    "tool": "Personal spreadsheet, updated daily",
                    "fields": ["role", "source", "stage", "rejection reason"],
                    "note": "Does not trust ATS reporting; personal spreadsheet is source of truth",
                },
            },
            {
                "narrative": "Kai's sourcing strategy prioritizes employee referrals over LinkedIn outreach — referrals convert at 4x the rate of cold LinkedIn messages.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Sourcing strategy",
                    "priority_order": ["Employee referrals", "LinkedIn Recruiter (targeted)", "Job boards"],
                    "referral_conversion_multiplier": "4x vs cold LinkedIn",
                },
            },
            {
                "narrative": "Kai has a weekly sync with Denise Washington on Tuesdays at 11am.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Denise Washington",
                    "relationship": "Manager / weekly sync",
                    "meeting": "Tuesdays at 11am",
                },
            },
            {
                "narrative": "The ML Engineer comp band has been flagged as likely below market by Kai; review is pending with Denise and Catherine Liu.",
                "entity_type": "waiting_on",
                "entity_data": {
                    "waiting_for": "Denise Washington and Catherine Liu",
                    "subject": "ML Engineer comp band review",
                    "urgency": "High — ML finalist has three competing offers and is deciding this week",
                },
            },
            {
                "narrative": "Kai's current Q2 projection is 5 of 8 engineering roles closed; ML Engineer, 1 Frontend, and possibly 1 Senior Backend are at risk of slipping to Q3.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Q2 engineering hiring projection",
                    "projected_closes": 5,
                    "at_risk": ["ML Engineer", "Frontend Role 2", "Senior Backend Role 3 (thin margin)"],
                },
            },
            {
                "narrative": "The 24-hour debrief-to-offer SLA has had three violations in the past 4 weeks, all from the same hiring manager; Kai escalated to Denise.",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Debrief-to-offer SLA violations",
                    "violation_count": 3,
                    "pattern": "Same hiring manager in all three cases",
                    "escalation": "Flagged to Denise Washington",
                },
            },
            {
                "narrative": "Kai was a software engineer for 3 years before switching to recruiting — he uses that background to read resumes technically and have credible conversations with engineering candidates.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Kai Nakamura",
                    "background": "3 years backend engineering before recruiting",
                    "advantage": "Technical credibility with engineering candidates",
                },
            },
            {
                "narrative": "Kai's async coding assessment A/B test showed a 2.9-day reduction in time-to-first-technical-screen with no drop in candidate satisfaction or screen pass rate; shipping to all candidates next month.",
                "entity_type": "decision",
                "entity_data": {
                    "subject": "Async coding assessment rollout decision",
                    "evidence": "2.9-day reduction, satisfaction unchanged (4.2/5.0), pass rate unchanged",
                    "rollout": "All candidates next month",
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },
]
