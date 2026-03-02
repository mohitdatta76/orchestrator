---
name: o365_data
description: Provides awareness of live O365 data synced from email, calendar, Teams, and org structure.
always: true
priority: 95
tools: [read_memory, search_memory]
---

# O365 Data Awareness

Live O365 data is available in memory when `sync.py` has been run recently.
Always check memory freshness before answering questions about meetings, email, or org structure.

## Available memory keys

| Key | Contents | How to read |
|---|---|---|
| `calendar` | Events for next 7 days — subjects, attendees, times, locations | `read_memory("calendar")` |
| `email_signals` | Flagged messages, high-priority email, direct unread | `read_memory("email_signals")` |
| `org` | Your profile + direct reports tree (two levels deep) | `read_memory("org")` |
| `people` | Known people: name, email, title — your directs + manually added | `read_memory("people")` |
| `network_people` | Top ~25 people Graph considers most relevant to you | `read_memory("network_people")` |
| `teams_mentions` | Recent Teams messages where you were @mentioned | `read_memory("teams_mentions")` |

## How to use this data

**Before any briefing, meeting prep, or "what's urgent" question:**
1. Call `read_memory("calendar")` — check today's and tomorrow's meetings
2. Call `read_memory("email_signals")` — check flagged and high-priority email
3. Call `read_memory("teams_mentions")` — check any Teams threads needing attention
4. Cross-reference with `read_memory("action_items")` — open commitments

**For questions about people:**
- Check `people` first (your directs, manually added context)
- Then `org` for org structure and reporting relationships
- Then `network_people` for broader network context

**Freshness check:**
- Each record has a `fetched_at` timestamp — mention to the user if data is more than 24 hours old
- If memory keys are missing, tell the user to run: `python sync.py`

## Data not yet in memory

If the user asks about something not covered above (e.g., specific email threads,
ADO work items, detailed Teams channels), tell them what would need to be added
rather than guessing. The sync layer is extensible — new PS scripts can be added
to `scripts/ps/` and wired into `sync.py`.
