"""Test user profiles batch 1 — for Cairn testgen tooling.

Contains 4 realistic user profiles representing engineering and marketing
personas. Each profile includes acts, scenes, conversations, and memories
that reflect authentic work patterns and communication styles.
"""

PROFILES_1 = [
    {
        "id": "priya_chandrasekaran",
        "identity": {
            "full_name": "Priya Chandrasekaran",
            "department": "Engineering",
            "title": "Senior Software Engineer",
        },
        "personality": "analytical",
        "your_story": """\
# Priya Chandrasekaran — Senior Software Engineer, Real-Time Sync

I'm a senior software engineer on the Real-Time Sync team at Meridian Labs, an enterprise
collaboration tools company based in the Pacific Northwest. I've been at Meridian for four years,
joining from a Series B startup where I built the core sync engine from scratch. Before that, I
spent three years at a distributed-systems consultancy working on consistency guarantees for
financial data pipelines.

I have eleven years of professional software engineering experience, with a deep specialization in
distributed systems, conflict-free replicated data types (CRDTs), and consensus protocols. My
undergraduate degree is in Computer Science from UC San Diego, and I completed a part-time master's
degree in Distributed Systems from Georgia Tech while working full-time.

At Meridian, my team owns the synchronization layer that keeps collaborative documents consistent
across thousands of concurrent users and unreliable network conditions. I'm the technical lead on
the CRDT conflict resolution engine — a project I proposed after we had a significant data loss
incident eighteen months ago caused by a race condition in our legacy operational transform system.

I care deeply about correctness. I measure things before I optimize them. I write thorough design
docs and expect my colleagues to push back on them. Code reviews from me tend to be detailed and
specific, and I appreciate the same in return. I don't enjoy meetings that could have been emails,
but I genuinely value a well-structured async technical discussion.

Outside work, I'm interested in formal verification methods — I've been slowly working through the
TLA+ book — and I train for half marathons. I live in Portland with my partner and our two cats.
I'm Indian-American, first generation, and I think a lot about mentorship as a result.
""",
        "acts": [
            {
                "title": "CRDT Conflict Resolution Engine",
                "color": "#6366f1",
                "notes": """\
The CRDT Conflict Resolution Engine project is the most technically ambitious initiative on the
Real-Time Sync team this year. The goal is to replace the existing operational transform (OT)
system — which has produced subtle data corruption bugs under high concurrency — with a principled
CRDT-based approach targeting 99.99% merge correctness across all online/offline transition
scenarios we can enumerate.

**Background and Motivation**

Eighteen months ago, a race condition in our OT engine caused partial document loss for roughly
400 enterprise customers during a regional failover. The root cause was that our OT system assumed
total ordering of operations delivered by the server, an assumption that broke under network
partition. CRDTs avoid this class of error entirely because merge is commutative, associative, and
idempotent — it doesn't matter what order operations arrive in, the result is always the same.

**Technical Approach**

We're implementing a variant of the Logoot sequence CRDT for text editing, extended with a custom
metadata layer to carry Meridian-specific semantics like comments, formatting spans, and
permissions annotations. Causality is tracked using a vector clock per client session, and we use
Lamport timestamps as tiebreakers when the vector clocks are concurrent.

The most difficult technical problem has been tombstone garbage collection. CRDTs for sequences
need to retain deleted elements (tombstones) so that concurrent insertions can be correctly
positioned relative to them. If you collect tombstones too aggressively, remote peers that were
offline miss context and misplace insertions. We're implementing a distributed GC protocol that
uses a global quiescence signal: tombstones are only collected after all known peers have
acknowledged they've seen the deletion, with a configurable retention window (currently 30 days)
for peers that are persistently offline.

**Current Status**

The prototype is working in our staging environment. Single-client round-trips are passing all
correctness tests. We've identified seventeen edge cases that still fail: primarily scenarios
involving three-way concurrent edits where one client is operating on a stale snapshot more than
five minutes old. These failures are non-data-loss (they resolve on next sync) but they produce
visible glitches — temporary duplicate content — that we need to eliminate before shipping.

**Team**

Core implementers are me, Theo Nakamura (distributed systems), and a contract engineer, Ravi
Subramanian, handling the client-side integration in our Electron app. The protocol team (Marcus
Chen's group) needs to finalize the v3 API surface before we can close our integration layer —
this is currently the critical path blocker.

**Testing Strategy**

We're using a chaos testing harness I built that spawns 100 simulated clients with randomized
network partition schedules, generating 10,000 operations per test run. Each run asserts merge
idempotency, commutativity, and final convergence within 500ms of the last network reconnect.
We're targeting zero failures across 10,000 runs before marking this production-ready.
""",
                "scenes": [
                    {
                        "title": "Prototype correctness validation",
                        "stage": "complete",
                        "notes": "All single-client and two-client scenarios passing chaos harness. Merged to staging branch.",
                    },
                    {
                        "title": "Three-way concurrent edit edge cases",
                        "stage": "in_progress",
                        "notes": "17 failing scenarios identified. Working through them in order of reproduction frequency. Theo owns the vector clock tiebreaker fix; I own the stale-snapshot detection logic.",
                    },
                    {
                        "title": "Tombstone GC protocol design",
                        "stage": "in_progress",
                        "notes": "Draft spec written. Waiting on Marcus's team to confirm they can surface the quiescence signal through the v3 API. Retention window set to 30 days pending ops input.",
                    },
                    {
                        "title": "Protocol team v3 API freeze dependency",
                        "stage": "awaiting_data",
                        "notes": "Blocked on protocol team. Marcus said end of week but slipped twice. Need to escalate if not resolved by Friday.",
                    },
                    {
                        "title": "Client-side integration (Electron)",
                        "stage": "planning",
                        "notes": "Ravi Subramanian (contract) will own this once we finalize the merge interface. Estimated 3 weeks. Needs design doc review from me first.",
                    },
                    {
                        "title": "10,000-run chaos harness sign-off",
                        "stage": "planning",
                        "notes": "Final gate before production readiness. Will run after edge cases are resolved and client integration is complete.",
                    },
                ],
            },
            {
                "title": "Sync Protocol v3 Migration",
                "color": "#8b5cf6",
                "notes": """\
The Sync Protocol v3 Migration is a coordinated effort to move all Meridian clients — desktop,
mobile, and browser extension — from the legacy v2 sync protocol to the new v3 protocol that
supports partial sync, delta compression, and conflict-free merge semantics natively.

**Why v3**

The v2 protocol was designed in 2019 when Meridian had roughly 50,000 active users and documents
averaged 40KB. Today we have 2.1 million active users and median document size is 380KB, with a
long tail above 10MB. v2 full-sync on document open is now a meaningful source of latency and
bandwidth cost. v3 introduces range-based partial sync (download only the blocks you need), Zstd
compression at the frame level, and a merge layer that is aware of CRDT semantics — meaning
clients can sync deltas without a full document download on reconnect.

**Migration Phases**

Phase 1 (complete): v3 server deployed behind a feature flag. All new writes are dual-written to
v2 and v3 backends. Read path remains v2. This gave us six weeks of v3 write validation without
customer impact.

Phase 2 (in progress): Desktop client v3 read path enabled for internal employees. We have
~800 internal users on this path now. Monitoring bandwidth reduction (currently seeing 61% reduction
on document open, target was 55%) and latency (p50 down 40%, p99 down 28%, both ahead of targets).

Phase 3 (planned): Progressive rollout to external customers by cohort, starting with customers
on dedicated infrastructure (our enterprise tier) where we have more control over rollback.
10% → 25% → 50% → 100% over six weeks, with automatic rollback triggers if p99 latency regresses
more than 15% or error rate exceeds 0.1%.

Phase 4 (planned): v2 write path deprecation. Once 100% of active clients are on v3 read, we
will sunset v2 writes. Estimated 90 days after Phase 3 completion to allow for offline clients
to sync.

**Backward Compatibility**

v3 documents are readable by v2 clients in degraded mode — they get the full document without
partial sync benefits. We made this choice deliberately to avoid forced upgrades. The migration
is pull-based from the client perspective.

**Metrics and Rollout Tooling**

I've instrumented the server with per-cohort latency histograms (Prometheus), bandwidth counters,
and sync error rates. Rollout is controlled by a LaunchDarkly flag with percentage and cohort
dimensions. On-call runbook updated to cover v3-specific failure modes.
""",
                "scenes": [
                    {
                        "title": "Phase 1 — dual-write validation",
                        "stage": "complete",
                        "notes": "6 weeks complete. All v3 writes validated against v2 baseline. Zero divergence detected.",
                    },
                    {
                        "title": "Phase 2 — internal employee rollout",
                        "stage": "in_progress",
                        "notes": "800 internal users on v3 read path. Bandwidth reduction 61% (target 55%). p99 latency -28%. Holding for 2 more weeks before Phase 3.",
                    },
                    {
                        "title": "Phase 3 rollout plan — enterprise tier first",
                        "stage": "planning",
                        "notes": "Cohort selection script written. LaunchDarkly flag configured. Waiting on Phase 2 stability window to close.",
                    },
                    {
                        "title": "On-call runbook update for v3",
                        "stage": "complete",
                        "notes": "Runbook updated. Two v3-specific alert rules added to PagerDuty. Reviewed by oncall rotation lead.",
                    },
                    {
                        "title": "v2 deprecation plan",
                        "stage": "planning",
                        "notes": "Drafted deprecation notice template. Legal needs to review. Timeline: 90 days post Phase 3 completion.",
                    },
                ],
            },
            {
                "title": "Performance Benchmarking Suite",
                "color": "#a78bfa",
                "notes": """\
The Performance Benchmarking Suite is an internal tooling project to give the Real-Time Sync team
reliable, reproducible, and automated measurements of sync latency, throughput, correctness, and
resilience under realistic network conditions. Before this project, performance analysis was
ad hoc — engineers ran one-off scripts locally, and results weren't comparable across time or
machine configurations.

**Motivation**

During the v3 migration planning phase, we discovered that we had no authoritative baseline for
v2 performance. We were comparing v3 improvements against manually recorded anecdotes. That's not
engineering — it's storytelling. I proposed this benchmarking suite to fix that permanently.

**Tool Choices**

The harness is written in Python (our team's lingua franca), using `asyncio` for concurrent client
simulation. We use `locust` for load generation with a custom Meridian sync client plugin, and
`pytest-benchmark` for microbenchmark regressions on specific codec and merge functions.
Results are stored in a PostgreSQL metrics database (separate from production) and visualized
in Grafana. We chose not to use an external benchmarking SaaS to avoid leaking performance data.

**Test Scenarios**

We currently have eight scenario classes:

1. Cold open — fresh client downloads document from scratch
2. Warm reconnect — client resumes after 60-second network interruption
3. Concurrent editing — N clients simultaneously editing the same document
4. Offline burst — client makes 100 edits offline, reconnects and syncs
5. Large document — 10MB+ documents, stress-testing partial sync
6. High cardinality — workspace with 10,000 documents, testing index performance
7. Network degradation — 200ms RTT, 5% packet loss, jitter simulation via `tc`
8. Tombstone pressure — documents with high deletion ratios, GC stress

**CI Integration**

The suite runs nightly in CI (GitHub Actions, self-hosted runner with dedicated hardware to
minimize variance). Results are committed to the metrics database and compared against a rolling
30-day baseline. If any scenario regresses more than 10% in p99, the CI job fails and pages the
oncall. Pull requests can optionally trigger a focused benchmark run via a `/benchmark` bot
comment.

**Baseline Results (v2, established last month)**

- Cold open p50: 380ms, p99: 1.2s
- Warm reconnect p50: 95ms, p99: 310ms
- Concurrent editing (10 clients) merge time p50: 12ms, p99: 88ms

These are now the reference numbers against which v3 and CRDT engine improvements are measured.
""",
                "scenes": [
                    {
                        "title": "Harness architecture and tooling selection",
                        "stage": "complete",
                        "notes": "Python/locust/pytest-benchmark stack selected. PostgreSQL metrics store deployed. Grafana dashboards live.",
                    },
                    {
                        "title": "Scenario implementation — scenarios 1-5",
                        "stage": "complete",
                        "notes": "Cold open, warm reconnect, concurrent editing, offline burst, large document. All passing and producing stable measurements.",
                    },
                    {
                        "title": "Scenario implementation — scenarios 6-8",
                        "stage": "in_progress",
                        "notes": "High cardinality and network degradation done. Tombstone pressure scenario in draft — waiting on GC protocol to stabilize before finalizing.",
                    },
                    {
                        "title": "CI nightly run integration",
                        "stage": "complete",
                        "notes": "Nightly CI job live. PagerDuty alert rule configured. Baseline committed. First regression alert fired and was a true positive (caught a locust config bug, not a real regression).",
                    },
                    {
                        "title": "PR-level benchmark bot",
                        "stage": "planning",
                        "notes": "/benchmark comment trigger. GitHub Actions workflow drafted. Needs review from DevOps before enabling — concerned about runner contention.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What's the p99 latency on the sync benchmark runs from yesterday?",
                    },
                    {
                        "role": "cairn",
                        "content": "From yesterday's nightly benchmark run (Tuesday, 2026-03-10):\n\n- **Cold open p99:** 1.18s (baseline: 1.2s, -1.7%)\n- **Warm reconnect p99:** 298ms (baseline: 310ms, -3.9%)\n- **Concurrent editing (10 clients) p99:** 91ms (baseline: 88ms, +3.4%)\n\nAll within threshold. The concurrent editing number is slightly elevated — same pattern as Monday. Worth watching but not alarming yet. Want me to note that as a watch item on the benchmarking act?",
                    },
                    {
                        "role": "user",
                        "content": "Yes, flag it. Also — did Marcus's team send anything about the v3 API freeze? I was expecting an update by end of day yesterday.",
                    },
                    {
                        "role": "cairn",
                        "content": "I don't see any messages from Marcus or the protocol team in your recent activity. The blocker scene on the CRDT act is still in awaiting_data.\n\nWant me to draft a follow-up message to Marcus? I can frame it around the impact on the CRDT integration timeline.",
                    },
                    {
                        "role": "user",
                        "content": "Yeah, draft something. Keep it direct, not passive-aggressive. We're blocked and I need a date.",
                    },
                    {
                        "role": "cairn",
                        "content": "Draft:\n\n---\n\nHey Marcus — following up on the v3 API freeze timeline. We're currently blocked on the CRDT integration layer: specifically, we need the quiescence signal endpoint to be in the frozen surface before we can finalize the tombstone GC protocol design.\n\nCan you give me a firm date? Even a \"not before X\" would help us plan. If there are open questions on our side that are holding things up, I want to know.\n\n— Priya\n\n---\n\nWant me to adjust the tone or add anything?",
                    },
                    {
                        "role": "user",
                        "content": "That works. Send it as a tracked follow-up — I want Cairn to remind me if I don't hear back by Friday.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted. I've set a reminder for Friday at 9am: if the protocol team API freeze blocker scene is still in awaiting_data, I'll surface it at the top of your morning briefing. The draft is saved if you want to copy it into your email client.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I need to track a new blocker. The Electron client integration for the CRDT engine can't start until Ravi reviews the merge interface design doc. I sent it to him Monday but haven't heard back.",
                    },
                    {
                        "role": "cairn",
                        "content": "Got it. I'm adding a waiting-on to the CRDT act: waiting on Ravi Subramanian to review the merge interface design doc, sent Monday March 9. The client-side integration scene is already in planning — I'll link this as a dependency blocker.\n\nHow long do you want to wait before escalating?",
                    },
                    {
                        "role": "user",
                        "content": "He's a contractor so I don't want to be annoying. Give it until Thursday.",
                    },
                    {
                        "role": "cairn",
                        "content": "Thursday reminder set. If the scene is still blocked Thursday morning, I'll prompt you with the option to send a check-in. I'll keep the language neutral — just a status check, not pressure.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What's on my calendar tomorrow?",
                    },
                    {
                        "role": "cairn",
                        "content": "Tomorrow (Wednesday, March 11):\n\n- **9:00am** — Sync team standup (async, 15-min window to post update)\n- **10:30am** — CRDT design review with Theo and Ravi\n- **2:00pm** — 1:1 with Marcus (Engineering Manager)\n- **4:00pm** — No more meetings\n\nThe CRDT design review at 10:30 is the substantive one. Based on current act status, the most useful thing to bring is the three-way concurrent edit edge case list and the tombstone GC protocol draft. Want me to pull those into a summary for you?",
                    },
                    {
                        "role": "user",
                        "content": "Yes. Just the open questions, not a full recap.",
                    },
                    {
                        "role": "cairn",
                        "content": "**Open questions for CRDT design review (2026-03-11 10:30am):**\n\n1. Three-way concurrent edits: should stale-snapshot detection trigger a full re-sync or an incremental reconciliation pass? (I lean incremental — Theo disagrees)\n2. Tombstone GC quiescence signal: does the protocol team's v3 API actually expose per-peer acknowledgment, or only global quiescence? This changes the GC algorithm substantially.\n3. Retention window: 30 days is a guess. Do we have data on how long enterprise clients typically stay offline?\n\nAnything to add before the meeting?",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Priya prefers async standups over synchronous ones. She finds synchronous standups interruptive to deep work and has set her calendar to block morning hours for focused engineering.",
                "entity_type": "insight",
                "entity_data": {"subject": "Priya Chandrasekaran", "preference": "async standups", "context": "work rhythm"},
            },
            {
                "narrative": "The CRDT Conflict Resolution Engine is blocked on the protocol team's v3 API freeze. Marcus Chen's team has missed two deadline commitments. Priya needs a firm date before she can finalize the tombstone GC protocol.",
                "entity_type": "waiting_on",
                "entity_data": {"waiting_on": "Marcus Chen / protocol team", "for": "v3 API freeze date", "project": "CRDT Conflict Resolution Engine", "slipped_count": 2},
            },
            {
                "narrative": "Priya's 1:1 with her manager Marcus is every Wednesday at 2pm. She uses it to surface blockers and review engineering priorities.",
                "entity_type": "person",
                "entity_data": {"name": "Marcus Chen", "role": "Engineering Manager", "recurring_meeting": "Wednesday 2:00pm", "meeting_type": "1:1"},
            },
            {
                "narrative": "Ravi Subramanian is a contractor handling client-side CRDT integration in the Electron app. Priya sent him the merge interface design doc on Monday March 9. Waiting on review before client integration can start.",
                "entity_type": "waiting_on",
                "entity_data": {"waiting_on": "Ravi Subramanian", "for": "merge interface design doc review", "sent_date": "2026-03-09", "escalate_by": "2026-03-12"},
            },
            {
                "narrative": "Theo Nakamura is a distributed systems engineer on Priya's team. He owns the vector clock tiebreaker fix in the CRDT engine. He and Priya disagree on whether stale-snapshot detection should trigger full re-sync or incremental reconciliation.",
                "entity_type": "person",
                "entity_data": {"name": "Theo Nakamura", "role": "Distributed Systems Engineer", "disagreement": "stale-snapshot recovery strategy"},
            },
            {
                "narrative": "The concurrent editing p99 benchmark has been slightly elevated (88ms baseline, running at 91ms) for two consecutive nightly runs. Not yet at alert threshold but worth monitoring.",
                "entity_type": "insight",
                "entity_data": {"metric": "concurrent editing p99", "baseline_ms": 88, "current_ms": 91, "trend": "elevated, 2 days", "status": "watch"},
            },
            {
                "narrative": "Priya is working through the TLA+ specification book in her personal time. She's interested in formal verification as a complement to chaos testing for CRDT correctness guarantees.",
                "entity_type": "insight",
                "entity_data": {"subject": "Priya Chandrasekaran", "interest": "TLA+ formal verification", "context": "personal learning"},
            },
        ],
        "emails": [],
        "calendar_events": [],
    },

    {
        "id": "derek_okafor",
        "identity": {
            "full_name": "Derek Okafor",
            "department": "Engineering",
            "title": "Junior Software Engineer",
        },
        "personality": "anxious",
        "your_story": """\
# Derek Okafor — Junior Software Engineer, Frontend Platform

I'm a junior software engineer on the Frontend Platform team at Meridian Labs. This is my first
job out of college — I graduated from UT Austin eighteen months ago with a BS in Computer Science,
and I've been at Meridian for two years now. I'm 24 years old, Nigerian-American, and I grew up
in Austin where I still live.

My day-to-day work is in React and TypeScript, building and maintaining the component library that
the rest of Meridian's frontend teams consume. I also own a slice of the Storybook migration and
I'm currently leading (which feels like a big word for what I'm doing) the accessibility audit of
the component library.

Honestly, I'm still figuring out how to be an engineer. I know my fundamentals are solid — I
did well in school and I can work through hard problems — but I get anxious about production
things. The idea that something I write could break for hundreds of thousands of users is something
I think about a lot. I double-check PRs before I send them. I read deploy freeze schedules before
I merge anything. I ask for reviews from more senior engineers even when it's probably not
necessary.

My mentor is Priya Chandrasekaran from the Sync team. She's been really patient with me about the
whole "just ship it" mentality I haven't quite internalized yet. We have a learning session every
Friday afternoon that I genuinely look forward to — she's been walking me through distributed
systems concepts that aren't directly related to my job but are making me a better engineer.

Outside of work I play pickup basketball and I'm slowly learning to cook. I'm trying to get
better at the parts of software engineering that aren't just writing code — communication,
prioritization, knowing when something is good enough.
""",
        "acts": [
            {
                "title": "Component Library Accessibility Audit",
                "color": "#ef4444",
                "notes": """\
The Component Library Accessibility Audit is my first solo project at Meridian with real
organizational visibility. The goal is to bring our shared component library into full
WCAG 2.1 AA compliance — we had a customer complaint from a major enterprise account whose
accessibility team flagged that several of our form components weren't keyboard navigable,
and it escalated to the point where leadership asked Frontend Platform to conduct a formal audit.

**Scope**

The component library has 87 components. My initial assessment triaged them into three buckets:
- High risk (form controls, modals, navigation): 22 components
- Medium risk (data display, feedback): 34 components
- Low risk (layout, typography): 31 components

I started with the high-risk bucket.

**Findings So Far**

I've audited 19 of the 22 high-risk components. Findings include:
- 8 components missing `aria-label` or `aria-labelledby` on interactive elements
- 4 components with non-descriptive focus states (either invisible or using only color)
- 3 modal components that don't trap focus (keyboard users can tab behind the modal)
- 2 data table components that don't announce sort state to screen readers
- 1 component with a completely non-functional keyboard interaction path

The focus trap issues in modals are the most urgent — they're a genuine barrier for screen reader
users, not just a technical violation.

**Remediation Plan**

I'm filing GitHub issues for each finding, labeling them by severity (critical/major/minor) and
component. For critical findings, I'm submitting the fix in the same PR as the audit note. For
major and minor findings, I'm creating a remediation milestone for Q2.

**Tools**

I'm using axe-core for automated scanning (catches about 30-40% of issues), Chrome DevTools
accessibility tree inspection, and manual keyboard-only navigation testing. I wanted to do NVDA
screen reader testing on Windows but I don't have a Windows machine — I've been using a shared
QA machine for two hours a week, which feels inadequate. I've asked my manager Leena if we can
get a dedicated Windows VM for accessibility testing.

**Timeline Anxiety**

The customer account that filed the complaint has a follow-up review scheduled for the end of Q2.
My manager said we need to show meaningful progress by then. I'm worried the medium-risk components
are going to take longer than I've estimated — I keep finding more issues than I expect once I
start testing manually. I've been padding my estimates but I'm not sure I've padded them enough.
""",
                "scenes": [
                    {
                        "title": "High-risk component audit (22 components)",
                        "stage": "in_progress",
                        "notes": "19 of 22 audited. 3 remaining: DatePicker, RichTextEditor, ComboBox. These are the most complex — saving them for when I have a long uninterrupted block.",
                    },
                    {
                        "title": "Critical findings remediation — modal focus traps",
                        "stage": "in_progress",
                        "notes": "3 modal components need focus trap implementation. I've fixed one (ConfirmDialog). Working on AlertModal next. SlideOver modal is the hardest — has nested focusable elements.",
                    },
                    {
                        "title": "Medium-risk component audit (34 components)",
                        "stage": "planning",
                        "notes": "Haven't started yet. Nervous about the timeline. Will start after high-risk audit completes.",
                    },
                    {
                        "title": "Windows VM for NVDA testing",
                        "stage": "awaiting_data",
                        "notes": "Requested from Leena. Haven't heard back. Will follow up in our next 1:1.",
                    },
                    {
                        "title": "Q2 remediation milestone and customer update",
                        "stage": "planning",
                        "notes": "Need to write a summary document for the customer account. Leena said she'll review it before it goes out. Due before end of April.",
                    },
                ],
            },
            {
                "title": "Storybook Migration",
                "color": "#f97316",
                "notes": """\
The Storybook Migration project is about moving our component library documentation from a
hand-written Markdown site (which nobody reads) to Storybook 8, where developers can interact
with components directly, see their props and variants, and run visual regression tests against
them. This was assigned to me as a good "ownership" project for a junior engineer — it's
real, ships to production, but the blast radius is relatively small if I mess something up.

**What I've Done**

I got Storybook 8 running locally in the first two weeks. That part was mostly following the
docs. The harder part has been writing good stories. A "story" in Storybook is a code example
showing a specific component state. Our component library has a lot of undocumented implicit
states — things where the component behaves differently based on a combination of props that
nobody wrote down anywhere. I've been reverse-engineering these by reading source code and, when
confused, asking Priya or my teammate Kenji.

**Current Status**

I've written stories for 31 of 87 components. The first 20 were slow — I was figuring out the
patterns. The last 11 have been faster. I have a template now that I copy for each component type
(form control, display, feedback, layout) which speeds things up.

**Visual Regression Testing**

I set up Chromatic for visual regression testing. Every PR that touches a component will now
run a visual diff against the baseline. This was harder than I expected — Chromatic's GitHub
Actions integration kept failing because of a CORS issue with our internal CDN that I spent
two days debugging before posting to the team Slack. Kenji spotted the fix in ten minutes. That
was a humbling experience but also kind of a relief — I wasn't doing something fundamentally wrong,
it was a legitimately tricky infrastructure issue.

**Learning Curve**

Storybook has a lot of surface area. I've had to learn about decorators, args tables, play
functions (for interaction testing), and the Storybook addon ecosystem. It's been genuinely
educational. I think I understand component APIs much better now because writing a good story
forces you to understand every prop.

**Blockers**

The main blocker right now is that some of our older components are tightly coupled to a
global Redux store, which means I can't render them in Storybook without mocking the entire
store. I've been working around it but it's inconsistent and fragile. The right fix is to
decouple those components — but that's a bigger refactor than this project scoped for.
I asked my manager if I should flag this as technical debt or just work around it.
""",
                "scenes": [
                    {
                        "title": "Storybook 8 setup and configuration",
                        "stage": "complete",
                        "notes": "Storybook running locally and in CI. Configuration includes Tailwind, TypeScript, and our design token system.",
                    },
                    {
                        "title": "Story writing — batch 1 (31 of 87 components)",
                        "stage": "in_progress",
                        "notes": "31 done. Template established for 4 component categories. Pace improving. Target: 10 stories per week.",
                    },
                    {
                        "title": "Chromatic visual regression setup",
                        "stage": "complete",
                        "notes": "Live in CI. GitHub PR checks passing. Baseline established. One flaky test on the Tooltip component — timing-sensitive, needs a proper fix.",
                    },
                    {
                        "title": "Redux-coupled component workaround strategy",
                        "stage": "awaiting_data",
                        "notes": "Asked Leena whether to flag as tech debt or work around it. Waiting for her input before proceeding.",
                    },
                    {
                        "title": "Remaining 56 components",
                        "stage": "planning",
                        "notes": "Will accelerate once the accessible components are also done — don't want to write stories for components that are about to change significantly.",
                    },
                ],
            },
            {
                "title": "Dark Mode Implementation",
                "color": "#64748b",
                "notes": """\
Dark mode is a Q3 commitment Meridian made to enterprise customers after it appeared repeatedly
in NPS feedback. The Frontend Platform team owns the implementation, and this project landed
on my plate because I've been building familiarity with our design token system through the
Storybook work. That logic makes sense to me even if the responsibility feels large.

**Approach**

We're not doing a "flip a class on the body" hack. We're doing a proper design token system
migration: every color, shadow, and border value in the component library will be expressed as
a CSS custom property that resolves to different values in light and dark contexts. The design
team has delivered the token set in Figma and a Tokens Studio JSON export.

I'm the implementer, not the designer, so my job is:
1. Ingest the token JSON into our build pipeline (Style Dictionary transform)
2. Replace hardcoded color values in all components with token references
3. Wire the theme switcher (the design team owns the UI for this) to `data-theme` attribute
   toggling on the root element
4. Test across browsers and ensure no visual regressions in either theme

**Design System Coordination**

This requires close coordination with Maya on the design team, who owns the Figma tokens and
will be the source of truth for any ambiguous token values. We have a shared Notion doc where
I log questions and she answers them. There have been about 20 clarifying questions so far —
things like "should interactive-surface-hover be the same in dark mode or slightly more
elevated?" The coordination is slower than I'd like but she's juggling multiple projects.

**Edge Cases**

The most problematic edge cases I've found:
- SVG icons with hardcoded fill colors (not token-based) — need manual fix for each
- Third-party embedded components (our rich text editor uses a library with its own CSS) —
  dark mode may not apply there without heavy overrides
- User-uploaded images appear in document bodies — no inversion, they stay as-is (correct behavior,
  but I need to confirm with design)

**Cross-Browser Testing**

Chrome and Firefox are solid. Safari has a quirk with CSS custom property inheritance in shadow
DOM that I'm still debugging. I'm also planning to test on Edge because several enterprise
customers use it as their default.

**Timeline**

This is a Q3 delivery so I have more runway than the accessibility audit. Still, I want to
start the component migration work in Q2 so that Q3 isn't a crunch. The ambiguity in some
token values is the thing that could eat my timeline.
""",
                "scenes": [
                    {
                        "title": "Token system ingestion via Style Dictionary",
                        "stage": "complete",
                        "notes": "Style Dictionary pipeline consuming Tokens Studio JSON. CSS custom properties generated and bundled. Light theme matches Figma exactly.",
                    },
                    {
                        "title": "Dark theme token values — design review",
                        "stage": "in_progress",
                        "notes": "20 questions logged in Notion, 14 answered. 6 still pending from Maya. Can't finalize dark token values until resolved.",
                    },
                    {
                        "title": "Component migration — replace hardcoded colors",
                        "stage": "planning",
                        "notes": "Not started. Will begin after dark token values are finalized. Estimate 4-6 weeks for full component library.",
                    },
                    {
                        "title": "SVG icon audit — hardcoded fill colors",
                        "stage": "planning",
                        "notes": "Script to identify SVGs with hardcoded fills written. 47 icons flagged. Remediation not yet started.",
                    },
                    {
                        "title": "Safari shadow DOM CSS custom property bug",
                        "stage": "in_progress",
                        "notes": "Reproducing consistently. Opened a bug. May need a Safari-specific workaround. Asked Kenji to take a look.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Hey Cairn, I'm worried I might have broken the build with my last PR. Can you check if there's anything on my calendar about the deploy freeze?",
                    },
                    {
                        "role": "cairn",
                        "content": "The current deploy freeze runs through midnight tonight (Wednesday, March 11). Your last merge was this afternoon at 2:47pm — that's during the freeze window, but deploy freezes at Meridian apply to production deploys, not merges to the development branch. You'd need to check whether your PR targeted main or the release branch.\n\nIs there a specific build failure you're seeing, or is this more of a 'I think I might have done something wrong' feeling?",
                    },
                    {
                        "role": "user",
                        "content": "The latter. The CI went red but I think it was already red before my PR? I don't know. I'm probably being paranoid.",
                    },
                    {
                        "role": "cairn",
                        "content": "That's worth verifying rather than worrying about. The fastest check: look at the CI history on main and see if the red started before or after your commit. If it was already failing, you're in the clear.\n\nIf you want, I can note this as a reminder to check CI status before merging in the future — not as a criticism, just as a habit that reduces this kind of anxiety.",
                    },
                    {
                        "role": "user",
                        "content": "Yes please. And yeah, I checked — it was already failing. I'm fine.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted: check CI status on main before merging, not just the PR checks. I'll surface this as a reminder the next time you mention a pending merge.\n\nGlad you're fine. That particular anxiety is pretty common for engineers early in their career — it gets quieter with time.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I have so many tasks right now and I don't know what to focus on. The accessibility audit, the Storybook work, the dark mode stuff. Where do I even start today?",
                    },
                    {
                        "role": "cairn",
                        "content": "Let me help you sort that out. Based on your current acts:\n\n**Highest urgency:**\n- Accessibility audit — the ConfirmDialog focus trap fix is in progress and you have a customer-facing deadline. The remaining 3 high-risk components (DatePicker, RichTextEditor, ComboBox) need to be audited before you can call that phase done.\n\n**Second priority:**\n- Storybook — you're in a steady state with a clear pace (10/week). No deadline pressure right now.\n\n**Lowest urgency:**\n- Dark mode — Q3 delivery, 6 pending design questions blocking next steps anyway.\n\nMy suggestion: block the first 2-3 hours this morning for the AlertModal focus trap fix (continuation of yesterday's work), then do one Storybook story as a palette cleanser after lunch. The dark mode questions can wait until Maya responds.\n\nDoes that feel right, or is there something I'm missing about today?",
                    },
                    {
                        "role": "user",
                        "content": "That's actually really helpful. Yeah, I'll do the AlertModal this morning. I keep avoiding it because it's the harder one but that's probably exactly why I should do it first.",
                    },
                    {
                        "role": "cairn",
                        "content": "That instinct is right — it's called eating the frog. Hardest thing first while your brain is fresh. Good luck with AlertModal. Let me know if you want to talk through the focus trap implementation before you start.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "My learning session with Priya is today right?",
                    },
                    {
                        "role": "cairn",
                        "content": "Yes — Friday at 3pm, your standing learning session with Priya Chandrasekaran. About 4 hours from now.\n\nAnything specific you want to prepare or topics you want to suggest? Last session you were covering vector clocks — do you want to continue there or pivot to something more directly relevant to your current work?",
                    },
                    {
                        "role": "user",
                        "content": "I want to ask her about the Redux coupling problem in Storybook. She'll probably have a good take on the architectural side.",
                    },
                    {
                        "role": "cairn",
                        "content": "Good instinct — that's exactly the kind of structural question she's well-positioned to help with. You might also frame it as: 'should I refactor the components or work around the coupling in stories?' so she can help you decide, not just explain the technical options.\n\nWant me to add a reminder at 2:45 to wrap up whatever you're working on so you're not rushing into the session?",
                    },
                    {
                        "role": "user",
                        "content": "Yes please.",
                    },
                    {
                        "role": "cairn",
                        "content": "Reminder set for 2:45pm: wrap up and prepare for learning session with Priya.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Derek gets overwhelmed by large PRs and tasks. He consistently produces better work when changes are broken into small, incremental steps. He's aware of this and is actively working on it.",
                "entity_type": "insight",
                "entity_data": {"subject": "Derek Okafor", "pattern": "overwhelm with large scope", "mitigation": "incremental small changes"},
            },
            {
                "narrative": "Priya Chandrasekaran is Derek's mentor. They have a standing learning session every Friday at 3pm. Priya has been covering distributed systems concepts with Derek.",
                "entity_type": "person",
                "entity_data": {"name": "Priya Chandrasekaran", "role": "mentor", "recurring_meeting": "Friday 3:00pm", "topic": "distributed systems"},
            },
            {
                "narrative": "Derek's manager is Leena. Derek has asked Leena two open questions: (1) whether to get a Windows VM for NVDA accessibility testing, and (2) whether to flag Redux coupling in Storybook as tech debt. Both are awaiting response.",
                "entity_type": "waiting_on",
                "entity_data": {"waiting_on": "Leena", "open_questions": ["Windows VM for NVDA testing", "Redux coupling tech debt strategy"]},
            },
            {
                "narrative": "Derek has a habit of checking CI after merging rather than before. A reminder was noted to check CI status on main before merging, to avoid anxiety about whether failures were pre-existing.",
                "entity_type": "insight",
                "entity_data": {"subject": "Derek Okafor", "habit_to_build": "check CI on main before merging"},
            },
            {
                "narrative": "Kenji is a more senior teammate on the Frontend Platform team. Derek turns to Kenji for infrastructure questions and debugging help. Kenji spotted a CORS fix in 10 minutes that Derek had spent 2 days on.",
                "entity_type": "person",
                "entity_data": {"name": "Kenji", "role": "senior teammate, Frontend Platform", "context": "go-to for infra/debugging questions"},
            },
            {
                "narrative": "The accessibility audit has a customer-facing deadline tied to a major enterprise account's Q2 review. Leena confirmed meaningful progress needs to be visible by end of Q2.",
                "entity_type": "task",
                "entity_data": {"project": "Component Library Accessibility Audit", "deadline": "end of Q2", "driver": "enterprise customer complaint", "owner": "Derek Okafor"},
            },
        ],
        "emails": [],
        "calendar_events": [],
    },

    {
        "id": "elena_vasquez",
        "identity": {
            "full_name": "Elena Vasquez",
            "department": "Marketing",
            "title": "Content Marketing Director",
        },
        "personality": "creative",
        "your_story": """\
# Elena Vasquez — Content Marketing Director

I run content marketing at Meridian Labs, and I've been doing this kind of work for eighteen years
— which still surprises me to say out loud. I manage a team of six writers and two video producers,
and collectively we own Meridian's voice across every written and visual channel: the blog, the
webinar program, the case study library, social media, and increasingly our developer community
presence.

Before Meridian, I spent five years at HubSpot leading their SMB content function, and before that
I was at a sequence of mid-size B2B companies where I basically built content programs from scratch.
I've done this enough times that I know the shape of what works — I just have to resist the urge
to do everything at once, which is my most consistent failure mode.

I'm Mexican-American, grew up in Chicago, and still live there. I think in stories and metaphors.
My first instinct when someone gives me a product feature is to ask "who's the protagonist of this
story, and what do they want?" That lens has served me well in B2B content, which tends to be
written for companies and not for people.

My team is genuinely understaffed right now — we have two writer openings we've been trying to
fill since January, and the gap is showing in our capacity. I'm doing too much writing myself,
which means I'm doing less editing, strategy, and mentoring than I should be. That's a solvable
problem but it requires headcount I don't have yet.

My creative process: I do my best conceptual work in the morning, ideally before I've looked at
Slack. Afternoons are for the operational stuff — briefs, reviews, stakeholder meetings. I try to
protect at least two mornings a week for thinking, but meetings keep eating them.
""",
        "acts": [
            {
                "title": "Q2 Product Launch Campaign",
                "color": "#ec4899",
                "notes": """\
The Q2 Product Launch Campaign is the most complex content initiative on my plate this year. We're
launching three AI-powered features in late April — Smart Summarization, Meeting Transcription, and
AI-Assisted Commenting — and the content program needs to support awareness, education, and
conversion across every channel simultaneously.

**Campaign Architecture**

The campaign has five content streams:

1. **Blog series** — Six posts published over eight weeks. Topics: "The future of meeting notes"
(thought leadership, published at launch), three how-to posts featuring the new features
specifically, one customer story, one post on our responsible AI approach (important for enterprise
trust). Two of the six posts are written; four are in various stages of draft.

2. **Webinar program** — A live launch webinar with product demos and a customer panel (April 29),
followed by two on-demand educational webinars in May covering specific use cases. The launch
webinar is confirmed; speakers are locked (two customers confirmed, one still negotiating). The
on-demand webinars are planned but not yet briefed.

3. **Case studies** — Three new case studies featuring AI feature beta customers. One complete,
one in final review, one just started. The third case study customer (a fintech company) is slow
to respond to our interview requests, which is putting us behind.

4. **Social strategy** — LinkedIn-first approach, with threads expanding on each blog post plus
a dedicated launch day social push. My social media manager Sophie is running this. Launch day
content calendar is drafted; pre-launch teaser content is in production.

5. **Press outreach** — I'm coordinating with our PR agency on a product news angle. They've
pitched three trade outlets; two have expressed interest. We're not doing a traditional press
release — instead we're doing a "briefing under embargo" approach with a two-week window before
the public launch.

**Creative Brief Status**

The master creative brief is done and has been reviewed by the product team and our CMO. Visual
direction is set (gradient aesthetic, warm colors contrasting with Meridian's usual cool palette
to signal "this is different and energizing"). Brand has signed off. All writers have been briefed.

**What I'm Worried About**

The fintech case study customer going dark is a real risk — if we can't get the interview done by
March 20, we'll miss the copy deadline for the launch. I have a backup customer in mind (a
healthcare tech company), but they haven't used the AI features as long, so the story is less
developed. I'm going to make a call on this by Friday.

Also: I don't have enough writers. One of my current contractors is only available through March,
and I'm relying on her for two of the blog posts. If she finishes and I don't have a replacement,
I'll be writing those myself, which is fine but not ideal.
""",
                "scenes": [
                    {
                        "title": "Master creative brief",
                        "stage": "complete",
                        "notes": "Approved by product, CMO, and brand. Visual direction set. All writers briefed.",
                    },
                    {
                        "title": "Blog series — 6 posts",
                        "stage": "in_progress",
                        "notes": "2 published, 1 in final review, 2 in draft, 1 not started. Contractor finishing 2 of the drafts through end of March.",
                    },
                    {
                        "title": "Launch webinar (April 29)",
                        "stage": "in_progress",
                        "notes": "Confirmed. 2 of 3 customer speakers locked. Deck in progress. Third speaker still negotiating.",
                    },
                    {
                        "title": "Case studies — 3 new",
                        "stage": "in_progress",
                        "notes": "1 complete. 1 in final review. 1 (fintech customer) behind — interview not yet scheduled. Decision due Friday on backup customer.",
                    },
                    {
                        "title": "Press outreach — embargo briefings",
                        "stage": "in_progress",
                        "notes": "PR agency running. 3 pitches sent, 2 interested. Embargo window 2 weeks before launch.",
                    },
                    {
                        "title": "Social calendar — launch day and pre-launch",
                        "stage": "in_progress",
                        "notes": "Launch day content drafted. Pre-launch teaser in production. Sophie owns execution.",
                    },
                ],
            },
            {
                "title": "Developer Community Program",
                "color": "#d946ef",
                "notes": """\
The Developer Community Program is a newer initiative — it grew out of a realization six months ago
that Meridian had almost no presence among developers, even though developers are a critical buying
influence at the enterprise accounts we target. Engineers evaluate tools, recommend integrations,
and block or unblock deals. We were invisible to them.

**Program Pillars**

The program has four interconnected pillars:

1. **Technical blog** — A dedicated "engineering" section of our blog, separate from the main
content marketing feed, featuring deep technical posts written by Meridian engineers (and sometimes
by members of the developer community). We've published six posts so far. Early signal is
positive — our best-performing developer post (on our sync protocol design) got 3x the organic
traffic of a typical marketing post. I'm working with the engineering team to build a sustainable
cadence of one post per month. The challenge is that engineers need a lot of hand-holding through
the editorial process — they're great at depth, not at narrative.

2. **Conference sponsorships** — We're sponsoring three conferences this year: a distributed
systems conference in June, a TypeScript/React conference in September, and a general developer
conference in October. For each, I'm trying to create content assets that work in the conference
context (talks, workshops) and extend to web content afterward. We have a submitted talk proposal
for the distributed systems conference — decision expected in April.

3. **Open source contributions** — Meridian's engineering team has released two open-source
libraries related to our sync protocol. I'm responsible for the "marketing" of those releases:
documentation landing pages, release announcements, community engagement. The second library was
released last month; the announcement post got 800 GitHub stars in the first week, which exceeded
our expectations.

4. **Ambassador program** — We're building a small program of 10-15 external developers who
regularly use Meridian's API and are willing to create content, speak at meetups, and provide
community feedback in exchange for early access, swag, and modest honoraria. We're in the
recruitment phase: 6 candidates identified, 3 conversations had, 0 commitments yet.

**Metrics**

Developer community metrics are harder to tie to pipeline than traditional content marketing. I'm
tracking: developer blog organic traffic, GitHub stars on open-source repos, conference attendee
interactions, and ambassador pipeline. I want to establish a metric for API trial signups that
we can attribute to community programs, but I haven't figured out the attribution model yet.
Jordan Park in marketing analytics is supposed to help me with this.

**What Excites Me**

This program has more creative latitude than almost anything else I've worked on. The developer
audience responds to authenticity and technical depth, not marketing polish. That's a permission
structure I find energizing.
""",
                "scenes": [
                    {
                        "title": "Technical blog cadence — 1 post/month",
                        "stage": "in_progress",
                        "notes": "6 posts published. Working with engineering to build sustainable pipeline. Monthly editorial calendar established. April post topic selected (CRDT design).",
                    },
                    {
                        "title": "Conference sponsorships — 3 events",
                        "stage": "in_progress",
                        "notes": "All 3 sponsored. Talk proposal submitted for distributed systems conference. Decision April.",
                    },
                    {
                        "title": "Open source announcement — library 2",
                        "stage": "complete",
                        "notes": "Published. 800 GitHub stars first week. Exceeded expectations. Post-mortem written for future OS releases.",
                    },
                    {
                        "title": "Ambassador program — recruitment phase",
                        "stage": "in_progress",
                        "notes": "6 candidates identified, 3 conversations had, 0 commitments. Target: 10 ambassadors by end of Q2.",
                    },
                    {
                        "title": "API trial attribution model",
                        "stage": "awaiting_data",
                        "notes": "Need Jordan Park's help to define attribution. Haven't had a formal working session yet. Should set one up.",
                    },
                ],
            },
            {
                "title": "Brand Voice Guidelines v3",
                "color": "#f43f5e",
                "notes": """\
The Brand Voice Guidelines v3 project is an overhaul of Meridian's documented content standards —
the playbook that every writer, internal or external, is supposed to use to ensure Meridian sounds
like itself. The last version (v2) was written three years ago, before Meridian moved upmarket into
enterprise, before we added a developer audience, and before AI content became a category anyone
had to think about. It needs a serious rewrite.

**Why Now**

Two things pushed this to the front of my agenda. First, we've been onboarding a lot of contract
writers for the Q2 campaign, and I'm spending too much time in editorial review catching voice
inconsistencies that a good guidelines doc would have prevented. Second, I want Meridian to have
a documented position on AI-generated content — both for external communication and for internal
policy — and that needs to live in the brand voice guidelines.

**Scope**

v3 covers:
- **Tone guidelines** — The adjectives we use to describe Meridian's voice (thoughtful,
  direct, technically credible, warm but not casual), with examples and anti-examples for each
- **Persona messaging matrix** — How the voice adapts for our three main audiences: business
  buyers, IT administrators, and developers. Each persona has different concerns and responds
  to different value propositions.
- **AI content policy** — Where AI writing tools are acceptable (first drafts, research summaries,
  SEO outlines) and where they're not (customer quotes, case study narratives, executive
  bylines). With rationale, not just rules.
- **Content templates** — Standard templates for blog posts, case studies, emails, and social
  content with embedded voice guidance
- **Inclusive language guide** — Additions to the existing Meridian style guide specifically
  covering accessibility (alt text, plain language) and inclusive terminology

**Process**

I'm doing stakeholder interviews with ten internal stakeholders across sales, product, customer
success, and engineering before writing anything. The goal is to understand where they feel
Meridian's current voice fails them — what does it say when they'd prefer it to stay quiet, what
does it fail to say? I've completed six of ten interviews. The most interesting feedback so far
has come from the sales team, who feel that Meridian's content is too educational and not
commercially direct enough.

I'm also doing a competitive voice analysis — reading six months of content from our top five
competitors and cataloging what they do with tone, structure, and emphasis. This is tedious but
useful. I've finished three of five.

**Timeline**

Draft v3 by end of April. Internal review in May. Publish (internally, on the content wiki) in
June. Roll out through a training session for the writing team and a briefing for key stakeholders
in July.
""",
                "scenes": [
                    {
                        "title": "Stakeholder interviews (10 internal)",
                        "stage": "in_progress",
                        "notes": "6 of 10 complete. Sales feedback: content too educational, not commercially direct. Remaining: product, CS, engineering leads.",
                    },
                    {
                        "title": "Competitive voice analysis (5 competitors)",
                        "stage": "in_progress",
                        "notes": "3 of 5 complete. Key finding so far: competitors lean heavily on 'effortless' — we should differentiate on 'thoughtful' and 'earned simplicity'.",
                    },
                    {
                        "title": "v3 draft — tone guidelines and persona matrix",
                        "stage": "planning",
                        "notes": "Will start after interviews complete. Expecting to draft in early April.",
                    },
                    {
                        "title": "AI content policy section",
                        "stage": "planning",
                        "notes": "Need to align with legal and HR before drafting. Will set up a 30-min working session.",
                    },
                    {
                        "title": "Internal review and publication",
                        "stage": "planning",
                        "notes": "Target: published on content wiki by end of June. Training session for writing team in July.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Oh! I just had an idea — what if we tied the developer community launch to the Q2 campaign? Like a developer track at the webinar? Also, when's my next meeting?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your next meeting is in 47 minutes: 2:00pm, Q2 campaign sync with Sophie and the PR agency.\n\nOn the idea — a developer track at the April 29 launch webinar is interesting. The risk is that the webinar is already scoped for a business buyer audience, and the two audiences have pretty different expectations: one wants to see outcomes and ROI, the other wants to see how things work under the hood. Trying to serve both in one event often means serving neither well.\n\nAlternative framing: what if the developer community content ran as a *follow-up* to the launch webinar, not concurrent? A technical deep-dive webinar in May specifically for developers and API consumers. That preserves the launch narrative for the main webinar and gives developers a reason to stay engaged post-launch.\n\nWant me to capture this in the developer community act as an idea to develop?",
                    },
                    {
                        "role": "user",
                        "content": "Yes, capture it. And yes, you're right about the audience problem — I always fall into the trap of wanting everything to connect to everything. The May follow-up is actually cleaner. What would we call it?",
                    },
                    {
                        "role": "cairn",
                        "content": "A few name directions:\n\n- **Under the Hood** — Developer deep-dive webinar series (positions as ongoing, not one-off)\n- **Built on Meridian** — API and integration focused\n- **Sync Deep Dive** — Technical, specific to the sync protocol/AI features\n\n'Under the Hood' has the most reusability if you want to make it a recurring developer webinar. Captures it in the developer community act now — topic: technical deep-dive webinar, May timing, potential series name 'Under the Hood.' You can refine it before your 2pm meeting if you want to bring it up.",
                    },
                    {
                        "role": "user",
                        "content": "I love 'Under the Hood.' Let's go with that. Add it to the developer community act as a planned scene.",
                    },
                    {
                        "role": "cairn",
                        "content": "Added: 'Under the Hood developer webinar — May' to the Developer Community Program act, stage planning. Notes include the series framing and the connection to the Q2 launch campaign as a deliberate follow-up, not a concurrent event.\n\nYou've got 40 minutes before your 2pm. Anything you want to prep for that meeting?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "The fintech case study customer hasn't responded in two weeks. I think we need to go with the backup. Can you remind me what the backup situation is?",
                    },
                    {
                        "role": "cairn",
                        "content": "Your backup customer for the third case study is the healthcare tech company — I have a note that they've been using the AI features for a shorter period, so the story isn't as developed as the fintech one would have been.\n\nYou set a decision deadline of this Friday for whether to switch. Today is Wednesday. If you go with the backup, do you know who the contact is and whether they'd be available for an interview on short notice?",
                    },
                    {
                        "role": "user",
                        "content": "Yes — Fatima at Meridian's CS team manages that account. She'd know. Can you add a task to reach out to Fatima today?",
                    },
                    {
                        "role": "cairn",
                        "content": "Added to your Q2 Launch Campaign act: reach out to Fatima (CS) today about healthcare tech backup customer interview availability. I'll surface this in your task list this afternoon if you haven't checked it off by 3pm.\n\nDo you also want to formally move the fintech case study scene to blocked, or wait until after you talk to Fatima?",
                    },
                    {
                        "role": "user",
                        "content": "Move it to blocked. I'm done waiting on them.",
                    },
                    {
                        "role": "cairn",
                        "content": "Fintech case study scene moved to awaiting_data with a note: customer non-responsive for 2 weeks, backup customer under evaluation. That keeps the scene visible without implying it's progressing.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What's the status of the ambassador program? I keep meaning to follow up but it slips through.",
                    },
                    {
                        "role": "cairn",
                        "content": "Ambassador program status:\n\n- 6 candidates identified\n- 3 conversations completed\n- 0 commitments\n- Target: 10 ambassadors by end of Q2\n\nThe last update I have is from two weeks ago. The three candidates you've spoken with — do you know if any of them are close to a yes, or are they all still vague?",
                    },
                    {
                        "role": "user",
                        "content": "One of them — Carlos, the developer who wrote that blog post about our sync API — I think he's genuinely interested. I just haven't sent the formal program overview yet.",
                    },
                    {
                        "role": "cairn",
                        "content": "That's a warm lead going cold from neglect, which is the easiest kind to fix. Send Carlos the program overview today — it's probably 15 minutes of work.\n\nWant me to add that as a task on the Developer Community act with a nudge if you haven't done it by end of day?",
                    },
                    {
                        "role": "user",
                        "content": "Yes. And remind me — I also need to schedule the working session with Jordan about the API attribution model.",
                    },
                    {
                        "role": "cairn",
                        "content": "Two tasks added:\n1. Send Carlos the ambassador program overview — nudge at 4pm if not done\n2. Schedule working session with Jordan Park on API trial attribution model\n\nThe Jordan one is on an open waiting-on I've had for a while. The API attribution model can't move forward until you have that session.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Elena does her best creative and strategic work in the morning. She tries to protect at least two mornings per week for thinking before Slack and meetings interrupt her. Afternoons are for operational tasks.",
                "entity_type": "insight",
                "entity_data": {"subject": "Elena Vasquez", "work_rhythm": "creative mornings, operational afternoons", "preference": "protect morning blocks"},
            },
            {
                "narrative": "Elena's team is understaffed — two writer openings unfilled since January. One contractor finishes end of March. She is personally covering writing capacity, which reduces her time for strategy, editing, and mentoring.",
                "entity_type": "insight",
                "entity_data": {"subject": "Elena Vasquez team", "issue": "understaffed", "openings": 2, "impact": "Elena doing too much writing", "urgency": "need headcount by Q3"},
            },
            {
                "narrative": "The fintech case study customer for the Q2 campaign has been non-responsive for two weeks. Elena decided to pursue the healthcare tech company as a backup. Fatima in Customer Success manages that account.",
                "entity_type": "decision",
                "entity_data": {"decision": "switch to healthcare tech backup customer for case study 3", "waiting_on": "Fatima (CS) interview availability", "deadline": "March 13 (Friday)"},
            },
            {
                "narrative": "Carlos, a developer who wrote a blog post about Meridian's sync API, is a warm lead for the ambassador program. Elena hasn't sent him the formal program overview yet.",
                "entity_type": "person",
                "entity_data": {"name": "Carlos", "context": "developer, wrote sync API blog post", "status": "warm ambassador candidate", "next_action": "send program overview"},
            },
            {
                "narrative": "Elena tends to over-connect initiatives and try to make everything relate to everything else. She acknowledged this pattern herself in conversation. The 'Under the Hood' developer webinar idea was originally framed as a concurrent track to the Q2 launch webinar, but she correctly pivoted to a May follow-up when the audience conflict was surfaced.",
                "entity_type": "insight",
                "entity_data": {"subject": "Elena Vasquez", "pattern": "over-connection of initiatives", "self-aware": True},
            },
            {
                "narrative": "Jordan Park (Marketing Analytics Manager) needs to help Elena establish an attribution model for API trial signups from developer community programs. No working session scheduled yet.",
                "entity_type": "waiting_on",
                "entity_data": {"waiting_on": "Jordan Park", "for": "API trial attribution model working session", "project": "Developer Community Program"},
            },
            {
                "narrative": "Competitive voice analysis finding: Meridian's top competitors lean heavily on 'effortless' as their brand tone. Elena's differentiation angle is 'thoughtful' and 'earned simplicity' — positioning Meridian as the tool that respects your intelligence rather than hiding complexity.",
                "entity_type": "insight",
                "entity_data": {"project": "Brand Voice Guidelines v3", "finding": "competitors use 'effortless'; differentiate on 'thoughtful' and 'earned simplicity'"},
            },
        ],
        "emails": [],
        "calendar_events": [],
    },

    {
        "id": "jordan_park",
        "identity": {
            "full_name": "Jordan Park",
            "department": "Marketing",
            "title": "Marketing Analytics Manager",
        },
        "personality": "terse",
        "your_story": """\
# Jordan Park — Marketing Analytics Manager

Marketing analytics at Meridian Labs. 29. Six years in analytics — two years at McKinsey
(business analyst, consumer and retail practice), then moved to tech because I wanted to
see my models actually used. Joined Meridian two years ago.

Day job: own the measurement infrastructure for marketing. Attribution modeling, pipeline
forecasting, campaign performance analysis, data quality, dashboard design. I report to the
VP of Marketing.

I live in spreadsheets and SQL. I use bullet points. I distrust last-touch attribution on
principle — it's a lie that's easy to measure, which is why everyone uses it. I'm a multi-touch
advocate. Currently rebuilding our attribution model from scratch using Markov chains.

Former McKinsey means I know how to structure a presentation, but I don't like making decks.
Numbers should speak. If a slide needs a paragraph of explanation, the analysis is unclear.

Korean-American. Grew up in San Francisco, still there. Run 5Ks on weekends. Efficient.
""",
        "acts": [
            {
                "title": "Attribution Model Rebuild",
                "color": "#0ea5e9",
                "notes": """\
The Attribution Model Rebuild is the most technically demanding project in my current portfolio.
The goal is to replace Meridian's current last-touch attribution system with a Markov chain-based
multi-touch attribution model that correctly distributes credit across all touchpoints in the
customer journey.

**Why We're Doing This**

Last-touch attribution is simple: 100% of conversion credit goes to the last marketing touchpoint
before a deal closes. Every analytics person knows this is wrong. It systematically undervalues
awareness and consideration-stage content (blog posts, webinars, brand advertising) and
overvalues bottom-of-funnel tactics (demo request emails, direct outreach). The result: marketing
budget optimizes toward bottom-of-funnel, awareness atrophies, and eventually pipeline weakens.
We're seeing early signs of this at Meridian.

**Data Sources**

- Salesforce (CRM): opportunity lifecycle, deal stages, close dates, amounts
- HubSpot (MAP): all marketing touchpoints with timestamps — email opens/clicks, form fills,
  content downloads, webinar registrations, event attendance
- Segment (CDP): website behavior, product trial activity, API usage events
- LinkedIn Ads, Google Ads: paid touchpoint data via API

Data pipeline: dbt transforms raw source data into a unified touchpoint table in Snowflake.
Each row is (opportunity_id, touchpoint_timestamp, touchpoint_type, channel, campaign_id).

**Model Architecture**

Markov chain attribution works by modeling the customer journey as a sequence of states
(touchpoints) and computing the removal effect of each touchpoint: if you remove channel X from
all journeys, how much does conversion probability drop? That removal effect, normalized across
all channels, is the attribution weight.

I'm using the Python `markovattribution` library as a starting point but extending it to handle:
- Multi-opportunity journeys (same account, multiple deals over time)
- Touchpoint decay weighting (recent touchpoints get slightly more weight, configurable)
- Channel grouping (paid search, organic search, email, events, content — rather than individual
  campaigns, which creates too many states)

**Validation Approach**

Validation is the hard part. You can't A/B test an attribution model the way you'd test a feature.
My approach:
1. Holdout validation: train on 18 months of closed-won opportunities, validate on the most recent
   3 months. Compare predicted vs actual channel distribution.
2. Sanity checks: compare model output to media mix modeling (we ran an MMM last year — it should
   roughly agree on which channels drive pipeline).
3. Stakeholder gut-check: does the result pass the laugh test with sales and demand gen?

**Dashboard Design**

Output will be a Looker dashboard: channel attribution summary (week/month/quarter), campaign-level
attribution, trend view (how attribution weights shift over time as we change our marketing mix).
Design in progress — working with the BI team on the Looker model.

**Status**

Data pipeline: complete. Model prototype: running, producing output. Validation: 60% through.
Most sanity checks passing. One anomaly: the model attributes significantly less credit to
LinkedIn than our current last-touch model does. Investigating whether this is correct (possible)
or a data quality issue in our LinkedIn touchpoint tracking (also possible).
""",
                "scenes": [
                    {
                        "title": "Data pipeline — unified touchpoint table",
                        "stage": "complete",
                        "notes": "dbt models in production. Touchpoint table in Snowflake. All 4 sources connected. Data quality checks passing.",
                    },
                    {
                        "title": "Markov chain model prototype",
                        "stage": "complete",
                        "notes": "Model running. Producing attribution weights. LinkedIn anomaly under investigation.",
                    },
                    {
                        "title": "Validation — holdout and sanity checks",
                        "stage": "in_progress",
                        "notes": "60% through. Holdout validation passing. MMM comparison roughly aligned. LinkedIn discrepancy unresolved.",
                    },
                    {
                        "title": "LinkedIn touchpoint data quality investigation",
                        "stage": "in_progress",
                        "notes": "Hypothesis: LinkedIn click tracking may be undercounting due to iOS privacy changes reducing click-through attribution. Need to check ad platform UTM coverage.",
                    },
                    {
                        "title": "Looker dashboard design",
                        "stage": "in_progress",
                        "notes": "Working with BI team. LookML model drafted. Channel summary and campaign views in review.",
                    },
                    {
                        "title": "Stakeholder review and rollout",
                        "stage": "planning",
                        "notes": "Plan to present to VP Marketing and demand gen leads after validation is complete. Estimate 2 weeks.",
                    },
                ],
            },
            {
                "title": "Pipeline Forecasting System",
                "color": "#06b6d4",
                "notes": """\
The Pipeline Forecasting System is a predictive model to estimate marketing-sourced pipeline
contribution 30, 60, and 90 days out. Currently, marketing pipeline projections are done manually
by the VP of Marketing using gut feel and recent trends. That's not good enough for a company at
Meridian's stage.

**Business Need**

Sales ops has a sophisticated sales pipeline forecast. Marketing has nothing equivalent. The result
is that the marketing contribution to pipeline is always presented as a lagging indicator (last
quarter's results) rather than a leading one. I want to give the business a 90-day forward view
of marketing pipeline contribution so they can make budget decisions proactively, not reactively.

**Features Used**

The model uses:
- Trailing 12-month pipeline contribution by channel and segment (ICP fit tier)
- Marketing activity levels: MQL volume, webinar attendance, content downloads, trial starts
- Seasonal patterns: Meridian has a pronounced Q1 slow and Q4 strong pattern, common in
  enterprise SaaS
- Pipeline velocity: average time from MQL to opportunity, opportunity to close-won, by segment
- External signals: job posting volume at target accounts (correlates with expansion purchasing)

**Historical Data**

Three years of historical data in Snowflake. Enough to capture two full seasonal cycles. Data
quality is uneven in the oldest year — some touchpoint tracking was inconsistent before Segment
was implemented. I'm weighting the older data down and treating it as context rather than ground
truth.

**Model Approach**

I evaluated three approaches:
1. Time series (Prophet): clean, interpretable, handles seasonality natively. Struggles with
   abrupt marketing mix changes (e.g., if we start a major new channel mid-period).
2. Gradient boosting (XGBoost): more flexible, handles many features, less interpretable.
3. Ensemble: combine both. Use Prophet for the baseline seasonal pattern, XGBoost for the
   marketing-activity adjustment on top.

Going with the ensemble. Prophet baseline is solid. XGBoost component is still being tuned.

**Accuracy Target**

Target: within 15% of actual pipeline on a rolling 90-day basis, 80% of the time. Current model
performance (backtested on holdout): within 18% of actual. Need to close that gap.
Main error driver: the model underestimates the Q4 surge — the seasonality factor needs
recalibration.

**Seasonality Note**

The Q4 enterprise buying surge is real but not fully captured in the data because Meridian
changed its go-to-market strategy two years ago (shifted from SMB to enterprise), which means
the historical Q4 patterns from 2023 aren't fully representative. I'm applying a manual
uplift factor of 1.15x to the Q4 Prophet baseline for now. Not elegant but defensible.

**Delivery**

Output: weekly Looker dashboard showing 30/60/90-day pipeline forecast with confidence intervals,
broken out by segment, channel, and geography. Stakeholder presentation to VP Marketing and CFO
once accuracy target is met.
""",
                "scenes": [
                    {
                        "title": "Historical data prep and feature engineering",
                        "stage": "complete",
                        "notes": "3 years of data in Snowflake. Features engineered. Older data down-weighted.",
                    },
                    {
                        "title": "Prophet baseline model",
                        "stage": "complete",
                        "notes": "Trained and validated. Seasonal pattern captured. Q4 manual uplift applied.",
                    },
                    {
                        "title": "XGBoost marketing-activity adjustment layer",
                        "stage": "in_progress",
                        "notes": "Still tuning. Currently within 18% of actual. Target is 15%. Q4 underestimation is primary error driver.",
                    },
                    {
                        "title": "Ensemble integration and backtesting",
                        "stage": "in_progress",
                        "notes": "Ensemble structure working. Running full backtest battery. Results by end of week.",
                    },
                    {
                        "title": "Looker dashboard — 30/60/90 day view",
                        "stage": "planning",
                        "notes": "Design drafted. Will build after model accuracy target is hit.",
                    },
                    {
                        "title": "Stakeholder presentation — VP Marketing and CFO",
                        "stage": "planning",
                        "notes": "Scheduled after dashboard is live. Will bring confidence intervals and methodology explainer.",
                    },
                ],
            },
            {
                "title": "Q1 Campaign Performance Analysis",
                "color": "#14b8a6",
                "notes": """\
The Q1 Campaign Performance Analysis is the quarterly retrospective on all marketing spend and
activity from January through March 2026. This is a routine deliverable but a critical one —
it feeds directly into Q2 budget allocation decisions and the Q2 planning cycle.

**Scope**

All marketing campaigns in Q1:
- Paid search (Google Ads): $280K spend
- LinkedIn sponsored content: $190K spend
- Content marketing (organic): blog, SEO — no direct cost, but measured on traffic and pipeline
  influence
- Webinars: three live webinars, two on-demand
- Email: six campaigns to the marketing database
- Events: two sponsored conferences (industry events in January and February)

**Channels Analyzed**

For each channel:
- Spend (if applicable)
- Impressions, clicks, CTR
- MQL volume and MQL rate
- Opportunity influence (how many open deals had a touchpoint from this channel)
- Closed-won influence (pipeline converted to revenue where this channel appeared in the journey)
- CAC (customer acquisition cost, using last-touch for apples-to-apples comparison with prior
  periods while we wait for the multi-touch model to be validated)

**Key Findings (Preliminary)**

- **Paid search**: Strongest channel by last-touch CAC ($12,400 per closed-won deal). However,
  I suspect this is inflated by attribution — search often gets credit for deals where the real
  driver was an earlier event or content touchpoint. Flagged for reassessment once multi-touch
  model is live.
- **LinkedIn**: Weakest last-touch CAC ($31,200). But my hypothesis is that LinkedIn is doing
  awareness work that isn't showing up in last-touch. This is the exact pattern the multi-touch
  model is designed to surface.
- **Webinars**: Highest opportunity influence rate (34% of opportunities in Q1 had a webinar
  touchpoint). Strongest case for a channel that's hard to attribute with last-touch.
- **Email**: Volume of 6 campaigns generated 2,100 MQLs, 18% MQL-to-opportunity conversion rate.
  Solid but not exceptional.
- **Events**: Two conferences generated 340 net-new contacts. Pipeline influence still developing
  — event contacts typically have 90-day sales cycles.

**Q2 Recommendations (Draft)**

1. Hold or increase webinar investment — strongest opportunity influence
2. Reduce LinkedIn spend cautiously until multi-touch model confirms or denies its awareness role
3. Increase paid search budget by 10-15% — most efficient last-touch channel
4. Add one event in Q2 given strong contact generation

**Q1 CAC Summary**

Overall blended CAC (last-touch, Q1): $18,700. Q1 2025 baseline: $20,100. Down 7%.
Target for 2026: $17,500. Ahead of pace but not yet at goal.

**Delivery**

Presentation to VP Marketing and the demand gen leads. Deck almost done. Scheduled for March 17.
""",
                "scenes": [
                    {
                        "title": "Data extraction and channel reporting",
                        "stage": "complete",
                        "notes": "All channel data pulled from Salesforce, HubSpot, ad platforms. Unified in Snowflake. Validated row counts.",
                    },
                    {
                        "title": "Channel analysis — paid, organic, events",
                        "stage": "complete",
                        "notes": "All channels analyzed. CAC, MQL rates, opportunity influence computed.",
                    },
                    {
                        "title": "Q2 recommendation deck",
                        "stage": "in_progress",
                        "notes": "Draft almost done. 4 recommendations. Adding a 'caveats on last-touch' section to prime the audience for multi-touch model.",
                    },
                    {
                        "title": "Stakeholder presentation — March 17",
                        "stage": "planning",
                        "notes": "Confirmed with VP Marketing. 45 minutes. Demand gen leads attending.",
                    },
                ],
            },
        ],
        "conversations": [
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Calendar today?",
                    },
                    {
                        "role": "cairn",
                        "content": "Today (Wednesday, March 11):\n\n- 10:00am — Marketing weekly sync (already passed)\n- 1:00pm — 1:1 with VP Marketing\n- 3:30pm — BI team check-in (Looker dashboard review)\n\nNothing else.",
                    },
                    {
                        "role": "user",
                        "content": "What do I need for the 1pm?",
                    },
                    {
                        "role": "cairn",
                        "content": "Based on open items:\n\n- Attribution model: LinkedIn anomaly still unresolved. Worth flagging — VP will ask.\n- Q1 analysis deck: presentation March 17. She'll want a status check.\n- Pipeline forecast: accuracy at 18%, target 15%. Not ready to present yet.\n\nAnything specific she asked you to bring?",
                    },
                    {
                        "role": "user",
                        "content": "She asked about Elena's attribution ask. Make a note.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted: VP Marketing asked about Elena Vasquez's API trial attribution request (developer community program). This is on the open waiting-on list — no working session scheduled yet. Do you want to propose a time before the 1pm meeting so you have something to report?",
                    },
                    {
                        "role": "user",
                        "content": "Yes. Send Elena a Slack message asking for 30 min this week or next.",
                    },
                    {
                        "role": "cairn",
                        "content": "Draft Slack message to Elena:\n\n\"Hey Elena — want to get 30 minutes on the calendar to work through the API trial attribution model for the developer community program. Does this week or next work for you?\"\n\nShort and direct. Want me to adjust or save this as a draft reminder for you to send manually?",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Status on attribution project?",
                    },
                    {
                        "role": "cairn",
                        "content": "Attribution model rebuild:\n\n- Data pipeline: complete\n- Model prototype: complete\n- Validation: 60% through — holdout passing, MMM comparison aligned\n- Blocker: LinkedIn discrepancy unresolved (model attributes significantly less credit to LinkedIn than last-touch; cause unclear — could be correct or could be iOS privacy tracking gap)\n- Dashboard: LookML model in review with BI team\n- Rollout: planned ~2 weeks after validation completes\n\nLinkedIn is the only open question blocking validation sign-off.",
                    },
                    {
                        "role": "user",
                        "content": "Who owns the LinkedIn tracking check?",
                    },
                    {
                        "role": "cairn",
                        "content": "Not explicitly assigned. The hypothesis is UTM coverage gaps from iOS privacy changes affecting click attribution in HubSpot. That would be a marketing ops question — likely Diego in your team or whoever manages the LinkedIn Ads integration.\n\nWant me to add a task to assign this explicitly?",
                    },
                    {
                        "role": "user",
                        "content": "Yes. Assign to Diego. Deadline Friday.",
                    },
                    {
                        "role": "cairn",
                        "content": "Task added to attribution model act: Diego to investigate LinkedIn UTM/click tracking coverage — deadline Friday March 13.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Remind me: what was the Q1 CAC number?",
                    },
                    {
                        "role": "cairn",
                        "content": "Q1 2026 blended CAC (last-touch): **$18,700**\n\nComparison:\n- Q1 2025 baseline: $20,100\n- Change: -7%\n- 2026 target: $17,500\n\nAhead of pace. Not yet at goal.",
                    },
                    {
                        "role": "user",
                        "content": "And paid search specifically?",
                    },
                    {
                        "role": "cairn",
                        "content": "Paid search Q1 CAC: **$12,400** — strongest channel by last-touch.\n\nCaveat from your analysis: you noted this is likely inflated by attribution bias (search gets credit for deals where earlier touchpoints were the real driver). Flagged for reassessment once multi-touch model is validated.",
                    },
                ],
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Weekly marketing sync — what do I need to know going in?",
                    },
                    {
                        "role": "cairn",
                        "content": "Monday 10am marketing sync prep:\n\n**Open items to surface:**\n- Attribution model: LinkedIn anomaly being investigated, Diego owns, due Friday\n- Q1 analysis: presentation March 17, deck 85% done\n- Pipeline forecast: 18% accuracy, target 15% — not ready to share yet\n- Elena's attribution ask: working session not yet scheduled\n\n**What others will likely bring:**\n- Elena usually has Q2 campaign updates — the case study situation is in flux\n- Demand gen will want the Q1 CAC number ($18,700)\n\nAnything you want to take off your plate before walking in?",
                    },
                    {
                        "role": "user",
                        "content": "No. Good enough.",
                    },
                    {
                        "role": "cairn",
                        "content": "Noted. See you after the sync if anything comes up.",
                    },
                ],
            },
        ],
        "memories": [
            {
                "narrative": "Jordan prefers data presented in tables, not prose. When giving Jordan a summary, use structured formats: numbers, comparisons, and brief labels. Avoid narrative explanations unless specifically asked.",
                "entity_type": "insight",
                "entity_data": {"subject": "Jordan Park", "preference": "tabular data over prose", "communication_style": "terse, direct"},
            },
            {
                "narrative": "Jordan's weekly marketing sync is every Monday at 10am. This is the primary cross-marketing team coordination meeting.",
                "entity_type": "person",
                "entity_data": {"meeting": "marketing weekly sync", "day": "Monday", "time": "10:00am", "recurrence": "weekly"},
            },
            {
                "narrative": "Jordan is a strong advocate for multi-touch attribution and is skeptical of last-touch models on principle. He views last-touch as 'a lie that's easy to measure.' He is actively rebuilding Meridian's attribution model using Markov chains.",
                "entity_type": "insight",
                "entity_data": {"subject": "Jordan Park", "position": "multi-touch attribution advocate", "skeptical_of": "last-touch attribution", "project": "Attribution Model Rebuild"},
            },
            {
                "narrative": "Diego (marketing ops) owns the investigation into LinkedIn UTM/click tracking coverage gaps — a potential cause of the LinkedIn attribution anomaly in the Markov chain model. Deadline: Friday March 13.",
                "entity_type": "task",
                "entity_data": {"owner": "Diego", "task": "LinkedIn UTM tracking investigation", "deadline": "2026-03-13", "project": "Attribution Model Rebuild"},
            },
            {
                "narrative": "Q1 2026 blended marketing CAC (last-touch): $18,700. Q1 2025 baseline: $20,100 (-7%). 2026 target: $17,500. Ahead of pace but not yet at goal. Paid search CAC: $12,400 (strongest channel, but likely attribution-biased).",
                "entity_type": "insight",
                "entity_data": {"metric": "Q1 2026 CAC", "blended": 18700, "paid_search": 12400, "prior_year": 20100, "target": 17500, "yoy_change_pct": -7},
            },
            {
                "narrative": "Jordan committed to Elena Vasquez (Content Marketing Director) to help design an API trial attribution model for the developer community program. No working session has been scheduled. VP Marketing asked Jordan about this.",
                "entity_type": "waiting_on",
                "entity_data": {"committed_to": "Elena Vasquez", "for": "API trial attribution working session", "vp_aware": True, "status": "not scheduled"},
            },
            {
                "narrative": "The pipeline forecasting model is within 18% of actual on a 90-day basis. Target is 15%. The primary error driver is Q4 underestimation due to Meridian's go-to-market shift (SMB to enterprise) making pre-2024 historical data less representative. Jordan applied a manual 1.15x Q4 uplift as a temporary calibration fix.",
                "entity_type": "insight",
                "entity_data": {"project": "Pipeline Forecasting System", "current_accuracy_pct": 18, "target_accuracy_pct": 15, "error_driver": "Q4 underestimation", "mitigation": "1.15x manual Q4 uplift"},
            },
        ],
        "emails": [],
        "calendar_events": [],
    },
]
