"""Generate realistic mock emails for each profile."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

BASE_DATE = datetime(2026, 3, 13, 9, 0, 0)

# Common Meridian Labs people (appear as senders/recipients across profiles)
MERIDIAN_PEOPLE = {
    "eng": [
        ("Priya Chandrasekaran", "priya@meridian-labs.com"),
        ("Derek Okafor", "derek@meridian-labs.com"),
        ("Marcus Chen", "marcus.chen@meridian-labs.com"),
        ("Lisa Park", "lisa.park@meridian-labs.com"),
        ("Ravi Sharma", "ravi@meridian-labs.com"),
    ],
    "marketing": [
        ("Elena Vasquez", "elena@meridian-labs.com"),
        ("Jordan Park", "jordan.park@meridian-labs.com"),
        ("Amy Nguyen", "amy.nguyen@meridian-labs.com"),
        ("Ben Torres", "ben.torres@meridian-labs.com"),
    ],
    "finance": [
        ("Catherine Liu", "catherine@meridian-labs.com"),
        ("Tomás Rivera", "tomas@meridian-labs.com"),
        ("Sarah Kim", "sarah.kim@meridian-labs.com"),
    ],
    "hr": [
        ("Denise Washington", "denise@meridian-labs.com"),
        ("Kai Nakamura", "kai@meridian-labs.com"),
        ("Rachel Adams", "rachel.adams@meridian-labs.com"),
    ],
    "product": [
        ("Sam Abeywickrama", "sam@meridian-labs.com"),
        ("Aisha Osman", "aisha@meridian-labs.com"),
        ("Mike Zhang", "mike.zhang@meridian-labs.com"),
    ],
    "ops": [
        ("Viktor Petrov", "viktor@meridian-labs.com"),
        ("Riley Chen", "riley@meridian-labs.com"),
        ("Dana Liu", "dana.liu@meridian-labs.com"),
    ],
    "leadership": [
        ("James Whitfield", "james@meridian-labs.com"),
        ("Nora Okafor", "nora@meridian-labs.com"),
        ("David Park", "david.park@meridian-labs.com"),
    ],
}

EXTERNAL_SENDERS = [
    ("AWS Notifications", "no-reply@aws.amazon.com"),
    ("GitHub", "notifications@github.com"),
    ("Jira", "jira@meridian-labs.atlassian.net"),
    ("Slack", "notification@slack.com"),
    ("Google Calendar", "calendar-notification@google.com"),
    ("Jennifer Walsh", "jennifer.walsh@acme-corp.com"),
    ("Robert Singh", "robert.singh@techflow.io"),
    ("Amanda Torres", "amanda@designpartners.co"),
    ("Zoom", "no-reply@zoom.us"),
    ("IT Security", "security@meridian-labs.com"),
    ("Payroll", "payroll@meridian-labs.com"),
    ("Benefits", "benefits@meridian-labs.com"),
    ("Linda Foster", "lfoster@globaldata.com"),
    ("Nathan Brooks", "nbrooks@vendortrack.com"),
]

# Subject templates by category
SUBJECT_TEMPLATES = {
    "project_update": [
        "Re: {project} — status update",
        "{project}: weekly sync notes",
        "Update on {project} timeline",
        "{project} — blocker identified",
        "Re: {project} deliverables for this sprint",
        "{project}: milestone review",
        "FYI: {project} dependency change",
    ],
    "meeting": [
        "Re: Agenda for {meeting}",
        "{meeting} — rescheduled to {day}",
        "Notes from {meeting}",
        "Action items from {meeting}",
        "Canceling {meeting} this week",
    ],
    "request": [
        "Quick question about {topic}",
        "Need your input on {topic}",
        "Can you review {topic}?",
        "Urgent: {topic}",
        "Help needed with {topic}",
        "FYI — {topic}",
    ],
    "announcement": [
        "[All Hands] {topic}",
        "Company Update: {topic}",
        "New Policy: {topic}",
        "Reminder: {topic}",
        "Important: {topic}",
    ],
    "automated": [
        "[Jira] {ticket} updated",
        "[GitHub] PR #{pr_num}: {pr_title}",
        "[CI/CD] Build {status} — {branch}",
        "[AWS] CloudWatch Alarm: {alarm}",
        "[Slack] {count} unread messages in #{channel}",
    ],
}


def _random_date(days_back: int = 30) -> datetime:
    """Random datetime within the last N days."""
    offset = random.randint(0, days_back * 24 * 60)
    return BASE_DATE - timedelta(minutes=offset)


def _short_body(topic: str) -> str:
    bodies = [
        f"Noted on {topic}. Will follow up.",
        f"Thanks for the update on {topic}.",
        f"Got it. Let's discuss in our next sync.",
        f"Acknowledged. I'll take a look at {topic} today.",
        f"Makes sense. Let me know if anything changes.",
        f"+1. {topic} looks good to go.",
        f"Flagging this for the team. {topic} needs attention.",
    ]
    return random.choice(bodies)


def _medium_body(topic: str, sender: str) -> str:
    bodies = [
        f"Hi team,\n\nQuick update on {topic}. We've made progress on the main deliverables "
        f"and are on track for the milestone. A few things to flag:\n\n"
        f"- The dependency on the platform team is resolved\n"
        f"- We still need to finalize the testing strategy\n"
        f"- I'll share a detailed timeline by EOW\n\n"
        f"Let me know if you have questions.\n\nBest,\n{sender}",

        f"Hey,\n\nFollowing up on our discussion about {topic}. I've put together "
        f"an initial proposal and would love your feedback. Key points:\n\n"
        f"1. We should prioritize the core use case first\n"
        f"2. The integration with existing systems will take ~2 weeks\n"
        f"3. We need sign-off from leadership before proceeding\n\n"
        f"Can we sync on this tomorrow?\n\n{sender}",

        f"Team,\n\nWanted to share some findings from the {topic} analysis. "
        f"The data suggests we should adjust our approach. Specifically:\n\n"
        f"- Current approach has a 23% failure rate in edge cases\n"
        f"- Alternative approach tested at 4% failure rate\n"
        f"- Cost difference is minimal (~$200/mo)\n\n"
        f"I'd recommend we switch. Thoughts?\n\n{sender}",

        f"Hi,\n\nRegarding {topic} — I've completed the first phase of work "
        f"and wanted to get alignment before moving forward. Here's where we stand:\n\n"
        f"Done:\n- Requirements gathering\n- Initial design review\n- Stakeholder interviews\n\n"
        f"Next:\n- Prototype development\n- User testing (scheduled for next week)\n- Final spec\n\n"
        f"Any concerns before I proceed?\n\n{sender}",
    ]
    return random.choice(bodies)


def _long_body(topic: str, sender: str) -> str:
    return (
        f"Hi everyone,\n\n"
        f"I wanted to send a comprehensive update on {topic} since we've had several "
        f"developments over the past week that I think are worth discussing in detail.\n\n"
        f"## Background\n\n"
        f"As you know, we kicked off this initiative at the beginning of Q1 with the goal "
        f"of improving our {topic.lower()} capabilities. Since then, the team has been "
        f"working through the discovery phase and we've uncovered some interesting findings.\n\n"
        f"## Key Findings\n\n"
        f"First, the current system is handling about 3x the load we originally designed for. "
        f"This is both good news (adoption is strong) and concerning (we're approaching "
        f"capacity limits). The performance data shows:\n\n"
        f"- Average response time: 240ms (target: <200ms)\n"
        f"- P99 response time: 1.2s (target: <500ms)\n"
        f"- Error rate: 0.3% (target: <0.1%)\n\n"
        f"Second, user feedback from the last round of interviews indicates that the "
        f"primary pain point isn't performance but rather the workflow complexity. Users "
        f"are spending an average of 4.2 steps to complete what should be a 2-step process.\n\n"
        f"## Proposed Changes\n\n"
        f"Based on these findings, I'm proposing we adjust our roadmap:\n\n"
        f"1. **Short-term (2 weeks):** Address the performance bottleneck in the data layer\n"
        f"2. **Medium-term (6 weeks):** Redesign the primary workflow to reduce steps\n"
        f"3. **Long-term (Q3):** Full architecture review with the platform team\n\n"
        f"I've shared the detailed proposal in the project doc and would appreciate your "
        f"review by end of week.\n\n"
        f"## Action Items\n\n"
        f"- {sender}: Finalize the performance benchmark suite\n"
        f"- Engineering: Review the proposed data layer changes\n"
        f"- Product: Validate the workflow redesign with 3 key customers\n"
        f"- Leadership: Approve the adjusted timeline and resource allocation\n\n"
        f"Let me know if you have questions or concerns. Happy to set up a deeper dive "
        f"session if that would be helpful.\n\n"
        f"Thanks,\n{sender}"
    )


def generate_emails(profile: dict) -> list[dict]:
    """Generate 100 realistic emails for a profile."""
    personality = profile["personality"]
    dept = profile["identity"]["department"].lower()
    full_name = profile["identity"]["full_name"]
    email_addr = f"{profile['id'].split('_')[0]}@meridian-labs.com"
    act_titles = [a["title"] for a in profile["acts"]]

    # Build sender pool: same department + cross-functional + external
    dept_key = {
        "engineering": "eng", "marketing": "marketing", "finance": "finance",
        "hr / people operations": "hr", "people operations": "hr", "hr": "hr",
        "product management": "product", "product": "product",
        "operations / it": "ops", "operations": "ops", "it": "ops",
    }.get(dept, "eng")

    same_dept = [p for p in MERIDIAN_PEOPLE.get(dept_key, []) if p[0] != full_name]
    other_depts = []
    for k, v in MERIDIAN_PEOPLE.items():
        if k != dept_key and k != "leadership":
            other_depts.extend(v)
    leaders = MERIDIAN_PEOPLE["leadership"]

    emails = []
    topics = act_titles + [
        "Q2 planning", "team offsite", "budget review", "hiring plan",
        "security audit", "performance review", "tool migration",
        "customer feedback", "sprint retrospective", "OKR check-in",
    ]
    meetings = [
        "Monday team standup", "weekly 1:1", "Q2 planning session",
        "all-hands", "project review", "design review", "sprint planning",
    ]
    tickets = ["MERID-1234", "MERID-2891", "MERID-3045", "MERID-1567", "MERID-4201"]
    channels = ["general", "engineering", "random", "launches", "incidents"]

    for i in range(100):
        date = _random_date(30)
        is_read = random.random() < 0.7
        has_attachment = random.random() < 0.15

        # Decide email type
        roll = random.random()
        if roll < 0.15:
            # Automated notification
            tmpl = random.choice(SUBJECT_TEMPLATES["automated"])
            sender = random.choice(EXTERNAL_SENDERS)
            subject = tmpl.format(
                ticket=random.choice(tickets),
                pr_num=random.randint(100, 999),
                pr_title="Fix race condition in sync layer",
                status=random.choice(["succeeded", "failed"]),
                branch=random.choice(["main", "feature/sync-v3", "fix/memory-leak"]),
                alarm=random.choice(["High CPU", "Disk Space Low", "API Latency"]),
                count=random.randint(3, 47),
                channel=random.choice(channels),
            )
            body = f"Automated notification.\n\n{subject}\n\nView details in the dashboard."
            importance = "normal"
        elif roll < 0.30:
            # Meeting-related
            tmpl = random.choice(SUBJECT_TEMPLATES["meeting"])
            sender = random.choice(same_dept + leaders) if same_dept else random.choice(other_depts)
            subject = tmpl.format(
                meeting=random.choice(meetings),
                day=random.choice(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
            )
            body = _medium_body(random.choice(meetings), sender[0])
            importance = "normal"
        elif roll < 0.50:
            # Project update
            tmpl = random.choice(SUBJECT_TEMPLATES["project_update"])
            sender = random.choice(same_dept + other_depts[:3])
            topic = random.choice(act_titles)
            subject = tmpl.format(project=topic)
            if personality in ("verbose", "creative"):
                body = _long_body(topic, sender[0])
            elif personality in ("terse",):
                body = _short_body(topic)
            else:
                body = _medium_body(topic, sender[0])
            importance = random.choice(["normal", "normal", "high"])
        elif roll < 0.70:
            # Request/question
            tmpl = random.choice(SUBJECT_TEMPLATES["request"])
            sender = random.choice(same_dept + other_depts)
            topic = random.choice(topics)
            subject = tmpl.format(topic=topic)
            body = _medium_body(topic, sender[0])
            importance = "high" if "Urgent" in tmpl else "normal"
        elif roll < 0.85:
            # Cross-functional
            tmpl = random.choice(SUBJECT_TEMPLATES["request"])
            sender = random.choice(other_depts + leaders)
            topic = random.choice(topics)
            subject = tmpl.format(topic=topic)
            body = _medium_body(topic, sender[0])
            importance = "normal"
        else:
            # Company announcement
            tmpl = random.choice(SUBJECT_TEMPLATES["announcement"])
            sender = random.choice(leaders)
            topic = random.choice([
                "Q1 Results & Q2 Outlook", "New Benefits Package",
                "Office Closure March 28", "Engineering All-Hands March 20",
                "Updated Travel Policy", "Meridian Labs Turns 5!",
                "Series C Update", "New Hire Welcome — March Cohort",
            ])
            subject = tmpl.format(topic=topic)
            body = _long_body(topic, sender[0])
            importance = "normal"
            has_attachment = random.random() < 0.3

        # Recipients: usually the profile user, sometimes team lists
        if random.random() < 0.7:
            recipients = email_addr
        else:
            team_list = f"{dept_key}-team@meridian-labs.com"
            recipients = f"{team_list}, {email_addr}"

        folder = "Inbox" if random.random() < 0.85 else random.choice(["Sent", "Archive"])

        emails.append({
            "id": f"email-{uuid.uuid4()}",
            "message_id": f"<{uuid.uuid4()}@meridian-labs.com>",
            "subject": subject,
            "sender": f"{sender[0]} <{sender[1]}>",
            "recipients": recipients,
            "date": date.isoformat(),
            "body": body,
            "is_read": 1 if is_read else 0,
            "folder": folder,
            "has_attachment": 1 if has_attachment else 0,
            "importance": importance,
        })

    # Sort by date descending
    emails.sort(key=lambda e: e["date"], reverse=True)
    return emails
