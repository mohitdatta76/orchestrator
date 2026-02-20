"""
Microsoft Graph API client with mock-data fallback.

Auth priority (highest to lowest):
  1. GRAPH_ACCESS_TOKEN env var — manual token, expires ~1 hour
  2. MSAL device code flow — set GRAPH_CLIENT_ID + GRAPH_TENANT_ID in .env,
     then run: python manager/auth.py --login
  3. Mock mode — realistic synthetic data, no credentials needed
"""

import os
from datetime import datetime, timedelta, timezone

from manager.auth import get_access_token

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self):
        self.token = get_access_token()
        self.mock_mode = not bool(self.token)
        if self.mock_mode:
            print("[graph] No credentials configured — running in mock mode")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_emails(self, days: int = 1, max_results: int = 20) -> list[dict]:
        if self.mock_mode:
            return self._mock_emails(days, max_results)
        return self._real_emails(days, max_results)

    def get_calendar(self, days_ahead: int = 2, days_back: int = 1) -> list[dict]:
        if self.mock_mode:
            return self._mock_calendar(days_ahead, days_back)
        return self._real_calendar(days_ahead, days_back)

    def get_teams_messages(self, days: int = 1, chats_only: bool = False) -> list[dict]:
        if self.mock_mode:
            return self._mock_teams(days, chats_only)
        return self._real_teams(days, chats_only)

    def get_meeting_transcript(self, meeting_subject: str) -> str:
        if self.mock_mode:
            return self._mock_transcript(meeting_subject)
        return self._real_transcript(meeting_subject)

    # ------------------------------------------------------------------
    # Real Graph API calls
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _real_emails(self, days: int, max_results: int) -> list[dict]:
        if not _REQUESTS_AVAILABLE:
            return [{"error": "requests library not installed"}]
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        url = (
            f"{GRAPH_BASE}/me/messages"
            f"?$filter=receivedDateTime ge {since}"
            f"&$select=subject,from,receivedDateTime,importance,bodyPreview,isRead"
            f"&$orderby=receivedDateTime desc"
            f"&$top={max_results}"
        )
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        items = resp.json().get("value", [])
        return [
            {
                "id": m["id"],
                "subject": m.get("subject", "(no subject)"),
                "from": m.get("from", {}).get("emailAddress", {}).get("name", "Unknown"),
                "from_email": m.get("from", {}).get("emailAddress", {}).get("address", ""),
                "received": m.get("receivedDateTime", ""),
                "importance": m.get("importance", "normal"),
                "is_read": m.get("isRead", True),
                "preview": m.get("bodyPreview", "")[:300],
            }
            for m in items
        ]

    def _real_calendar(self, days_ahead: int, days_back: int) -> list[dict]:
        if not _REQUESTS_AVAILABLE:
            return [{"error": "requests library not installed"}]
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=days_back)).isoformat()
        end = (now + timedelta(days=days_ahead)).isoformat()
        url = (
            f"{GRAPH_BASE}/me/calendarView"
            f"?startDateTime={start}&endDateTime={end}"
            f"&$select=subject,start,end,organizer,attendees,isOnlineMeeting,onlineMeeting,bodyPreview"
            f"&$orderby=start/dateTime"
            f"&$top=50"
        )
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        items = resp.json().get("value", [])
        return [
            {
                "id": e.get("id", ""),
                "subject": e.get("subject", "(no title)"),
                "start": e.get("start", {}).get("dateTime", ""),
                "end": e.get("end", {}).get("dateTime", ""),
                "organizer": e.get("organizer", {}).get("emailAddress", {}).get("name", ""),
                "attendees": [
                    a.get("emailAddress", {}).get("name", "")
                    for a in e.get("attendees", [])[:10]
                ],
                "is_online": e.get("isOnlineMeeting", False),
                "join_url": e.get("onlineMeeting", {}).get("joinUrl", ""),
                "notes": e.get("bodyPreview", "")[:200],
            }
            for e in items
        ]

    def _real_teams(self, days: int, chats_only: bool) -> list[dict]:
        # Teams Graph API requires specific permissions and is more complex.
        # Basic implementation — expand as needed.
        if not _REQUESTS_AVAILABLE:
            return [{"error": "requests library not installed"}]
        url = f"{GRAPH_BASE}/me/chats?$expand=members&$top=20"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        chats = resp.json().get("value", [])
        messages = []
        since = datetime.now(timezone.utc) - timedelta(days=days)
        for chat in chats[:10]:
            msgs_url = (
                f"{GRAPH_BASE}/me/chats/{chat['id']}/messages"
                f"?$top=10&$orderby=createdDateTime desc"
            )
            msgs_resp = requests.get(msgs_url, headers=self._headers(), timeout=15)
            if msgs_resp.status_code != 200:
                continue
            for m in msgs_resp.json().get("value", []):
                created = m.get("createdDateTime", "")
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt < since:
                        continue
                except (ValueError, AttributeError):
                    pass
                body = m.get("body", {}).get("content", "")
                # Strip HTML tags crudely
                import re
                body = re.sub(r"<[^>]+>", "", body).strip()
                if body:
                    messages.append({
                        "type": "chat",
                        "chat_id": chat["id"],
                        "from": m.get("from", {}).get("user", {}).get("displayName", "Unknown"),
                        "timestamp": created,
                        "body": body[:400],
                        "is_mention": "@" in body,
                    })
        return messages

    def _real_transcript(self, meeting_subject: str) -> str:
        # Transcripts require meeting recordings — complex to fetch.
        # Placeholder for future implementation.
        return f"(Transcript retrieval not yet implemented for real API — search subject: '{meeting_subject}')"

    # ------------------------------------------------------------------
    # Mock data (realistic Microsoft engineering manager scenario)
    # ------------------------------------------------------------------

    def _mock_emails(self, days: int, max_results: int) -> list[dict]:
        today = datetime.now(timezone.utc)
        emails = [
            {
                "id": "email_001",
                "subject": "Re: Q1 OKR review — action needed by EOD",
                "from": "Priya Sharma",
                "from_email": "priya.sharma@microsoft.com",
                "received": (today - timedelta(hours=2)).isoformat(),
                "importance": "high",
                "is_read": False,
                "preview": (
                    "Hi, following up on the Q1 OKR review. We need your team's "
                    "final KR status by end of day today. Please have your managers "
                    "submit their updates in the shared deck. Key area: Reliability KR "
                    "is showing 94.2% vs 99% target — will need a note on remediation plan."
                ),
            },
            {
                "id": "email_002",
                "subject": "Incident post-mortem: P0 outage Feb 17 — review required",
                "from": "On-Call Rotation",
                "from_email": "oncall@microsoft.com",
                "received": (today - timedelta(hours=5)).isoformat(),
                "importance": "high",
                "is_read": False,
                "preview": (
                    "The post-mortem doc for the Feb 17 P0 is ready for leadership review. "
                    "Root cause: config change not validated in staging. 3 action items assigned "
                    "to your org. Please review and sign off before the all-hands Thursday."
                ),
            },
            {
                "id": "email_003",
                "subject": "FYI: Engineering all-hands agenda — input requested",
                "from": "Alex Chen",
                "from_email": "alex.chen@microsoft.com",
                "received": (today - timedelta(hours=8)).isoformat(),
                "importance": "normal",
                "is_read": True,
                "preview": (
                    "Sharing the draft agenda for Thursday all-hands. We have 10 minutes "
                    "allocated for your org's Q1 progress update. Please send talking points "
                    "by Wednesday noon. Happy to help you shape the narrative."
                ),
            },
            {
                "id": "email_004",
                "subject": "Team health survey results — Manager action needed",
                "from": "People Team",
                "from_email": "peopleteam@microsoft.com",
                "received": (today - timedelta(hours=12)).isoformat(),
                "importance": "normal",
                "is_read": False,
                "preview": (
                    "Your org's Connect survey results are ready. Overall score: 68 (down 4 pts "
                    "from last quarter). Lower scores in 'clarity of direction' and 'manager "
                    "effectiveness' for Team Phoenix. Recommend 1:1 discussion with that manager. "
                    "Results dashboard linked below."
                ),
            },
            {
                "id": "email_005",
                "subject": "Headcount request: approval needed for SWE IC4 backfill",
                "from": "Jordan Rivera",
                "from_email": "jordan.rivera@microsoft.com",
                "received": (today - timedelta(hours=18)).isoformat(),
                "importance": "normal",
                "is_read": True,
                "preview": (
                    "Hi, as discussed in our 1:1 last week, I'm formally requesting approval "
                    "to backfill the IC4 position on my team (open since January). We're "
                    "blocked on the Copilot integration feature without this person. JD attached. "
                    "Can you approve in IcM by Friday?"
                ),
            },
            {
                "id": "email_006",
                "subject": "Re: Cross-team dependency: API contract change — your input needed",
                "from": "Sam Patel",
                "from_email": "sam.patel@microsoft.com",
                "received": (today - timedelta(days=1, hours=3)).isoformat(),
                "importance": "normal",
                "is_read": True,
                "preview": (
                    "Following up from yesterday's sync. The API breaking change from Platform "
                    "team will affect two of your team's services. They propose a 3-week migration "
                    "window starting March 1. Your teams need to confirm capacity. Can you check "
                    "with Jordan and Casey and reply by tomorrow?"
                ),
            },
            {
                "id": "email_007",
                "subject": "[PROMOTION] Nomination package for Casey Williams - SEM promo cycle",
                "from": "Casey Williams",
                "from_email": "casey.williams@microsoft.com",
                "received": (today - timedelta(days=1, hours=8)).isoformat(),
                "importance": "normal",
                "is_read": False,
                "preview": (
                    "Attaching my updated promo packet for the Feb cycle. I've incorporated "
                    "your feedback from last month. Key evidence added: the Phoenix launch "
                    "metrics and the cross-org collaboration section. Deadline for submission "
                    "is Feb 28. Please review when you get a chance."
                ),
            },
            {
                "id": "email_008",
                "subject": "FYI: Org re-org proposal from leadership — confidential",
                "from": "VP Engineering",
                "from_email": "vpeng@microsoft.com",
                "received": (today - timedelta(days=1, hours=12)).isoformat(),
                "importance": "high",
                "is_read": False,
                "preview": (
                    "Sharing for awareness: leadership is considering moving the Data Platform "
                    "team under a different org. This is not final. Please do not share. "
                    "Will discuss impact at the staff meeting Friday. Start thinking about "
                    "team structure implications."
                ),
            },
        ]
        return emails[:max_results]

    def _mock_calendar(self, days_ahead: int, days_back: int) -> list[dict]:
        today = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
        events = [
            {
                "id": "cal_001",
                "subject": "1:1 with Jordan Rivera",
                "start": (today + timedelta(hours=1)).isoformat(),
                "end": (today + timedelta(hours=1, minutes=30)).isoformat(),
                "organizer": "You",
                "attendees": ["Jordan Rivera"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock",
                "notes": "Weekly 1:1. Jordan is working on Copilot integration, headcount ask pending.",
            },
            {
                "id": "cal_002",
                "subject": "Team Standup — Engineering Staff",
                "start": (today + timedelta(hours=3)).isoformat(),
                "end": (today + timedelta(hours=3, minutes=30)).isoformat(),
                "organizer": "You",
                "attendees": ["Jordan Rivera", "Casey Williams", "Robin Kumar", "Sam Patel"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock2",
                "notes": "Weekly staff sync. Agenda: OKR updates, P0 post-mortem review, API migration.",
            },
            {
                "id": "cal_003",
                "subject": "Skip-level: Robin Kumar's team",
                "start": (today + timedelta(hours=5)).isoformat(),
                "end": (today + timedelta(hours=5, minutes=45)).isoformat(),
                "organizer": "You",
                "attendees": ["Robin Kumar", "Team Phoenix ICs (4)"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock3",
                "notes": "Quarterly skip-level. Team survey scores were lower this quarter — clarify org direction.",
            },
            {
                "id": "cal_004",
                "subject": "Architecture review: Copilot Integration v2",
                "start": (today + timedelta(days=1, hours=2)).isoformat(),
                "end": (today + timedelta(days=1, hours=3)).isoformat(),
                "organizer": "Alex Chen",
                "attendees": ["Alex Chen", "Jordan Rivera", "You", "Platform Team"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock4",
                "notes": "Design review for the new Copilot integration surface. Jordan presenting.",
            },
            {
                "id": "cal_005",
                "subject": "Engineering All-Hands",
                "start": (today + timedelta(days=2, hours=1)).isoformat(),
                "end": (today + timedelta(days=2, hours=3)).isoformat(),
                "organizer": "VP Engineering",
                "attendees": ["All Engineering"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock5",
                "notes": "You have a 10-minute slot for Q1 org progress. Talking points needed by Wednesday noon.",
            },
            {
                "id": "cal_006",
                "subject": "1:1 with Casey Williams",
                "start": (today + timedelta(days=1, hours=4)).isoformat(),
                "end": (today + timedelta(days=1, hours=4, minutes=30)).isoformat(),
                "organizer": "You",
                "attendees": ["Casey Williams"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock6",
                "notes": "Casey's promotion packet is ready for your review — promo cycle deadline Feb 28.",
            },
            {
                "id": "cal_007",
                "subject": "Staff meeting with Director",
                "start": (today + timedelta(days=2, hours=4)).isoformat(),
                "end": (today + timedelta(days=2, hours=5)).isoformat(),
                "organizer": "VP Engineering",
                "attendees": ["VP Engineering", "Peer M2s", "You"],
                "is_online": True,
                "join_url": "https://teams.microsoft.com/l/meetup-join/mock7",
                "notes": "Weekly staff. Org re-org discussion expected. Be ready to discuss team structure impact.",
            },
        ]
        return events

    def _mock_teams(self, days: int, chats_only: bool) -> list[dict]:
        today = datetime.now(timezone.utc)
        messages = [
            {
                "type": "chat",
                "chat_id": "chat_jordan",
                "from": "Jordan Rivera",
                "timestamp": (today - timedelta(hours=1)).isoformat(),
                "body": (
                    "Hey, quick heads up — the API contract review meeting tomorrow might run long. "
                    "Sam's team has concerns about backward compatibility. Might want to prep "
                    "for a tough conversation."
                ),
                "is_mention": False,
            },
            {
                "type": "chat",
                "chat_id": "chat_casey",
                "from": "Casey Williams",
                "timestamp": (today - timedelta(hours=3)).isoformat(),
                "body": (
                    "Did you get a chance to look at my promo packet? The deadline is Feb 28 "
                    "and I want to make sure we have enough time for your edits."
                ),
                "is_mention": False,
            },
            {
                "type": "channel",
                "chat_id": "channel_incidents",
                "from": "Robin Kumar",
                "timestamp": (today - timedelta(hours=6)).isoformat(),
                "body": (
                    "@you The post-mortem action items are assigned — two to my team, one to Jordan's. "
                    "We're on track to close them before Thursday's all-hands. Want to review before we publish?"
                ),
                "is_mention": True,
            },
            {
                "type": "chat",
                "chat_id": "chat_priya",
                "from": "Priya Sharma",
                "timestamp": (today - timedelta(hours=8)).isoformat(),
                "body": (
                    "Reminder: OKR deck is due today EOD. The reliability KR gap is the "
                    "one leadership is watching most closely. Make sure your note is specific "
                    "about root cause and the recovery timeline."
                ),
                "is_mention": False,
            },
            {
                "type": "channel",
                "chat_id": "channel_eng_staff",
                "from": "Sam Patel",
                "timestamp": (today - timedelta(hours=10)).isoformat(),
                "body": (
                    "Adding context for tomorrow's arch review: Platform team's breaking change "
                    "is a required field addition to the response schema. Services that don't "
                    "update by March 14 will start getting 400s. Jordan's service and Casey's "
                    "data pipeline are both affected."
                ),
                "is_mention": False,
            },
            {
                "type": "chat",
                "chat_id": "chat_robin",
                "from": "Robin Kumar",
                "timestamp": (today - timedelta(days=1, hours=2)).isoformat(),
                "body": (
                    "The team survey results came in lower than expected. I think the 'clarity "
                    "of direction' score is partly on me — I haven't communicated the H1 roadmap "
                    "clearly enough. Planning to do a team meeting to walk through it this week. "
                    "Would love your input on the framing."
                ),
                "is_mention": False,
            },
        ]
        return messages

    def _mock_transcript(self, meeting_subject: str) -> str:
        return f"""[Mock transcript for: {meeting_subject}]

[00:00] You: Let's get started. Jordan, can you walk us through the Copilot integration status?

[01:23] Jordan Rivera: Sure. We're about 70% done with the core API integration. Main blocker
right now is the auth layer — we're waiting on the identity team to expose the new token endpoint.

[05:41] Alex Chen: What's the ETA on the identity team's side?

[06:02] Jordan Rivera: They said end of next week, but it's been slipping. We might need to
escalate if it doesn't land by Wednesday.

[07:15] You: Jordan, let's set up a check-in with identity team tomorrow. I'll join if needed.
Action item on me to reach out to their manager today.

[09:30] Casey Williams: I also want to flag — our data pipeline depends on the same auth token.
If it slips further we miss our March 1 milestone.

[11:00] You: Noted. Let's treat this as a shared blocker. I'll escalate with the identity team
today. Everyone else — are there other cross-team blockers I should know about?

[13:20] Meeting ended.
"""
