"""Test generation profiles 9-12 for Cairn testgen suite."""

PROFILES_3 = [
    {
        "id": "sam_abeywickrama",
        "identity": {
            "full_name": "Sam Abeywickrama",
            "department": "Product",
            "title": "Senior Product Manager",
        },
        "personality": "methodical",
        "your_story": """\
# Sam Abeywickrama — Senior Product Manager, Meridian Labs

I'm 37 years old and have spent the last 12 years in product, though my first three years were in engineering. That transition shaped how I work: I read the code, I sit in technical design reviews, and I don't hand engineers fuzzy requirements and expect them to fill in the gaps. I write PRDs that are specific enough that any ambiguity is intentional, not accidental.

I came to Meridian Labs five years ago to lead the collaboration features team. Meridian makes enterprise collaboration tools — think document editing, async communication, and permissions — for teams that live and die by structured workflows. My users are ops leads, compliance teams, and knowledge workers who would rather have a precise tool than a flashy one.

Before Meridian I worked at a Series B SaaS company where I owned the core editor, and before that a consultancy where I discovered that "doing PM for clients" is mostly doing triage for founders who hadn't decided what they wanted. That experience made me allergic to ambiguity.

I'm Sri Lankan-American, raised in Denver, and I still live there. I run a tight weekly planning practice: every Monday morning I block 90 minutes to build my priority matrix for the week — urgent+important, important+not-urgent, delegate, drop. I review it Friday afternoon. This isn't productivity theater; it's how I avoid letting the urgent crowd out the important.

My current focus is two large initiatives running in parallel — an AI Copilot feature for our document editor and a long-overdue redesign of our permissions model — plus a third-track mobile strategy that's in earlier stages. I work closely with engineering leads, design, and my research counterpart Aisha on translating her findings into actionable specs.

Outside work: I coach a youth soccer team on weekends, which is an exercise in managing conflicting priorities with zero budget and maximum stakeholder opinions.
""",
        "acts": [
            {
                "title": "AI Copilot for Documents",
                "color": "#2563eb",
                "notes": """\
Meridian's document editor is the core of the product, and it's currently dumb — you type, it saves. The AI Copilot initiative is about embedding intelligent writing assistance directly into the editor surface: summarization of long documents, rewriting at different reading levels, context-aware suggestions based on the document's purpose and the user's past edits, and a "meeting notes → action items" flow that turns raw transcripts into structured tasks.

**User Research Foundation**

Aisha ran a 6-week diary study and 22 contextual interviews across four enterprise customers. Key findings: (1) Knowledge workers spend an average of 40 minutes per working day editing documents that someone else drafted — trimming, restructuring, filling gaps. (2) Enterprise users are deeply skeptical of AI that modifies their documents without explicit confirmation. Any "just fix it" magic will get flagged by legal and compliance teams. (3) The most-requested capability was summarization of meeting notes, not generation from scratch.

These findings narrowed the initial feature scope significantly. We are not building a "write for me" AI. We are building a "help me communicate what I already know" AI.

**Model Selection: Claude API vs Fine-Tuned**

After a 3-week evaluation sprint with the ML team, we decided to use the Claude API rather than fine-tuning a smaller model. The reasoning: (1) Enterprise document prose is highly variable in domain — we'd need per-vertical fine-tuning data we don't have. (2) Maintenance burden of a fine-tuned model at our scale (3 ML engineers) exceeds Claude API cost for current projected usage. (3) Claude's instruction-following on structured output (JSON action items, rewrite-with-constraints) is strong out of the box. We document this decision and revisit in Q4 if monthly API spend exceeds $30K.

**Privacy Considerations**

This is a hard blocker for several of our enterprise customers. Document content is sensitive — legal contracts, HR materials, financial projections. The architecture will: (1) Strip all PII before sending to external APIs using our existing scrubbing pipeline (already in use for analytics). (2) Give workspace admins a kill switch to disable AI features entirely. (3) Log every AI interaction with a 90-day retention policy, exportable per SOC 2 requirements. Privacy review is scheduled with our security team in Week 8.

**UX Mockup Status**

Design completed V1 mockups for three entry points: (1) floating action button on paragraph selection, (2) slash command `/ai` in the editor, (3) a dedicated sidebar panel for longer operations like full-document summarization. User testing on the mockups is in progress — preliminary feedback prefers the slash command over the floating button.

**Phased Rollout**

Phase 1 (Q2): Summarization and meeting notes extraction, limited beta with 5 customers. Phase 2 (Q3): Rewriting and tone adjustment, expanded beta. Phase 3 (Q4): Context-aware suggestions using document history, GA.

**Success Metrics**

Primary: Feature activation rate (target 30% of active users within 90 days of GA). Secondary: NPS delta for users who activate vs. those who don't (target +8 points). Tertiary: Document edit time reduction (proxy: session length for "edit" sessions, target -15%).

**Competitive Analysis**

Notion AI and Google Duet are the primary comparables. Notion AI is tightly integrated but requires Notion's own document format. Duet is strong in Google Workspace but weak outside it. Our differentiation: enterprise privacy controls and admin governance that neither competitor offers at our tier.
""",
                "scenes": [
                    {
                        "title": "Finalize privacy architecture with security team",
                        "stage": "in_progress",
                        "notes": "PII scrubbing pipeline review + admin kill switch spec. Security review meeting scheduled Week 8.",
                    },
                    {
                        "title": "User testing on UX mockups (V1)",
                        "stage": "in_progress",
                        "notes": "5 sessions scheduled with beta customers. Preference data: slash command leading. Need to test sidebar panel.",
                    },
                    {
                        "title": "Claude API contract and rate limit negotiation",
                        "stage": "awaiting_data",
                        "notes": "Legal reviewing Anthropic enterprise agreement. Waiting on procurement approval before proceeding.",
                    },
                    {
                        "title": "Phase 1 beta customer selection",
                        "stage": "planning",
                        "notes": "Need 5 customers willing to be guinea pigs for summarization beta. Candidate list with CSM.",
                    },
                    {
                        "title": "PRD v2 with updated scope from research findings",
                        "stage": "complete",
                        "notes": "Updated after Aisha's diary study. Removed 'generate from scratch' flows. Scope locked for Phase 1.",
                    },
                    {
                        "title": "Competitive teardown: Notion AI and Duet",
                        "stage": "complete",
                        "notes": "Analysis complete. Differentiation strategy: enterprise privacy controls. Attached to PRD.",
                    },
                ],
            },
            {
                "title": "Enterprise Permissions Redesign",
                "color": "#1d4ed8",
                "notes": """\
Meridian's current permissions model is flat: you're either a workspace admin, a channel member, or a guest. This made sense when we were a 20-person startup. It does not make sense when customers are 4,000-person enterprises with legal, HR, finance, and engineering all in the same workspace and none of them should be able to see each other's documents by default.

**The Pain Points**

We have three enterprise customers who have experienced data leaks in the past 18 months — not external breaches, but internal visibility errors. A finance analyst saw an HR document because both teams were in the same "Operations" channel. An engineering contractor had read access to a product strategy doc that was shared at the channel level rather than the document level. These incidents haven't caused churn yet, but they've appeared in renewal conversations and one customer requested a "permissions audit" that we couldn't adequately support.

**Proposed Model**

The new model introduces a four-level hierarchy: Workspace → Team → Channel → Document. Permissions flow downward with explicit overrides. Key capabilities: (1) Role-Based Access Control with custom roles at the team level (not just admin/member/guest). (2) Guest access with scoped invitations — guests can be invited to specific documents without channel membership. (3) Audit logging: every permission change, every document access by a non-member, every role assignment. Immutable, exportable. (4) Inheritance visualization — admins can see why a user has the access they have.

**Migration Strategy**

The existing 1,200 enterprise customers all have data in the current flat model. Migration cannot be a flag day. The plan: (1) Run the new model in "shadow mode" for 30 days — compute new permissions in parallel, log discrepancies, alert admins to upcoming changes. (2) Customer-facing migration wizard that walks admins through mapping their current structure to the new hierarchy. (3) A 90-day grace period where the old permission APIs still work, then hard deprecation.

**Compliance Requirements**

SOC 2 Type II audit is in 6 months. The new audit logging capability is directly tied to our control for "least privilege access." GDPR: the new permission model must support right-to-erasure chains — if a user is deleted, their permission grants must cascade-delete from all documents. Our legal team has signed off on the architecture; engineering needs to implement the deletion cascade.

**Engineering Estimate**

Three engineers, two quarters. Q2 is backend (new permission model, migration infrastructure, audit log storage). Q3 is frontend (admin UI, migration wizard, inheritance visualization) and API versioning. One staff engineer is the technical lead. Risk: the migration tooling is the hardest part — if customers don't trust the wizard, they'll either refuse to migrate or they'll misconfigure and blame us.

**Success Metrics**

Zero data leak incidents (internal visibility) post-launch. Audit log export requested by at least 60% of enterprise customers within 90 days of GA (proxy for trust and usage). Permissions-related support ticket volume down 40%.
""",
                "scenes": [
                    {
                        "title": "Engineering kickoff: backend permission model",
                        "stage": "complete",
                        "notes": "Staff engineer confirmed approach. Q2 scope locked. JIRA epics created.",
                    },
                    {
                        "title": "Legal review: GDPR deletion cascade spec",
                        "stage": "in_progress",
                        "notes": "Legal reviewing the cascade delete design. Waiting on their sign-off before engineering builds it.",
                    },
                    {
                        "title": "Migration wizard UX design",
                        "stage": "planning",
                        "notes": "Design hasn't started. Blocked on finalizing the data model for the hierarchy mapping.",
                    },
                    {
                        "title": "Customer advisory board session on permissions redesign",
                        "stage": "planning",
                        "notes": "Need to present the proposed model to 6 enterprise admins before committing to Q3 migration. Schedule TBD.",
                    },
                    {
                        "title": "Audit log storage design review",
                        "stage": "awaiting_data",
                        "notes": "Waiting on engineering estimate for immutable log storage at current data volume. Need before finalizing infra costs.",
                    },
                ],
            },
            {
                "title": "Mobile App v2 Strategy",
                "color": "#1e40af",
                "notes": """\
The current Meridian mobile app is a read-only viewport. Users can browse documents and leave comments, but they can't edit. For our original customer profile — knowledge workers at desks — this was fine. As we've moved upmarket into field teams, manufacturing, and logistics, it's become a competitive liability.

**User Research Driver**

Aisha ran 14 contextual interviews across 3 customers with large field workforces. The top finding: field team leads use our product on desktop but can't complete their workflows on mobile because editing is disabled. The specific scenario that recurred: a shift supervisor needs to update a handoff document at end-of-shift, which they do from a phone in a noisy environment with intermittent connectivity. They currently do this in a Notes app and manually copy it to Meridian later. That workaround is our bug.

**Offline-First Editing**

The core technical challenge for v2 is offline-first editing with conflict resolution. The proposed approach is CRDT (Conflict-free Replicated Data Types) sync, which Riley — no, Priya on the platform team is leading this. My role is to coordinate the product requirements against the technical implementation. We've had two alignment sessions. Key constraints: (1) CRDT approach supports paragraph-level merges but not character-level in the first implementation. (2) Offline edits queue locally and sync on reconnection. (3) Conflict resolution is user-surfaced — the app shows conflicts rather than auto-resolving, which enterprise legal teams require.

**Push Notification Redesign**

The current notification system sends everything: every comment, every @mention, every document share. Engagement data shows 34% of users have disabled all push notifications. The v2 approach: intelligent filtering based on user-defined priority rules. "Only notify me if I'm @mentioned in a document I own." This reduces noise and restores trust in notifications as a signal rather than spam.

**Deep Linking**

Enterprise customers use Meridian links in email, Slack, and other tools. Currently, those links open the mobile browser, not the app. We need universal links (iOS) and App Links (Android) for any document or section URL. This is a smaller feature but high user-visible impact.

**Platform-Specific Considerations**

iOS: SwiftUI rewrite of the editor is in scope for v2. Current iOS app is Objective-C wrapped in React Native — too slow for offline edit operations. Android: The Android app is already React Native and performs better. CRDT sync library will be shared, but the editor surface will diverge between platforms in v2.

**Timeline**

CRDT sync: Q3 (platform team dependency). Offline edit UI: Q4 (depends on CRDT). Notification redesign: Q3, runs parallel to CRDT. Deep linking: Q2, standalone, no dependencies.

**Feature Prioritization Matrix**

Tier 1 (ship v2): Offline editing with CRDT sync, notification redesign, deep linking. Tier 2 (v2.1 if time allows): Voice-to-text for document input, biometric auth for sensitive documents. Tier 3 (backlog): Tablet-optimized layout, AR document annotations (this one came from an offsite brainstorm — not serious).
""",
                "scenes": [
                    {
                        "title": "Deep linking implementation (iOS universal links + Android App Links)",
                        "stage": "in_progress",
                        "notes": "Engineering started Q2. No platform team dependency. Target completion Week 10.",
                    },
                    {
                        "title": "CRDT sync alignment session with Priya's platform team",
                        "stage": "complete",
                        "notes": "Two sessions done. Paragraph-level merge confirmed for v1. Character-level deferred. PRD updated.",
                    },
                    {
                        "title": "Notification redesign spec",
                        "stage": "in_progress",
                        "notes": "Priority rule engine spec drafted. Need design mockups before engineering estimate.",
                    },
                    {
                        "title": "iOS SwiftUI editor prototype",
                        "stage": "planning",
                        "notes": "iOS team will start prototype in Q3. Need CRDT library available in staging first.",
                    },
                    {
                        "title": "Field team user testing: offline editing prototype",
                        "stage": "planning",
                        "notes": "Aisha is recruiting 8 field team participants. Testing planned for Q4 against the CRDT prototype.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Can you walk me through my priorities this week? I want to make sure I'm aligned on the AI Copilot launch timeline relative to the permissions redesign.",
                    },
                    {
                        "role": "cairn",
                        "content": "Sure. Looking at your current acts and scenes:\n\n**AI Copilot for Documents** — two active scenes this week: the privacy architecture review with the security team is in progress and is the higher-urgency item since it's blocking Phase 1 beta. The UX mockup user testing sessions are also ongoing.\n\n**Enterprise Permissions Redesign** — the GDPR deletion cascade legal review is in progress, but you're in a waiting position there. The customer advisory board session and migration wizard UX haven't started yet.\n\nOn timeline alignment: Phase 1 of the Copilot (summarization beta) is targeting Q2. The permissions redesign backend is also a Q2 engineering track. These are running in parallel, which is your current plan, but you have two Q2 dependencies that could bottleneck the same engineering resources if the permissions legal review comes back with changes. Worth flagging to your engineering lead now rather than in Week 9.",
                    },
                    {
                        "role": "user",
                        "content": "That's the right flag. The permissions redesign is three engineers and the Copilot is primarily ML team, so there's no direct resource conflict. What I'm more worried about is my own bandwidth — I'm the bottleneck on both PRDs.",
                    },
                    {
                        "role": "cairn",
                        "content": "That tracks. Right now you have open PRD work on both. For the Copilot, the v2 PRD with updated scope is marked complete, but the Phase 1 beta customer selection is still in planning — that requires your direct involvement to coordinate with CSM. For permissions, the migration wizard UX design hasn't started, which unblocks design, which unblocks engineering for Q3.\n\nIf you have to sequence your own work this week, the migration wizard UX spec is probably the higher-leverage item: it's earlier in a longer dependency chain. The beta customer selection can run in parallel if you can delegate the initial candidate list to your CSM contact.",
                    },
                    {
                        "role": "user",
                        "content": "Agreed. Can you add a note to the permissions redesign act reminding me to unblock the migration wizard spec before I look at anything else Monday morning?",
                    },
                    {
                        "role": "cairn",
                        "content": "Done. I've added a note to the Enterprise Permissions Redesign act: \"Monday priority: unblock migration wizard UX spec before anything else — design is waiting on the hierarchy mapping data model to be finalized.\" It'll surface at the top of your act notes when you open it Monday.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What did we decide about the mobile offline sync approach? I want to reference it in the PRD.",
                    },
                    {
                        "role": "cairn",
                        "content": "The decision is documented in your Mobile App v2 Strategy act. The approach is CRDT sync, led by Priya's platform team. The key constraints from your two alignment sessions: paragraph-level merges are supported in the first implementation, character-level merges are deferred. Offline edits queue locally and sync on reconnection. Conflict resolution is user-surfaced — the app shows conflicts rather than auto-resolving, which was a hard requirement from enterprise legal. You also noted that the CRDT sync library will be shared across platforms, but the editor surface will diverge between iOS and Android in v2.",
                    },
                    {
                        "role": "user",
                        "content": "Right. And the reason we chose CRDT over operational transforms?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your notes don't include a formal OT vs CRDT decision log — the act notes reference the CRDT approach as the chosen method following your alignment sessions with Priya, but don't document the comparative reasoning. If that rationale matters for the PRD, you'll want to get it from Priya directly or from the alignment session notes, if those were captured.",
                    },
                    {
                        "role": "user",
                        "content": "Fair. I'll ping Priya. Can you remind me to do that at 9am tomorrow?",
                    },
                    {
                        "role": "cairn",
                        "content": "Reminder set for tomorrow at 9am: ping Priya about the OT vs CRDT decision rationale for the Mobile v2 PRD.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "My skip-level with the VP is coming up. What should I bring?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your skip-level with the VP of Product is every other Friday at 1pm. For the agenda, here's what's worth surfacing based on your current state:\n\n**AI Copilot** — You're in a good position. Phase 1 scope is locked, security review is in progress, and you have a clear Q2 beta target. The Claude API contract is the one open risk (awaiting procurement). Worth flagging proactively.\n\n**Permissions Redesign** — The customer advisory board session hasn't been scheduled yet. If the VP cares about enterprise customer involvement in product decisions (likely), this is worth mentioning as a near-term step you're taking before committing to the migration design.\n\n**Mobile v2** — Early stage, but the offline editing user research finding is strong and specific. The field team supervisor scenario from Aisha's interviews is a compelling narrative.\n\nIs there anything you want to add to the agenda or any of these I should expand?",
                    },
                    {
                        "role": "user",
                        "content": "That's a good framing. I also want to raise the resource question — I'm worried we don't have enough engineering headcount to hit both Q2 tracks without slipping something. Can you help me think through what I'd say?",
                    },
                    {
                        "role": "cairn",
                        "content": "The clearest way to frame it: the Copilot and permissions redesign are both Q2 engineering starts, but they're drawing from different teams — ML team for Copilot, three product engineers for permissions. The risk isn't a direct headcount conflict between the two tracks; the risk is that if either track surfaces unexpected complexity, you have no slack to absorb it without slipping the other.\n\nThe concrete ask to the VP would be: do we have a priority ordering between the two if a slip becomes unavoidable? Right now both are treated as equal priority. Getting an explicit tiebreaker — or a commitment to add one engineer if needed — gives you a defined response to slippage rather than an improvised one under pressure.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Quick question — did I ever formally decide on the success metric for permissions? I remember discussing it but I'm not sure what made it into the PRD.",
                    },
                    {
                        "role": "cairn",
                        "content": "Yes, three metrics are documented in the Enterprise Permissions Redesign act:\n\n1. Zero data leak incidents (internal visibility errors) post-launch — this is the primary north star.\n2. Audit log export requested by at least 60% of enterprise customers within 90 days of GA — used as a proxy for trust and adoption of the new model.\n3. Permissions-related support ticket volume down 40%.\n\nThose are the three that made it into your act notes. If the PRD has different numbers, the act notes may be ahead of or behind the PRD version.",
                    },
                    {
                        "role": "user",
                        "content": "Good, those match. Thanks.",
                    },
                    {
                        "role": "cairn",
                        "content": "Confirmed. You're consistent.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Sam uses a weekly priority matrix as a core planning practice: urgent+important, important+not-urgent, delegate, drop. Reviews it Monday morning (90-minute block) and again Friday afternoon.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Sam Abeywickrama",
                    "insight": "Weekly priority matrix practice — 90min Monday block, Friday review",
                    "category": "work_habit",
                },
            },
            {
                "narrative": "Sam's skip-level with the VP of Product is every other Friday at 1pm.",
                "entity_type": "person",
                "entity_data": {
                    "name": "VP of Product",
                    "relationship": "skip-level manager",
                    "meeting_cadence": "every other Friday at 1pm",
                },
            },
            {
                "narrative": "Sam decided to use the Claude API for the AI Copilot feature instead of fine-tuning a smaller model. Reasons: insufficient per-vertical fine-tuning data, maintenance burden of a fine-tuned model exceeds API cost at current scale (3 ML engineers), Claude's instruction-following on structured output is strong out of the box. Decision to revisit in Q4 if API spend exceeds $30K/month.",
                "entity_type": "decision",
                "entity_data": {
                    "decision": "Use Claude API for AI Copilot, not fine-tuned model",
                    "rationale": "data gaps, maintenance cost, strong baseline instruction-following",
                    "revisit_trigger": "API spend > $30K/month in Q4",
                },
            },
            {
                "narrative": "Sam and Priya (platform team lead) collaborate closely on the CRDT mobile offline sync integration. Priya's team owns the CRDT sync library; Sam owns the product requirements. Two alignment sessions completed; paragraph-level merge is v1 scope, character-level deferred.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Priya",
                    "role": "Platform team lead",
                    "collaboration": "CRDT mobile offline sync — library owner",
                    "decision": "Paragraph-level merge in v1, character-level deferred",
                },
            },
            {
                "narrative": "Sam collaborates with Aisha Osman (UX Researcher) on translating research findings into PRD requirements. Aisha's diary study and contextual interviews were the primary driver for narrowing the AI Copilot scope away from 'generate from scratch' and toward 'help communicate what you already know.'",
                "entity_type": "person",
                "entity_data": {
                    "name": "Aisha Osman",
                    "role": "UX Researcher",
                    "collaboration": "research → PRD translation; AI Copilot and Mobile v2",
                },
            },
            {
                "narrative": "The Enterprise Permissions Redesign was prompted by three internal data leak incidents in 18 months — not external breaches, but internal visibility errors. These have appeared in renewal conversations. The new model introduces a four-level hierarchy: Workspace → Team → Channel → Document.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Enterprise Permissions Redesign",
                    "trigger": "3 internal visibility incidents in 18 months, appearing in renewals",
                    "new_model": "Workspace → Team → Channel → Document hierarchy",
                },
            },
            {
                "narrative": "Sam's background: former engineer turned PM. The engineering background means Sam reads code, attends technical design reviews, and writes PRDs specific enough that any ambiguity is intentional.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Sam Abeywickrama",
                    "insight": "Engineering background informs PM style — technical, precise, low-ambiguity PRDs",
                    "category": "professional_background",
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },
    {
        "id": "aisha_osman",
        "identity": {
            "full_name": "Aisha Osman",
            "department": "Product",
            "title": "UX Researcher",
        },
        "personality": "creative",
        "your_story": """\
# Aisha Osman — UX Researcher, Meridian Labs

I came to UX research through cognitive psychology. I spent four years in a PhD program studying how people form and maintain mental models of complex systems — specifically how users understand permission structures in software, which turned out to be completely applicable to my current job in ways I couldn't have predicted when I left ABD. "All But Dissertation" sounds like failure; I think of it as a calculated pivot. I had a complete methodology toolkit, a theoretical grounding that most UX researchers don't have, and I realized I wanted to do research that changed products people actually used rather than adding to a literature review no one would read.

I'm 33, Somali-American, grew up in Minneapolis and still live there. I joined Meridian Labs three years ago, and I run a mixed-methods research practice — diary studies, contextual inquiry, semi-structured interviews, quantitative funnel analysis. I don't believe in picking a method and hammering everything with it. I believe in matching the method to the question.

My collaborative style tends toward the associative: I make connections across findings that aren't always obvious, and I do my best thinking when I can talk through a half-formed idea out loud. My research notes are messy but my synthesis documents are tight. I record all sessions and transcribe with Otter.ai; everything gets tagged in Dovetail.

I work most closely with Sam on the product side. My research feeds directly into his PRDs, and I've learned to frame findings in ways that make prioritization decisions easier rather than just delivering themes. "Users find this confusing" doesn't move a roadmap. "The top-5 most common support tickets are caused by this single unclear affordance, and fixing it would deflect 30% of that volume" — that moves a roadmap.

I'm considering going back to finish my PhD part-time. The research I'm doing at Meridian is legitimately interesting enough that I could build a dissertation around it. Still deciding.
""",
        "acts": [
            {
                "title": "Enterprise Onboarding Research",
                "color": "#0891b2",
                "notes": """\
This is a 12-week mixed-methods study on the enterprise onboarding experience. The central question: where and why do enterprise customers fail to reach activation, and who is actually responsible for the drop-off?

**Study Design**

The study combines three methods: (1) Diary studies with 24 participants across 6 companies, running for 4 weeks each, capturing the onboarding journey in near-real-time. (2) Contextual inquiry — 36 interviews conducted in participants' work environments, watching them attempt onboarding tasks rather than asking them to recall. (3) Quantitative funnel analysis against Meridian's activation metrics (seat activation rate, first meaningful action, time-to-value). The combination matters because each method covers a different blindspot: diary studies capture what people think and feel over time, contextual inquiry captures what they actually do in context, and funnel analysis contextualizes both against behavior at scale.

**Recruitment Challenges**

Enterprise research recruitment is genuinely hard. I need people who are mid-onboarding, not people who have finished and are reconstructing the experience. We worked through CSM to identify customers in their first 60 days, then recruited through the primary admin contact at each company. Response rate on initial outreach: 31%. The challenge is that the people most willing to participate are often not the ones with the worst onboarding experience — they're the engaged early adopters. I'm counteracting this by specifically requesting access to users flagged as "low engagement" by our product analytics team.

**Preliminary Findings**

The most surprising finding so far: IT admins are the primary bottleneck in enterprise onboarding, not end users. End users are typically ready and willing to adopt; IT admins delay provisioning because Meridian's permission model is opaque to people who are used to managing AD and LDAP. The second finding: the onboarding email sequence is designed for individual users but lands in an inbox managed by an IT admin who doesn't understand why they're receiving "Your document editor is ready!" emails. These two findings are directly relevant to Sam's permissions redesign work.

**Synthesis Approach**

I use affinity diagramming for qualitative synthesis, running sessions with a research assistant and a product stakeholder present so findings have product-side witnesses. All themes are tagged in Dovetail with the verbatims attached. I generate insight cards rather than long reports — each card is one finding, one supporting evidence chain, one implication for product. Sam can attach them directly to PRD sections.

**Presentation Plan**

Final findings presentation is in Week 10. Audience: Sam, design lead, VP of Product, one representative from Engineering. Format: 45-minute narrative walk-through followed by insight card review. A subset of the findings will also feed into Aisha's broader Collaboration Patterns Taxonomy work, because onboarding behavior turns out to be a lens on how teams establish collaboration norms.
""",
                "scenes": [
                    {
                        "title": "Diary study: Week 3 check-ins with participants",
                        "stage": "in_progress",
                        "notes": "24 participants across 6 companies. Week 3 prompt sent. Response rate this week: 79%. Two participants have gone silent — follow up.",
                    },
                    {
                        "title": "Contextual inquiry sessions (batch 2 of 3)",
                        "stage": "in_progress",
                        "notes": "12 sessions completed, 24 remaining. Scheduling ongoing. Most sessions are remote — screen share + think-aloud.",
                    },
                    {
                        "title": "Quantitative funnel analysis with data team",
                        "stage": "awaiting_data",
                        "notes": "Waiting on data team to pull the low-engagement user cohort from analytics. Needed for triangulation.",
                    },
                    {
                        "title": "Affinity synthesis session (batch 1 findings)",
                        "stage": "planning",
                        "notes": "Schedule with Sam and design lead. Need the first 12 contextual inquiry transcripts done first.",
                    },
                    {
                        "title": "Final findings presentation (Week 10)",
                        "stage": "planning",
                        "notes": "Audience: Sam, design lead, VP of Product, engineering rep. 45-min narrative + insight card review.",
                    },
                    {
                        "title": "Recruit low-engagement participant cohort",
                        "stage": "complete",
                        "notes": "CSM identified 40 candidate users flagged as low-engagement. 9 agreed to participate. Added to diary study.",
                    },
                ],
            },
            {
                "title": "Collaboration Patterns Taxonomy",
                "color": "#0e7490",
                "notes": """\
This is a research initiative I proposed myself, which is unusual — most of my work is commissioned by PMs. The question: what are the fundamental patterns of collaboration that happen inside Meridian, and can we name and classify them well enough that product decisions can reference a shared vocabulary?

**Methodology**

The taxonomy is built on two data sources: (1) Behavioral data analysis — I'm working with the data team to analyze interaction patterns in Meridian (edit events, comment threads, share events, version history) to identify naturally occurring collaboration shapes. This is quantitative pattern recognition, not user-reported behavior. (2) Contextual inquiry across 8 customer organizations — I'm conducting extended site visits (half-day sessions) with diverse team types: legal, engineering, marketing, customer success, operations. The goal is to observe collaboration in situ and map observed behavior to the patterns emerging from the behavioral analysis.

**Emerging Pattern Categories**

Four patterns are appearing consistently enough that I'm starting to treat them as anchors:

1. **Synchronous-creative** — Real-time co-editing sessions, often short, high comment density, many small edits. Typical in brainstorming and early-draft phases.
2. **Async-review** — One author, many reviewers, comments concentrated in a review window, then author-resolves. The dominant pattern for formal documents.
3. **Structured-handoff** — Document used as a transition artifact between two roles. Edit rights transfer, comment history is closure evidence. Legal drafting, engineering specs.
4. **Ad-hoc-escalation** — A document that was static becomes active because of an external event. Comment volume spikes, multiple new editors appear. Incident reports, crisis comms.

**Academic References**

This work connects to literature I know from my PhD: Ackerman's "Social Activity Indicator" work, Gutwin and Greenberg on workspace awareness, and more recent CSCW papers on asynchronous collaboration in knowledge work. The taxonomy will include explicit academic grounding, which I think gives it durability beyond a typical internal research deliverable.

**Deliverable Format**

The taxonomy will be a living document in Meridian itself (appropriate given the subject matter): one document per pattern, with behavioral signatures, use-case examples, design implications, and a versioned revision history. It's designed to be referenced by Sam and design in future product work rather than consumed once and archived.
""",
                "scenes": [
                    {
                        "title": "Behavioral data analysis: phase 1 (interaction pattern extraction)",
                        "stage": "in_progress",
                        "notes": "Working with data team on edit event clustering. Preliminary clusters match the four emerging patterns.",
                    },
                    {
                        "title": "Extended site visit: legal team at Hartfield Industries",
                        "stage": "complete",
                        "notes": "Half-day session. Key finding: legal treats documents as artifacts of record, not living documents. Major implication for version history design.",
                    },
                    {
                        "title": "Extended site visit: engineering team at Vantec",
                        "stage": "complete",
                        "notes": "Structured-handoff pattern very clear in spec review process. Engineers treat comment-resolution as the sign-off ritual.",
                    },
                    {
                        "title": "Draft taxonomy document (four initial patterns)",
                        "stage": "planning",
                        "notes": "Will draft in Meridian. Need behavioral data phase 1 complete first for empirical grounding.",
                    },
                    {
                        "title": "Remaining site visits (6 orgs)",
                        "stage": "planning",
                        "notes": "Marketing, customer success, operations, and three more. Scheduling in progress.",
                    },
                ],
            },
            {
                "title": "Accessibility User Testing Program",
                "color": "#155e75",
                "notes": """\
Meridian has an accessibility gap. We claim WCAG 2.1 AA compliance in our marketing materials, but we've never conducted user testing with disabled users. I proposed this program six months ago; it was approved with a small budget in Q1.

**Participant Panel Recruitment**

I've partnered with three disability-advocacy organizations and one university accessibility center to recruit a standing panel of disabled participants for ongoing testing. Target panel: 20 participants across categories — screen reader users (JAWS, NVDA, VoiceOver), keyboard-only navigators, users with motor impairments using switch access, users with cognitive disabilities (ADHD, dyslexia). Current panel: 11 participants recruited, 3 pending onboarding.

**Monthly Testing Cadence**

The program runs monthly, 4-6 hours of testing per cycle. Each cycle focuses on a specific feature area. Cycle 1 (complete) was the document editor core. Cycle 2 (in progress) is the comment and review workflow. Cycle 3 will be the new AI Copilot features before they ship.

**Assistive Technology Compatibility**

JAWS and NVDA are the primary screen readers in our enterprise customer base (Windows-dominant). VoiceOver is present for Mac and iOS. Our current editor has multiple ARIA labeling failures that JAWS trips on, and two keyboard trap issues identified in Cycle 1. Engineering has 4 of the 7 Cycle 1 issues fixed; 3 are in backlog.

**Findings from First Three Sessions**

The most significant finding from Cycle 1: our slash command menu (the `/` trigger for inserting blocks) is completely inaccessible to JAWS users. The menu appears as a floating div with no ARIA role, and JAWS announces it as an unnamed container. Users couldn't find it without sighted assistance. This is a P1 fix that engineering has prioritized.

The second finding: keyboard focus order in the editor sidebar is non-deterministic — it jumps based on render order, not document order. This is a broader architectural issue that requires a focused engineering sprint, not a one-off fix.

**Budget Justification**

Annual program cost: $42K (participant compensation at $80/session, research assistant time, Dovetail subscription overhead). The alternative is a WCAG audit from an external firm, which typically costs $15-25K as a one-time event and produces a report that ages poorly. An ongoing testing program produces continuously updated findings and builds an internal capability. I'm making the "capability over compliance" argument, and so far it's holding.
""",
                "scenes": [
                    {
                        "title": "Cycle 2 testing: comment and review workflow",
                        "stage": "in_progress",
                        "notes": "3 of 6 sessions complete. Preliminary: comment threading navigation is broken for JAWS. @mention autocomplete also problematic.",
                    },
                    {
                        "title": "Cycle 1 issue tracking: engineering follow-up",
                        "stage": "in_progress",
                        "notes": "7 issues logged. 4 fixed, 3 in backlog. P1 (slash command ARIA) confirmed fixed in staging. Keyboard focus order still open.",
                    },
                    {
                        "title": "Panel onboarding: 3 pending participants",
                        "stage": "awaiting_data",
                        "notes": "Waiting on onboarding paperwork from 3 participants. One needs a specific NDA version — legal reviewing.",
                    },
                    {
                        "title": "Cycle 3 planning: AI Copilot accessibility review",
                        "stage": "planning",
                        "notes": "Will test the slash command AI entry point and sidebar panel before GA. Coordinate with Sam on feature freeze date.",
                    },
                    {
                        "title": "Inclusive design guidelines document (draft)",
                        "stage": "planning",
                        "notes": "Will synthesize findings into a living design reference. Intended audience: designers and engineers, not compliance team.",
                    },
                    {
                        "title": "Q1 budget approval",
                        "stage": "complete",
                        "notes": "$42K annual program budget approved. Made the capability-over-compliance argument successfully.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I had a fascinating insight during today's contextual inquiry — the way the legal team at Hartfield uses our product is completely different from engineering. They treat documents as artifacts of record, not living documents. This has huge implications for how we think about version history... Oh also, what's on my calendar tomorrow?",
                    },
                    {
                        "role": "cairn",
                        "content": "That's a significant finding — the \"artifact of record\" framing means legal users are probably looking for immutability guarantees and audit trails in version history, not just the ability to revert. That's a different product requirement than what engineers want from version history (comparison, branch, rollback).\n\nYour calendar tomorrow: 9am, data team sync on behavioral data phase 1 results. 1pm, Cycle 2 accessibility testing session 4 of 6. 4pm, open — you blocked it as synthesis time.\n\nDo you want to capture the Hartfield artifact-of-record insight in your Collaboration Patterns Taxonomy notes before it gets fuzzy? You just came out of the session.",
                    },
                    {
                        "role": "user",
                        "content": "Yes, let's capture it. Also — I think this connects to the structured-handoff pattern more than I initially thought. The way they use comment resolution as evidence of sign-off is exactly the structured-handoff signature.",
                    },
                    {
                        "role": "cairn",
                        "content": "Captured in the Collaboration Patterns Taxonomy act under the Hartfield site visit scene. Added: \"Legal at Hartfield treats documents as artifacts of record — immutability and audit trail are primary needs, not reverting or branching. Comment resolution functions as a formal sign-off ritual, which is the clearest structured-handoff signature yet observed. Implication: version history product requirements should be segmented by collaboration pattern, not treated as a single feature.\"\n\nWant me to also flag this for Sam? The structured-handoff pattern and the version history implication seem directly relevant to the permissions redesign — if document ownership transfers at handoff, that's a permission event, not just a version event.",
                    },
                    {
                        "role": "user",
                        "content": "Yes, flag it for Sam. I'll talk to him about it before the Week 10 presentation so he has context. Can you remind me to bring it up at my next sync with him?",
                    },
                    {
                        "role": "cairn",
                        "content": "Reminder added to your next Sam sync: raise the Hartfield artifact-of-record finding and its implication for version history as a permission event in the structured-handoff pattern. I'll surface it at the start of that meeting.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I'm trying to figure out if I should go back and finish my PhD. Part-time, while still working here. What does my current load look like?",
                    },
                    {
                        "role": "cairn",
                        "content": "Currently you have three active research programs: the Enterprise Onboarding Research (12-week study, in Weeks 5-6 based on your session schedule), the Collaboration Patterns Taxonomy (ongoing, self-directed), and the Accessibility User Testing Program (monthly cadence). The onboarding study is the heaviest right now — you have contextual inquiry batch 2 running, diary study check-ins, and a data team coordination thread open simultaneously.\n\nThe onboarding study wraps in Week 10. After that, your workload drops noticeably. If you were going to trial a PhD program overlap, after Week 10 is a more realistic start than now.\n\nWhat's the format you're considering? Part-time PhD programs vary a lot — some are two courses per semester, some are more structured around a dissertation only.",
                    },
                    {
                        "role": "user",
                        "content": "I'm ABD, so it would be dissertation only. I'd need to re-engage my committee and file a return-from-leave form. The dissertation was on mental models of permission structures in software — which is almost embarrassingly relevant to what I'm doing now.",
                    },
                    {
                        "role": "cairn",
                        "content": "That's a strong research-to-practice thread — your field observations at Hartfield and the onboarding study findings about IT admin mental models of permission hierarchies could feed directly into a dissertation on mental models of permission structures. You're generating primary data right now that a PhD candidate would struggle to access.\n\nThe practical question is probably committee availability and whether the program allows you to count professional research work as dissertation data. Worth a conversation with your advisor before you decide. Do you want to add a scene to track the PhD re-engagement process, or keep it out of your work system for now?",
                    },
                    {
                        "role": "user",
                        "content": "Keep it out for now. It's still a 'maybe.' But note it somewhere I'll find it.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted in your Your Story as a flagged consideration: \"Part-time PhD completion (dissertation only) under consideration — re-engaging committee and filing return-from-leave. Dissertation topic on mental models of permission structures is directly connected to current research work. Revisit after Week 10 onboarding study wraps.\"",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What are the outstanding items from the Cycle 1 accessibility testing that engineering hasn't fixed yet?",
                    },
                    {
                        "role": "cairn",
                        "content": "Three Cycle 1 issues are still open:\n\n1. **Keyboard focus order** — Non-deterministic in the editor sidebar, jumps based on render order rather than document order. This is the architectural one; engineering flagged it as requiring a focused sprint, not a one-off fix.\n2. Two additional issues are in backlog — your notes don't specify them individually beyond the P1 (slash command ARIA, now fixed in staging) and the focus order issue. Do you have more detail in your Dovetail tags?\n\nThe P1 slash command ARIA issue is confirmed fixed in staging per your most recent scene note. The four other fixes from Cycle 1 are complete.",
                    },
                    {
                        "role": "user",
                        "content": "I need to pull the full list from Dovetail. Can you remind me to do that before tomorrow's Cycle 2 session so I can give the participant panel an accurate status update?",
                    },
                    {
                        "role": "cairn",
                        "content": "Reminder set for 8am tomorrow: pull full Cycle 1 open issues from Dovetail before the 1pm Cycle 2 session. Participant panel will want an accurate status update on known issues.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I keep thinking about the onboarding finding — IT admins as the bottleneck, not end users. I feel like we're going to present this and someone is going to say 'so the fix is better admin documentation' and completely miss the point. How do I head that off?",
                    },
                    {
                        "role": "cairn",
                        "content": "The documentation-fix response is a pattern where people conflate the proximate cause (admin confusion) with the root cause (product complexity). The way to head it off is to present the finding with the cost framing upfront, before anyone can reach for the cheap solution.\n\nFrame it as: the IT admin bottleneck is costing X days of seat activation delay per enterprise customer. Show that delay as a revenue and churn risk metric, not a UX problem. Then show that the admin confusion is structural — the permission model is opaque to people who manage identity systems for a living. Documentation doesn't fix structural opacity; it makes the opacity more legible, which is different.\n\nYou'll also want to have a concrete alternative ready. \"Better documentation\" is easy to propose because it's cheap. If you go in with \"and here's what would actually fix it\" (from the permissions redesign work Sam is already doing), you close the escape hatch before it opens.",
                    },
                    {
                        "role": "user",
                        "content": "That's exactly right. I should coordinate with Sam to make sure the permissions redesign is in the room as the existing response when I present this.",
                    },
                    {
                        "role": "cairn",
                        "content": "Agreed. Add it to your pre-presentation Sam sync agenda: align on framing the IT admin finding as a structural problem with an existing product response (permissions redesign), so the Week 10 presentation doesn't generate a detour into documentation fixes. I'll add it to your Sam sync reminder alongside the Hartfield finding.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Aisha records all research sessions and transcribes them with Otter.ai. All findings are tagged in Dovetail. She generates insight cards rather than long reports — one finding, one evidence chain, one product implication per card.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Aisha Osman",
                    "insight": "Research workflow: Otter.ai transcription, Dovetail tagging, insight card format",
                    "category": "work_habit",
                },
            },
            {
                "narrative": "Aisha is ABD in cognitive psychology (PhD program). Her dissertation was on mental models of permission structures in software — directly relevant to current work at Meridian. She is considering re-engaging her committee to finish part-time. Decision deferred until after Week 10 onboarding study wraps.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Aisha Osman",
                    "insight": "ABD — considering part-time PhD completion after current study; dissertation on permission structure mental models",
                    "category": "personal_consideration",
                },
            },
            {
                "narrative": "Aisha collaborates closely with Sam Abeywickrama (Senior PM) on translating research findings into PRD requirements. She frames findings in terms of support ticket deflection and revenue impact to make prioritization easier.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Sam Abeywickrama",
                    "role": "Senior Product Manager",
                    "collaboration": "research → PRD translation; AI Copilot and Mobile v2 scope decisions",
                },
            },
            {
                "narrative": "Key onboarding research finding: IT admins are the primary bottleneck in enterprise onboarding, not end users. End users are willing to adopt; IT admins delay provisioning because Meridian's permission model is opaque to people who manage AD and LDAP.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Enterprise Onboarding Research",
                    "finding": "IT admins are the bottleneck, not end users — permission model opacity is the root cause",
                    "implication": "Documentation won't fix this; structural product change (permissions redesign) is the real solution",
                },
            },
            {
                "narrative": "Key collaboration patterns taxonomy finding from Hartfield Industries legal team site visit: legal treats documents as artifacts of record, not living documents. Comment resolution is a formal sign-off ritual. Mapped to the structured-handoff pattern. Implication: version history product requirements should be segmented by collaboration pattern.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Collaboration Patterns Taxonomy",
                    "finding": "Legal teams treat documents as artifacts of record; comment resolution = formal sign-off",
                    "pattern": "structured-handoff",
                    "implication": "Version history requirements differ by collaboration pattern",
                },
            },
            {
                "narrative": "Cycle 1 accessibility testing found two significant issues: (1) slash command menu completely inaccessible to JAWS users — no ARIA role, announces as unnamed container (P1, now fixed in staging); (2) keyboard focus order in editor sidebar is non-deterministic, requires a focused engineering sprint.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Accessibility User Testing Program",
                    "cycle": 1,
                    "p1_issue": "Slash command ARIA — fixed in staging",
                    "open_issue": "Keyboard focus order non-deterministic — architectural, needs sprint",
                },
            },
            {
                "narrative": "Aisha's research approach: mixed-methods, method matched to question. Diary studies for longitudinal experience, contextual inquiry for in-situ behavior, quantitative funnel analysis for scale. Affinity diagramming for synthesis with a product stakeholder present to create witnesses to findings.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Aisha Osman",
                    "insight": "Mixed-methods research philosophy — method follows question; stakeholder-present synthesis",
                    "category": "professional_approach",
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },
    {
        "id": "viktor_petrov",
        "identity": {
            "full_name": "Viktor Petrov",
            "department": "Operations",
            "title": "IT Operations Manager",
        },
        "personality": "terse",
        "your_story": """\
# Viktor Petrov — IT Operations Manager

24 years in IT. Started as a Unix sysadmin at a regional bank in 1999. Spent 12 years working my way from helpdesk to infrastructure lead. Moved into management in 2011 when the bank was acquired and the new parent company needed someone to consolidate two IT organizations without losing either's institutional knowledge.

Came to Meridian Labs 7 years ago. They had 80 employees and a flat network with no segmentation. Now we're at 430 employees, SOC 2 certified, with a real disaster recovery posture and a zero-trust migration in progress. I built that.

I'm 48, Russian-American. Phoenix. Start work at 6am, leave by 3pm. The early hours are for real work — no meetings, no Slack pings from sales about their laptop. I block the first two hours every day as no-meeting time. Change management windows are Sunday 2am to 6am. Anyone who schedules infrastructure changes outside that window without my sign-off doesn't do it twice.

I manage a team of four: two helpdesk, one network engineer, one systems engineer. Riley Chen is my DevOps engineer — separate reporting line, different skill profile. Riley's brilliant with Kubernetes and CI/CD but needs direction on prioritization. I try to keep Riley focused on one project at a time. Works about half the time.

I don't write long emails. I don't hold long meetings. If something can be said in two sentences, I say it in two sentences. If a decision requires a meeting, I send the decision memo first and use the meeting to handle objections, not to reach consensus from scratch.

The job is infrastructure. Keep it up, keep it secure, keep it documented.
""",
        "acts": [
            {
                "title": "Zero Trust Network Migration",
                "color": "#475569",
                "notes": """\
Meridian is moving from a legacy VPN model to zero trust. The current setup: split-tunnel VPN for remote access, flat internal network with overly broad trust zones, and a growing number of SaaS tools that bypass the VPN entirely. This is not a defensible posture for a company handling enterprise customer data.

**Current VPN Pain Points**

Performance is the user-visible symptom. Split-tunnel VPN routes internal traffic through a central gateway, which creates latency for cloud-based workloads that should never touch our network at all. IT support tickets about VPN connectivity represent 23% of our total helpdesk volume. Beyond performance: split-tunnel creates inspection gaps — we can't see traffic to SaaS tools that route around the tunnel, and we can't enforce consistent DLP policy.

**Vendor Evaluation**

I evaluated three vendors: Zscaler, Cloudflare Access (now Cloudflare One), and BeyondCorp Enterprise. My technical preference is Cloudflare Access — simpler architecture, faster deployment, and the ZTNA component integrates cleanly with our existing Cloudflare DNS setup. However, procurement has a pricing concern: Zscaler has offered a multi-year enterprise agreement that's 18% cheaper at our user count than Cloudflare's rack rate. The evaluation is ongoing; I'm requesting Cloudflare's enterprise pricing before making a final recommendation. BeyondCorp is off the table — it requires deeper Google Workspace integration than we're willing to commit to.

**Phased Rollout**

Phase 1: Internal tools (Jira, Confluence, our internal monitoring stack) — these are the lowest-risk applications and let us validate the identity-aware proxy configuration with a recoverable blast radius. Phase 2: Production engineering access (SSH, Kubernetes API, database access) — requires device attestation enforcement. Phase 3: Full replacement of the VPN for all employees. Target for Phase 1 completion: end of Q2. Full migration: Q4.

**Employee Communication Plan**

IT migrations fail on communication, not technology. I'm running three information sessions before Phase 1: one for engineering (technical), one for the rest of the company (non-technical), one for executives (what does this mean for travel and remote work). The sessions happen two weeks before any user-visible change.

**Timeline and Budget**

6-month migration. Total approved budget: $340K (vendor licensing, professional services for identity provider integration, 2 months of overlap maintaining legacy VPN in parallel). The parallel-run period is non-negotiable — I won't cut over until the replacement is validated.
""",
                "scenes": [
                    {
                        "title": "Cloudflare enterprise pricing request",
                        "stage": "awaiting_data",
                        "notes": "Waiting on Cloudflare account rep. Needed before final vendor recommendation to leadership.",
                    },
                    {
                        "title": "Identity provider integration: Okta SAML config",
                        "stage": "in_progress",
                        "notes": "Network engineer is building the Okta integration for Phase 1 apps. Target: completed by Week 6.",
                    },
                    {
                        "title": "Phase 1 application inventory",
                        "stage": "complete",
                        "notes": "7 internal tools scoped for Phase 1. Jira, Confluence, internal monitoring, internal docs. JIRA ticket created for each.",
                    },
                    {
                        "title": "Employee communication sessions (3x)",
                        "stage": "planning",
                        "notes": "Schedule 2 weeks before Phase 1 cutover. Engineering, all-hands, exec. Deck in draft.",
                    },
                    {
                        "title": "Phase 1 cutover",
                        "stage": "planning",
                        "notes": "Target end of Q2. Sunday change window. Legacy VPN stays live for 30-day parallel run.",
                    },
                ],
            },
            {
                "title": "Disaster Recovery Overhaul",
                "color": "#334155",
                "notes": """\
Meridian's current disaster recovery plan was written in 2019 for a 100-person company. It specifies an RPO of 24 hours and an RTO of 8 hours. For a SaaS company serving enterprise customers who have SLAs with their own customers, 24-hour RPO is indefensible. I've been pushing to update this for two years; it's now in the budget.

**Target Architecture**

New targets: RPO 1 hour, RTO 4 hours. The approach is AWS multi-region active-passive. Primary region: us-east-1. Secondary region: us-west-2. Data replication: continuous replication for the database layer (RDS with cross-region read replicas promoted to primary on failover), hourly snapshots for object storage (S3 cross-region replication). Application tier: pre-provisioned in us-west-2 but scaled to zero during normal operations — spun up during failover via automation.

**Current Gaps**

The 2019 plan has no automated failover. DR was a manual process: an on-call engineer SSH'd into backup servers and manually promoted databases. We have never tested this successfully under time pressure. The quarterly DR drill in 2022 took 11 hours — well beyond the documented 8-hour RTO. The 2023 drill was cancelled. There has been no DR test since 2022.

**Vendor and Infrastructure**

AWS for the multi-region infrastructure (we're already on AWS). Terraform for infrastructure-as-code, which means the failover environment is codified and can be spun up reproducibly. Key new capability: automated failover testing. I want a script that runs monthly in a non-production environment and validates that the failover sequence completes within 4 hours. If it doesn't, that's a page.

**Quarterly DR Drills**

In addition to automated testing, I'm reinstating quarterly manual DR drills. These are different from automated tests: they validate human processes, communication chains, and decision-making under pressure. The first drill is scheduled for Q3. Participants: IT operations team, engineering on-call lead, VP of Engineering.

**Compliance Implications**

SOC 2 Type II audit is in 6 months. Control CC7.5 (recovery from a disruption) requires evidence of tested recovery procedures. We need at least one successful DR drill on record before the audit. The Q3 drill timing is not accidental.

**Projected Timeline**

Q2: Infrastructure provisioning in us-west-2, database replication configured, automation scripted. Q3: First manual DR drill. Q4: RPO/RTO targets formally certified, audit documentation prepared.
""",
                "scenes": [
                    {
                        "title": "Terraform: us-west-2 failover environment",
                        "stage": "in_progress",
                        "notes": "Systems engineer building the Terraform config. RDS cross-region replication module done. Application tier in progress.",
                    },
                    {
                        "title": "Automated failover test script",
                        "stage": "planning",
                        "notes": "Script to run monthly in non-production, page if failover takes > 4 hours. Engineering dependency: need application tier Terraform first.",
                    },
                    {
                        "title": "Q3 manual DR drill",
                        "stage": "planning",
                        "notes": "Scheduled Q3. Participants: IT ops team, engineering on-call lead, VP Engineering. SOC 2 evidence requirement.",
                    },
                    {
                        "title": "DR plan v2 document",
                        "stage": "in_progress",
                        "notes": "Updated plan with new RPO/RTO targets, failover runbook, and communication chain. Draft review with VP Engineering next week.",
                    },
                    {
                        "title": "RDS cross-region replication validation",
                        "stage": "awaiting_data",
                        "notes": "Waiting on systems engineer to validate replication lag metrics before signing off on the configuration.",
                    },
                ],
            },
            {
                "title": "Internal Tools Consolidation",
                "color": "#1e293b",
                "notes": """\
Meridian currently pays for 47 distinct SaaS tools. I know this because I audited every contract and expense line over two months last year. When you look at actual usage data — logins in the past 90 days, file edits, integrations active — 12 of those tools have fewer than 10 active users. Several have zero active users and are month-to-month holdovers from teams that departed.

**Audit Results**

The audit categorized tools into three buckets: (1) Core — used by 80%+ of the organization, integrated into workflows. Untouchable in the short term. (2) Overlap — functionality covered by a core tool or by another non-core tool. Migration feasible. (3) Orphan — active contracts, no active users. Immediate cancellation.

Immediate cancellations identified: 8 tools ($23K/year). Overlap migrations: 9 tools requiring user migration and training ($157K/year if we replace with core tool seats or internal solutions). Target: reduce from 47 to 30 tools by end of year.

**Migration Plans for Deprecated Tools**

The most contested migration: three departments use separate project management tools (Asana for marketing, Monday for HR, ClickUp for the legal team) when Jira is the company standard. Each department has legitimate complaints about Jira (overkill for non-engineering workflows). My position: the consolidation saves $40K/year and reduces integration surface area. I'm offering to fund Jira configuration work (custom workflows for non-engineering teams) as a migration inducement. Marketing has agreed. HR is resistant. Legal hasn't responded.

**Enterprise Agreement Negotiations**

We're in active renegotiation with three vendors: Atlassian (Jira/Confluence), Zoom, and Okta. The zero-trust migration adds Okta seats, which I'm using as negotiating leverage: "We're increasing our Okta footprint by 40% — what does a multi-year enterprise agreement look like?" Current estimate: $35K in additional savings from favorable renegotiation.

**Projected Savings**

Immediate cancellations: $23K/year. Overlap migrations (deprecating 9 tools): $157K/year. Enterprise agreement renegotiation savings: $35K estimate. Less: migration costs (configuration, training, professional services): ~$35K one-time. Net first-year savings: approximately $180K.

**Department Pushback Management**

I document every exception request and the rationale. If a department wants to keep a tool that's on the deprecation list, they submit a written business case. Three have come in: one was approved (specialized research tool with no Meridian equivalent), two were denied (tool preference without functional differentiation). The documentation protects the process.
""",
                "scenes": [
                    {
                        "title": "HR migration to Jira: negotiation",
                        "stage": "in_progress",
                        "notes": "HR is resistant. Scheduled a walkthrough of custom Jira workflow options with HR director next Tuesday.",
                    },
                    {
                        "title": "Legal team: awaiting response on Jira migration",
                        "stage": "awaiting_data",
                        "notes": "Sent migration proposal 2 weeks ago. No response. Following up this week.",
                    },
                    {
                        "title": "Okta enterprise agreement renegotiation",
                        "stage": "in_progress",
                        "notes": "Using zero-trust seat expansion as leverage. Okta account team has a proposal coming by end of week.",
                    },
                    {
                        "title": "Immediate cancellations: 8 orphan tools",
                        "stage": "complete",
                        "notes": "$23K/year cancelled. All 8 contracts terminated. No active users, no migration needed.",
                    },
                    {
                        "title": "Marketing migration to Jira",
                        "stage": "complete",
                        "notes": "Marketing agreed. Custom workflow configured. Asana contract cancelled at renewal.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "DR drill results?",
                    },
                    {
                        "role": "cairn",
                        "content": "No drill results on record — the Q3 manual DR drill hasn't run yet. It's in planning stage, scheduled for Q3. The last drill was 2022 and took 11 hours. The 2023 drill was cancelled. Do you want an update on the infrastructure build that precedes the drill?",
                    },
                    {
                        "role": "user",
                        "content": "Terraform status.",
                    },
                    {
                        "role": "cairn",
                        "content": "In progress. RDS cross-region replication module is done. Application tier Terraform still in progress — that's the blocker for the automated failover test script. Waiting on systems engineer to validate replication lag metrics before sign-off.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Calendar.",
                    },
                    {
                        "role": "cairn",
                        "content": "Today: 6am–8am blocked (no meetings). 9am, network engineer check-in on Okta SAML config. 1pm, HR director walkthrough — Jira custom workflow demo. 3pm, end of day.\n\nTomorrow: 6am–8am blocked. 10am, Okta account team — enterprise agreement proposal. Nothing after that.",
                    },
                    {
                        "role": "user",
                        "content": "Move HR to Wednesday.",
                    },
                    {
                        "role": "cairn",
                        "content": "I can't move calendar events directly, but I've noted the reschedule request: HR director Jira walkthrough should move from Tuesday 1pm to Wednesday. You'll need to send the reschedule invitation. Do you want me to draft the message?",
                    },
                    {
                        "role": "user",
                        "content": "No.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Status on Zscaler POC.",
                    },
                    {
                        "role": "cairn",
                        "content": "No Zscaler POC is in your current scenes — the zero-trust vendor evaluation is ongoing but your notes indicate Cloudflare enterprise pricing is the current open item. Zscaler was evaluated and is in contention based on procurement pricing, but no POC is recorded as in progress. Did you start a Zscaler test environment that isn't captured yet?",
                    },
                    {
                        "role": "user",
                        "content": "No POC. I meant the pricing negotiation. Procurement sent something.",
                    },
                    {
                        "role": "cairn",
                        "content": "Understood. The Zscaler pricing from procurement isn't in your act notes — just the note that Zscaler is 18% cheaper than Cloudflare rack rate on a multi-year enterprise agreement. If procurement sent a formal proposal, it should be added to the zero-trust act for the vendor comparison. Want me to add a scene to track it?",
                    },
                    {
                        "role": "user",
                        "content": "Yes. 'Zscaler enterprise proposal — review before Cloudflare pricing arrives.'",
                    },
                    {
                        "role": "cairn",
                        "content": "Scene added to Zero Trust Network Migration: \"Zscaler enterprise proposal — review before Cloudflare pricing arrives.\" Stage: awaiting_data (pending Cloudflare response for comparison).",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Vendor call moved?",
                    },
                    {
                        "role": "cairn",
                        "content": "Which vendor? Okta is scheduled tomorrow at 10am. Cloudflare rep timing is unconfirmed — awaiting their response. Atlassian renegotiation hasn't been scheduled yet.",
                    },
                    {
                        "role": "user",
                        "content": "Okta. Moved to Thursday.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted — Okta enterprise agreement call moved to Thursday. Update your calendar. I'll reflect Thursday in your act notes.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Viktor starts work at 6am and leaves by 3pm. The first two hours (6-8am) are blocked as no-meeting time — reserved for real work without interruptions.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Viktor Petrov",
                    "insight": "Work schedule: 6am-3pm, 6-8am no-meeting block",
                    "category": "work_habit",
                },
            },
            {
                "narrative": "Viktor's change management window is Sunday 2am–6am. Infrastructure changes outside this window require his explicit sign-off.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Viktor Petrov",
                    "insight": "Change window: Sunday 2-6am. No exceptions without explicit sign-off.",
                    "category": "operational_policy",
                },
            },
            {
                "narrative": "Viktor trusts Cloudflare Access over Zscaler technically (simpler architecture, cleaner integration with existing Cloudflare DNS). Procurement prefers Zscaler pricing — 18% cheaper on multi-year enterprise agreement. Waiting on Cloudflare enterprise pricing before making final recommendation.",
                "entity_type": "decision",
                "entity_data": {
                    "decision": "Zero trust vendor: Cloudflare preferred technically, Zscaler preferred by procurement on price",
                    "status": "pending — awaiting Cloudflare enterprise pricing",
                    "off_table": "BeyondCorp — requires too deep Google Workspace integration",
                },
            },
            {
                "narrative": "Riley Chen is Viktor's DevOps engineer (separate reporting line from the main IT team). Viktor has assessed Riley as brilliant with Kubernetes but weak on networking/DNS, and struggles with prioritization — context-switches frequently. Viktor's management approach: try to keep Riley focused on one project at a time.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Riley Chen",
                    "role": "DevOps Engineer",
                    "strengths": "Kubernetes, CI/CD",
                    "weaknesses": "networking/DNS, prioritization",
                    "management_note": "Keep focused on one project at a time — works about half the time",
                },
            },
            {
                "narrative": "SOC 2 Type II audit is in 6 months. Two active work tracks are directly tied to audit controls: the permissions redesign (least-privilege access, CC6) and the DR overhaul (recovery from disruption, CC7.5). The Q3 DR drill is timed to produce audit evidence.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Compliance",
                    "insight": "SOC 2 audit in 6 months. DR drill must complete Q3 for audit evidence. Permissions redesign covers CC6.",
                    "category": "compliance_constraint",
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },
    {
        "id": "riley_chen",
        "identity": {
            "full_name": "Riley Chen",
            "department": "Operations",
            "title": "DevOps Engineer",
        },
        "personality": "anxious",
        "your_story": """\
# Riley Chen — DevOps Engineer

I'm 26, self-taught, bootcamp. I did a 6-month intensive in LA, got my first job as a junior infrastructure engineer, and have been doing DevOps work for 3 years. I manage CI/CD pipelines, monitoring and observability, and cloud infrastructure. I recently picked up Kubernetes and it's the thing I'm most competent at and also the thing giving me the most stress right now because we're in the middle of migrating stateful services to K8s and stateful services in Kubernetes are terrifying.

Honestly I'm working on too many things at once. I know this. Viktor knows this. We've talked about it. I try to focus, I really do, but when something breaks or someone pings me about something interesting or I see a potential optimization, I get pulled in. I keep a personal Notion doc I call "things I'll forget" — it's a brain dump of half-finished thoughts and tasks that I meant to get back to. I forget to check it about as often as I remember to.

I'm Chinese-American, grew up in LA. Still live there. I work remote, which is both good (no commute, more focus time) and bad (no natural forcing function to stop working — I lose track of time constantly).

My strongest skill is Kubernetes. I understand the resource model, the scheduling, the operator pattern, the storage architecture. I built our staging cluster from scratch. I'm weakest on networking and DNS — it's the part of the stack that still feels like magic to me, which is uncomfortable because DNS is never actually magic, it's just something I haven't fully internalized yet.

The current big projects: Kubernetes Phase 2 (migrating stateful services), observability stack upgrade (replacing Datadog with open-source), and CI/CD pipeline optimization. Three significant projects simultaneously, which is exactly the problem Viktor keeps flagging. I don't have a good answer for it except that all three feel urgent to me all the time.
""",
        "acts": [
            {
                "title": "Kubernetes Migration Phase 2",
                "color": "#ea580c",
                "notes": """\
Phase 1 moved stateless services to Kubernetes and went fine. Phase 2 is the part I've been avoiding: stateful services. PostgreSQL, Redis, and Elasticsearch. Running stateful workloads in Kubernetes is doable — it's not experimental anymore — but it's much more operationally complex than stateless, and the failure modes are scarier. If a stateless pod crashes, Kubernetes restarts it. If a stateful pod loses its persistent volume claim or its operator gets confused, you have a data incident.

**Operator Selection**

For PostgreSQL, I'm using the Zalando Postgres Operator. It's the most mature option, handles high-availability with Patroni, supports point-in-time recovery, and has good community documentation. For Redis, I'm using the Redis Operator from Redis Labs (now Redis Inc.) — it supports Sentinel configuration and cluster mode. For Elasticsearch, I'm using the Elastic Cloud on Kubernetes (ECK) operator from Elastic — official support, well-maintained.

I spent two weeks evaluating alternatives before settling on these three. The Crunchy Data Postgres Operator was a close second for Postgres but the Zalando operator has better Patroni integration for our HA requirements.

**Backup Strategies**

Velero for cluster-level backup (manifests, PV snapshots) to S3. Velero runs nightly with 30-day retention. For Postgres specifically, I'm also running pgBackRest for continuous WAL archiving to S3 — this gives us PITR (point-in-time recovery) down to the minute, independent of the Kubernetes snapshot. Redis backups are RDB snapshots every 15 minutes plus AOF logging. Elasticsearch: snapshot to S3 via the Elasticsearch snapshot API, hourly.

**PV Provisioning Challenges**

The staging cluster has been a nightmare for persistent volume provisioning. We're using the AWS EBS CSI driver with gp3 volumes. The challenges: (1) Node affinity constraints for stateful pods + PV availability zone constraints interact in non-obvious ways. I had three Postgres pods in a crash loop for two days before I figured out the AZ mismatch. (2) Volume expansion requests are slow — EBS expansion takes 6+ minutes, which caused a false alert storm. I've tuned the alerting thresholds, but the root issue is that gp3 expansion is just slow.

**Monitoring Gaps**

Monitoring for stateful services is more complex than stateless. I need Patroni metrics for Postgres HA state (leader, replica lag), Redis INFO stats, and Elasticsearch cluster health. None of these are exposed by default from the operators — they need custom ServiceMonitor configs for Prometheus scraping. I've built the Postgres and Redis ServiceMonitors. Elasticsearch is still missing.

**Production Cutover Plan**

This is the part that keeps me up. The plan: (1) Run services in parallel for 2 weeks — old VM-based services stay live, K8s services handle a small traffic percentage via feature flag. (2) Validate data consistency between the two (this is where I get nervous — if they diverge, we have a problem). (3) Full cutover in a Sunday change window. (4) Old VM services stay running for 1 week post-cutover as rollback option. The rollback procedure is documented in the runbook — or it will be once I finish writing it.
""",
                "scenes": [
                    {
                        "title": "Zalando Postgres Operator: staging validation",
                        "stage": "in_progress",
                        "notes": "Pods stable after AZ mismatch fix. PITR recovery tested once — worked. Need 3 more successful recovery tests before confident.",
                    },
                    {
                        "title": "Redis Operator: staging deployment",
                        "stage": "in_progress",
                        "notes": "Deployed. Sentinel config working. RDB snapshots to S3 confirmed. AOF logging enabled.",
                    },
                    {
                        "title": "Elasticsearch: ServiceMonitor + ECK operator",
                        "stage": "planning",
                        "notes": "ECK operator not yet deployed in staging. ServiceMonitor for Prometheus also not built. Monitoring gap.",
                    },
                    {
                        "title": "Production cutover runbook",
                        "stage": "in_progress",
                        "notes": "DRAFT — incomplete. Traffic splitting section done. Data consistency validation section not started. Viktor needs to review before cutover.",
                    },
                    {
                        "title": "Parallel run: traffic splitting setup",
                        "stage": "planning",
                        "notes": "Need to configure feature flag for traffic percentage routing. Depends on runbook completion.",
                    },
                    {
                        "title": "PV provisioning: AZ mismatch root cause fix",
                        "stage": "complete",
                        "notes": "Added explicit topology spread constraints to StatefulSet specs. Postgres pods stable for 8 days.",
                    },
                ],
            },
            {
                "title": "Observability Stack Upgrade",
                "color": "#c2410c",
                "notes": """\
We're paying $24,000 per month for Datadog. I like Datadog. It's good. It also costs $288K per year for a company our size, and I proposed to Viktor that we could run a comparable open-source stack for around $8K per month (compute + storage for self-hosted, plus some managed components). Viktor approved the migration. Now I have to actually do it.

**Cost Analysis**

Datadog: $24K/month. Breaks down as: infrastructure monitoring ($8K), APM ($7K), log management ($6K), synthetics/uptime ($3K). The APM component is the one I'm most worried about replacing — Datadog's APM has automatic instrumentation and really good distributed trace visualization. The open-source equivalent (Grafana Tempo + OpenTelemetry) requires manual instrumentation in some places.

Projected self-hosted stack: Grafana (free) + Prometheus + Loki (logs) + Tempo (traces) + Mimir (long-term metrics storage). Compute: 3 m5.xlarge instances for the Prometheus/Mimir layer, 2 for Loki, 1 for Tempo, Grafana on a smaller instance. S3 for long-term storage. Estimated: $8K/month including S3 costs.

**Migration Phases**

Phase 1: Stand up the Grafana stack in parallel. Don't turn anything off. Run both for 30 days. Phase 2: Migrate dashboards and alerts (this is the tedious part — we have 340 Datadog dashboards, not all of which are actively used). Phase 3: Migrate APM instrumentation. Phase 4: Migrate synthetics/uptime monitoring (replace Datadog synthetics with Grafana OnCall + Prometheus blackbox exporter). Phase 5: Cancel Datadog. This is a 5-month migration.

**Feature Parity Gaps**

The gaps I know about: (1) Datadog's anomaly detection is ML-based; Prometheus alerting is threshold-based. We'll lose some smart alerting and replace it with dumber, more manually tuned alerts. (2) Datadog's log parsing pipeline is more powerful than Loki's label-based approach for complex multi-format logs. (3) The Datadog mobile app is better than Grafana's mobile experience. This is a minor inconvenience. (4) Datadog synthetics has real-browser testing; Prometheus blackbox does not. We'll lose synthetic browser tests.

**Team Training**

Engineering uses Datadog daily for production debugging. Moving to Grafana means everyone needs to learn PromQL for ad-hoc queries. I'm planning two internal training sessions — one on PromQL basics, one on the new dashboard layout. The on-call team also needs Grafana OnCall training before I switch over alerting.

**Dashboard Recreation**

340 Datadog dashboards. I've categorized them: 120 are critical (on-call team uses daily), 140 are occasionally used (once a week or less), 80 are never used (last viewed 90+ days ago). I'll manually migrate the 120 critical dashboards. The 140 occasional ones I'll migrate on-demand as engineers ask. The 80 unused ones I'll archive and let die.

**Alert Migration**

We have 218 Datadog monitor alerts. I need to translate each to Prometheus alerting rules. The threshold-based ones are straightforward. The anomaly detection ones need to be redesigned as static thresholds — I'll use the past 90 days of Datadog data to set reasonable baselines.

**On-Call Integration**

Currently: Datadog monitors → PagerDuty. New: Prometheus Alertmanager → PagerDuty. The PagerDuty integration is well-documented; this part is low-risk.
""",
                "scenes": [
                    {
                        "title": "Grafana + Prometheus + Loki: initial stack deployment",
                        "stage": "in_progress",
                        "notes": "Core stack running in staging. Prometheus scraping most services. Loki ingesting logs from 60% of services.",
                    },
                    {
                        "title": "Dashboard migration: 120 critical dashboards",
                        "stage": "in_progress",
                        "notes": "43 of 120 critical dashboards recreated in Grafana. Estimated 2 more weeks at current pace.",
                    },
                    {
                        "title": "PromQL training sessions (2x)",
                        "stage": "planning",
                        "notes": "Not scheduled yet. Need critical dashboard migration mostly done first so examples are real.",
                    },
                    {
                        "title": "APM: OpenTelemetry instrumentation for 3 core services",
                        "stage": "planning",
                        "notes": "Blocked on Grafana Tempo validation. This is the hardest part — need 3 engineers to add OTEL to their services.",
                    },
                    {
                        "title": "Alert migration: 218 Datadog monitors → Prometheus rules",
                        "stage": "planning",
                        "notes": "Not started. Need Prometheus running in production (not just staging) first. Threshold baseline analysis in progress.",
                    },
                    {
                        "title": "Cost analysis and migration proposal",
                        "stage": "complete",
                        "notes": "$24K/mo Datadog vs projected $8K/mo self-hosted. Viktor approved. Migration authorized.",
                    },
                ],
            },
            {
                "title": "CI/CD Pipeline Optimization",
                "color": "#9a3412",
                "notes": """\
Our CI/CD pipeline builds take an average of 18 minutes. This is too long. Engineers context-switch during builds, push up half-finished PRs to "see if it passes," and the build queue backs up during peak morning hours. The target is under 8 minutes. I profiled the builds and know where the time goes. I don't have unlimited time to fix it, which is the meta-problem.

**Profiling Results**

I spent a week instrumenting the GitHub Actions workflows with timing annotations. Where the 18 minutes goes: (1) Docker image build: 7.2 minutes average. Layer caching is happening but inconsistently — the base image layer is cached, but application dependency layers bust the cache on nearly every PR because the requirements file changes frequently. (2) Test suite: 6.8 minutes. Currently single-threaded, sequential. No parallelization. (3) Linting and type checking: 2.1 minutes. (4) Docker push + deploy step: 1.9 minutes.

**Docker Layer Caching**

The fix here is to separate the dependency installation layer from the code copy layer in the Dockerfile, and to use a consistent, hash-keyed cache for the dependency layer in GitHub Actions. Currently the Dockerfile copies the entire repo before installing dependencies, which means any code change busts the dependency cache. Fixing the Dockerfile ordering alone should save 4-5 minutes on builds that don't change dependencies (which is most builds).

**Test Parallelization**

The test suite is pytest, 1,847 tests, single process. pytest-xdist supports parallel test execution across multiple processes. On a 4-core GitHub Actions runner, we could run 4 processes with reasonable overhead. Estimated reduction: from 6.8 to ~2 minutes. Risk: some tests are not process-safe (they share a SQLite database file). I need to audit for test isolation issues before enabling xdist, or use a separate database file per worker.

**Bazel Evaluation**

I looked at Bazel for build caching and remote execution. My conclusion: not worth it for our scale. Bazel's build graph analysis and remote caching are powerful but require significant upfront investment in BUILD file authoring. For a codebase our size, the Docker layer caching + pytest-xdist combo will get us to the 8-minute target without the operational overhead of Bazel. Revisit if we grow past 200 engineers.

**GitHub Actions Optimization**

Beyond Docker and test parallelization: (1) Selective testing — only run tests affected by the changed files. I'm evaluating `pytest-testmon` for this. Risk: false confidence if the impact analysis misses an indirect dependency. (2) Artifact caching — GitHub Actions cache for node_modules and pip packages. Currently not configured. (3) Runner sizing — upgrading from the 2-core standard runner to a 4-core runner costs $0.016/minute extra but would roughly double throughput for parallelized steps.

**Metrics Tracking**

I added build time tracking to a Grafana dashboard (the Grafana stack that's still in staging — I need to get this to production). Current baseline: 18.3 minutes average over last 500 builds, p90 at 23.1 minutes. Target: 8 minutes average, p90 under 12. I'll track weekly until the target is hit.
""",
                "scenes": [
                    {
                        "title": "Dockerfile layer ordering fix",
                        "stage": "in_progress",
                        "notes": "Restructuring Dockerfiles across 4 services. 2 done, 2 remaining. Projected saving: 4-5 min on most builds.",
                    },
                    {
                        "title": "pytest-xdist: test isolation audit",
                        "stage": "in_progress",
                        "notes": "Auditing for shared SQLite database test dependencies before enabling parallel workers. Found 3 problematic test files so far.",
                    },
                    {
                        "title": "GitHub Actions: artifact caching for pip and node_modules",
                        "stage": "planning",
                        "notes": "Straightforward config change. Low risk. Just haven't gotten to it. Should save ~90 seconds.",
                    },
                    {
                        "title": "Selective testing: pytest-testmon evaluation",
                        "stage": "planning",
                        "notes": "Evaluating impact analysis reliability. Worried about false confidence. Need to run shadow mode (run all tests, compare which testmon would have skipped) before enabling.",
                    },
                    {
                        "title": "Build time Grafana dashboard",
                        "stage": "complete",
                        "notes": "Dashboard built (in staging). Baseline: 18.3 min average, p90 23.1 min. Needs to move to prod once Grafana stack is promoted.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Okay so I'm in the middle of the Grafana migration but the K8s cluster is throwing OOM errors on the staging Postgres operator and I also need to fix the CI pipeline because builds are timing out — what should I tackle first? Also did I have a meeting at 2?",
                    },
                    {
                        "role": "cairn",
                        "content": "You did have a meeting at 2 — Viktor's weekly DevOps check-in. It's currently 2:07.\n\nOn the three things: the Postgres OOM errors are the most urgent because they're an active failure in staging that blocks the production cutover. Grafana migration and CI pipeline are both important but neither is on fire right now.\n\nSpecific recommendation: triage the Postgres OOM first. Check if it's a memory limit on the pod spec or an actual memory leak in Postgres — those have very different fixes. Then join Viktor's meeting late rather than skipping it. Grafana and CI pipeline can wait an hour.",
                    },
                    {
                        "role": "user",
                        "content": "Okay yeah you're right. The OOM is on the Postgres primary pod. The operator is reporting it as an eviction. I think the memory limit in the StatefulSet is too low but I'm not sure.",
                    },
                    {
                        "role": "cairn",
                        "content": "If it's an eviction rather than a process OOM kill, the container memory limit is the likely cause. Check `kubectl describe pod <postgres-primary-pod>` for the eviction reason — it'll say whether it was the container limit or node-level memory pressure.\n\nIf it's the container limit: look at the actual working set memory in your Prometheus metrics for the pod over the last 24 hours (`container_memory_working_set_bytes`). Set the limit to 20% above the p95 working set. If it's node-level pressure: you have a different problem — another pod is consuming too much and the Postgres pod is getting evicted as a lower-priority workload. Check node memory usage and look at pod priorities.\n\nDo this, note what you find, then go to the Viktor meeting.",
                    },
                    {
                        "role": "user",
                        "content": "Container limit. It was set to 2Gi but the working set is hitting 2.4Gi under load. I'll bump it to 3Gi.",
                    },
                    {
                        "role": "cairn",
                        "content": "Good. 3Gi gives you headroom. Update the StatefulSet spec, apply it, and confirm the pod comes back up without eviction before you move on. Add a note to the Kubernetes Phase 2 act so you remember this limit was adjusted and why — you'll want that context when you do the production sizing.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I forgot to update the runbook for the Redis migration, can you remind me tomorrow morning?",
                    },
                    {
                        "role": "cairn",
                        "content": "Reminder set for tomorrow 9am: update the Redis migration runbook section of the Kubernetes Phase 2 cutover runbook. Which section is missing — the traffic cutover, the rollback procedure, or the Sentinel configuration steps?",
                    },
                    {
                        "role": "user",
                        "content": "The data consistency validation part. I know what it should say I just haven't written it.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted. Reminder updated: \"Write Redis data consistency validation section of K8s Phase 2 cutover runbook — you know what it should say, just write it.\" 9am tomorrow.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Viktor asked me to focus on one project this week. Which one should it be?",
                    },
                    {
                        "role": "cairn",
                        "content": "Based on your current scene states, Kubernetes Phase 2 has the most active blockers and is the one with production risk. Two things are in progress simultaneously: the Postgres operator staging validation (needs 3 more successful PITR recovery tests) and the cutover runbook (data consistency section missing).\n\nThe CI/CD pipeline and Grafana migration both have in-progress scenes, but neither is blocking anything else right now. Grafana has 43 of 120 critical dashboards done — good progress but not urgent. CI pipeline has 2 of 4 Dockerfile fixes done.\n\nRecommendation: Kubernetes Phase 2 this week. Specifically: finish the 3 PITR recovery tests, finish the runbook data consistency section, and get the ECK Elasticsearch operator deployed in staging. Those three things are the remaining blockers before you can schedule the parallel run.\n\nTell Viktor that's the plan before you start, so you're aligned.",
                    },
                    {
                        "role": "user",
                        "content": "Okay but while I was thinking about Kubernetes I thought of an optimization for the CI pipeline Dockerfile fix — it's like a 10-minute change. Can I just do that real quick?",
                    },
                    {
                        "role": "cairn",
                        "content": "Write it down right now and do it Friday. If you switch now, you'll end up in the CI pipeline codebase for an hour, not 10 minutes — and then Viktor will ask you at the end of the week how Kubernetes is going.\n\nWhat's the optimization? I'll add it to your CI/CD notes so you don't forget it.",
                    },
                    {
                        "role": "user",
                        "content": "Using BuildKit's `--mount=type=cache` for pip instead of the GitHub Actions cache action. It's cleaner.",
                    },
                    {
                        "role": "cairn",
                        "content": "Added to the CI/CD Pipeline Optimization act notes: \"Use BuildKit --mount=type=cache for pip instead of GitHub Actions cache action — cleaner approach, evaluate when returning to this project.\" It'll be there Friday. Now: Kubernetes.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I'm stressed about the Postgres production cutover. Walk me through what could go wrong.",
                    },
                    {
                        "role": "cairn",
                        "content": "The honest risk list:\n\n**Data divergence during parallel run.** You'll have VM Postgres and K8s Postgres both accepting writes via feature flag traffic split. If the consistency check misses a write that goes to one but not both — which can happen in a network partition or during the switchover moment — you have diverged data. Mitigation: make the parallel run one-directional if possible (VM is authoritative, K8s is read-only replica during the parallel phase), only switch writes at full cutover.\n\n**Patroni failover during cutover.** If the primary pod restarts during the cutover window, Patroni should elect a replica. But if the replica is behind, you have a brief write gap. Mitigation: verify replica lag is under 5 seconds before starting cutover, and practice the Patroni failover in staging until it's boring.\n\n**Volume claim binding on production nodes.** You hit AZ mismatch issues in staging. Production has different AZ distribution. Same topology spread constraint fix, but you haven't tested it in production. Mitigation: pre-provision the PVCs in production before the cutover window so you know they bind correctly.\n\n**Operator version mismatch.** If the Zalando operator version in production differs from staging — even a patch version — the behavior could differ. Mitigation: pin the operator version in your Helm values and confirm it's identical between environments.\n\nThe rollback is your safety net for all of these: 1 week of old VM services still running post-cutover. The runbook needs to be complete and practiced before you go near production. Is the runbook your current blocker?",
                    },
                    {
                        "role": "user",
                        "content": "Yeah. The data consistency validation section. I keep avoiding it because it's the part I'm least confident about.",
                    },
                    {
                        "role": "cairn",
                        "content": "That's the part most worth writing, then. Avoidance is usually a signal that the section contains a decision you haven't made yet — in this case, probably: what exactly do you check, at what frequency, and what's the threshold for aborting the cutover?\n\nDraft answer: compare row counts and last-modified timestamps on the 5 highest-write tables every 5 minutes during the parallel run. If any table's counts diverge by more than 0.01%, pause and investigate before proceeding. This is simple and auditable. You can refine it, but have something on paper.\n\nReminder is still set for 9am tomorrow. Write the section then.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Riley frequently context-switches and loses track of what they were working on. Keeps a personal Notion doc called 'things I'll forget' but often forgets to check it. Viktor has asked Riley to focus on one project at a time — this works about half the time.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Riley Chen",
                    "insight": "Context-switching is a known problem. Viktor's directive: one project at a time. Notion doc 'things I'll forget' exists but is underused.",
                    "category": "work_habit",
                },
            },
            {
                "narrative": "Riley's manager is Viktor Petrov (IT Operations Manager). Viktor manages the broader IT team; Riley is on a separate reporting line as DevOps engineer.",
                "entity_type": "person",
                "entity_data": {
                    "name": "Viktor Petrov",
                    "role": "IT Operations Manager",
                    "relationship": "manager",
                    "direction": "Keep Riley focused; one project at a time",
                },
            },
            {
                "narrative": "Riley is strongest with Kubernetes — understands the resource model, scheduling, operator pattern, and storage architecture. Weakest with networking and DNS, which still feels like 'magic' and is an acknowledged gap.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Riley Chen",
                    "insight": "Kubernetes strength, networking/DNS weakness — DNS feels like magic, acknowledged gap",
                    "category": "skill_profile",
                },
            },
            {
                "narrative": "Staging Postgres OOM incident: container memory limit was set to 2Gi but working set hit 2.4Gi under load. Bumped to 3Gi. Eviction cause was container limit, not node-level pressure. Production StatefulSet spec needs to account for this during sizing.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Kubernetes Phase 2",
                    "insight": "Postgres container memory limit: was 2Gi, raised to 3Gi after eviction. Production sizing must account for 2.4Gi p95 working set.",
                    "category": "operational_incident",
                },
            },
            {
                "narrative": "Riley identified a CI/CD pipeline optimization: use BuildKit --mount=type=cache for pip instead of the GitHub Actions cache action. Deferred to avoid context-switching away from Kubernetes focus week. Captured for later.",
                "entity_type": "task",
                "entity_data": {
                    "task": "CI/CD: use BuildKit --mount=type=cache for pip instead of GitHub Actions cache action",
                    "status": "deferred",
                    "reason": "Context-switching guard — return when Kubernetes Phase 2 is stable",
                },
            },
            {
                "narrative": "Grafana observability migration: 43 of 120 critical dashboards recreated. Datadog running in parallel at $24K/month. Migration authorized by Viktor. 5-phase plan: stand up stack, migrate dashboards, migrate APM instrumentation, migrate synthetics, cancel Datadog.",
                "entity_type": "insight",
                "entity_data": {
                    "subject": "Observability Stack Upgrade",
                    "insight": "43/120 critical dashboards done. Parallel run ongoing. Phase 3 (APM) is the hardest — needs OTEL instrumentation from 3 engineering teams.",
                    "category": "project_status",
                },
            },
            {
                "narrative": "Riley avoids writing the Postgres production cutover runbook data consistency validation section because it contains an unresolved decision: what exactly to check, at what frequency, and what threshold triggers a cutover abort. Reminder set for 9am the following day.",
                "entity_type": "task",
                "entity_data": {
                    "task": "Write K8s Phase 2 cutover runbook: Redis data consistency validation section and Postgres parallel run consistency checks",
                    "status": "pending",
                    "blocker": "Unresolved decision on check frequency and abort threshold",
                    "draft_answer": "Compare row counts + last-modified on top-5 write tables every 5 min; abort if divergence > 0.01%",
                },
            },
        ],
        "emails": [],
        "calendar_events": [],
    },
]
