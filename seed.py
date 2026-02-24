#!/usr/bin/env python3
"""
Seed the memory store from raw input data.

Takes flat, unstructured data — meeting notes, email threads, 1:1 notes,
Slack/Teams conversations, project docs — and uses Claude to extract structured
context and write it into the right memory files.

Usage:
  python seed.py --file notes.txt           # process a single file
  python seed.py --dir ./raw_data/          # process all .txt/.md files in a dir
  python seed.py --text "paste text here"   # process inline text
  cat notes.txt | python seed.py            # pipe from stdin

  python seed.py --file notes.txt --dry-run # preview without writing
  python seed.py --dir ./raw/ --verbose     # show Claude's full extraction

What it does:
  1. Reads your raw input (any format — messy is fine)
  2. Sends it to Claude with instructions to identify what it is and extract structure
  3. Writes extracted content to the right memory files:
       - Named person → memory/people/<alias>.md
       - Named project → memory/projects/<name>.md
       - Narrative/events → memory/context.md
       - Decisions → memory/decisions.md
       - Action items → memory/action_items.json
  4. Prints a summary of what was written

For large inputs, the file is automatically chunked so nothing gets lost.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from config import Config
from manager import memory_store

# Maximum characters to send in a single Claude call before chunking
CHUNK_SIZE = 12_000

EXTRACT_SYSTEM_PROMPT = """You are processing raw manager data to extract structured memory for a Microsoft M2 engineering manager's assistant.

The input is unstructured — it could be meeting notes, email threads, 1:1 transcripts, project updates, Slack/Teams conversations, or any mix. It may be messy, abbreviated, or in note form. That's fine.

Your job: extract structured intelligence and return it as JSON.

Return ONLY valid JSON matching this schema exactly — no prose, no markdown fences:

{
  "summary": "1-2 sentence description of what this input contains",
  "writes": [
    {
      "key": "people/firstname_lastname",
      "content": "well-formatted markdown to prepend to this person's memory file"
    },
    {
      "key": "projects/project_name_slug",
      "content": "well-formatted markdown to prepend to this project's memory file"
    },
    {
      "key": "context",
      "content": "2-4 sentence narrative summary of key events/signals from this input"
    },
    {
      "key": "decisions",
      "content": "formatted decision entry if any important decisions appear"
    }
  ],
  "action_items": [
    {
      "title": "short imperative action title",
      "owner": "me or person name",
      "due": "YYYY-MM-DD or null",
      "context": "one sentence: where this came from"
    }
  ]
}

Rules for `writes`:
- Only include entries where there is actual content worth writing. Omit empty sections.
- For `people/<alias>`: alias is firstname_lastname (lowercase, underscore). Include: date header, what was discussed, their mood/concerns, any commitments made, observations.
- For `projects/<slug>`: slug is lowercase_underscore version of project name. Include: date header, status signals, decisions, blockers, action items.
- For `context`: only include if there are org-level signals, notable events, or cross-cutting themes.
- For `decisions`: only include if a clear decision was made (not just discussed).
- Format all `content` values as clean markdown suitable for a notes file.

Rules for `action_items`:
- Only extract clear, committed actions — not vague todos or "we should..."
- Owner should be "me" if it's the manager's action, otherwise the person's name.
- If no clear action items, return an empty array.

If the input contains a date, use it. Otherwise omit dates from content.
"""


def _slugify(text: str) -> str:
    """Convert a display name or title to a lowercase_underscore file slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:50]


def detect_synthesis(text: str) -> dict | None:
    """
    Return parsed JSON if the input is a synthesis file (daily or weekly),
    otherwise return None.

    Synthesis files have the shape: {"start_date": ..., "topics": [...]}
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "topics" in data and isinstance(data["topics"], list):
        return data
    return None


def parse_synthesis(data: dict) -> dict:
    """
    Convert a synthesis JSON directly into the extraction format without calling Claude.

    Works for both daily_synthesis.json and weekly_synthesis.json — same schema.
    """
    start = data.get("start_date", "")
    end = data.get("end_date", "")
    date_range = f"{start} to {end}" if start and end and start != end else (start or end)
    topics = data.get("topics", [])

    writes = []
    people_map: dict[str, tuple[str, list[str]]] = {}  # alias -> (display_name, [content_blocks])

    for topic in topics:
        topic_name = topic.get("topic", "Unknown")
        slug = _slugify(topic_name)
        summary = topic.get("summary", "")
        blockers = topic.get("blockers", [])
        risks = topic.get("risks", [])
        open_questions = topic.get("open_questions", [])
        people = topic.get("people_involved", [])

        # Build project file entry
        lines = [f"## {date_range}\n", f"{summary}\n"]
        if blockers:
            lines += ["**Blockers:**"] + [f"- {b}" for b in blockers] + [""]
        if risks:
            lines += ["**Risks:**"] + [f"- {r}" for r in risks] + [""]
        if open_questions:
            lines += ["**Open questions:**"] + [f"- {q}" for q in open_questions] + [""]
        if people:
            lines.append(f"**Key people:** {', '.join(p['name'] for p in people if p.get('name'))}")

        writes.append({"key": f"projects/{slug}", "content": "\n".join(lines)})

        # Accumulate per-person entries across topics
        for person in people:
            name = person.get("name", "").strip()
            if not name:
                continue
            alias = _slugify(name)
            contribs = person.get("contributions", [])
            block = f"## {date_range} — {topic_name}\n" + "\n".join(f"- {c}" for c in contribs)
            if alias not in people_map:
                people_map[alias] = (name, [])
            people_map[alias][1].append(block)

    # Write one file per person (all their topic contributions combined)
    for alias, (name, blocks) in people_map.items():
        writes.append({"key": f"people/{alias}", "content": "\n\n".join(blocks)})

    # Write a context entry summarising the period
    context_lines = [f"## {date_range}\n"]
    for topic in topics:
        context_lines.append(f"**{topic.get('topic', '')}:** {topic.get('summary', '')}\n")
    writes.append({"key": "context", "content": "\n".join(context_lines)})

    n_people = len(people_map)
    return {
        "summary": f"Synthesis {date_range}: {len(topics)} topics, {n_people} people — parsed directly from structured JSON.",
        "writes": writes,
        "action_items": [],
    }


def parse_args():
    p = argparse.ArgumentParser(
        description="Seed manager memory from raw input data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    source = p.add_mutually_exclusive_group()
    source.add_argument("--file", metavar="PATH", help="Path to a single input file")
    source.add_argument("--dir", metavar="PATH", help="Directory of input files (*.txt, *.md)")
    source.add_argument("--text", metavar="TEXT", help="Inline text to process")
    p.add_argument("--dry-run", action="store_true", help="Show what would be written without writing")
    p.add_argument("--verbose", action="store_true", help="Print Claude's full extraction output")
    return p.parse_args()


def read_inputs(args) -> list[tuple[str, str]]:
    """Return list of (label, text) pairs to process."""
    inputs = []

    if args.text:
        inputs.append(("inline text", args.text))

    elif args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: file not found: {path}")
            sys.exit(1)
        inputs.append((path.name, path.read_text(encoding="utf-8")))

    elif args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"Error: not a directory: {d}")
            sys.exit(1)
        files = sorted(d.glob("*.txt")) + sorted(d.glob("*.md")) + sorted(d.glob("*.json"))
        if not files:
            print(f"No .txt, .md, or .json files found in {d}")
            sys.exit(1)
        for f in files:
            if f.name.startswith("_"):
                continue  # skip templates
            inputs.append((f.name, f.read_text(encoding="utf-8")))

    else:
        # Read from stdin
        if sys.stdin.isatty():
            print("Paste your input below, then press Ctrl+D (or Ctrl+Z on Windows):\n")
        text = sys.stdin.read()
        if text.strip():
            inputs.append(("stdin", text))

    return inputs


def chunk_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def extract_with_claude(
    client: anthropic.Anthropic,
    config: Config,
    text: str,
    label: str,
) -> dict:
    """Call Claude to extract structured data from raw text."""
    response = client.messages.create(
        model=config.model,
        max_tokens=4096,
        system=EXTRACT_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Input label: {label}\n\n---\n\n{text}",
        }],
    )

    raw = "".join(
        block.text for block in response.content if hasattr(block, "text")
    ).strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)


def apply_extraction(extracted: dict, dry_run: bool, verbose: bool) -> dict[str, int]:
    """Write extracted data to memory files. Returns counts of writes."""
    counts = {"files": 0, "action_items": 0}

    if verbose:
        print(f"  Extraction: {extracted.get('summary', '?')}")

    for write in extracted.get("writes", []):
        key = write.get("key", "").strip()
        content = write.get("content", "").strip()
        if not key or not content:
            continue

        if dry_run:
            print(f"  [DRY-RUN] would write to: {key}")
            print(f"            {content[:120].replace(chr(10), ' ')}...")
        else:
            result = memory_store.update_memory(key, content)
            print(f"  wrote → {key}")
            if verbose:
                print(f"           {result}")
        counts["files"] += 1

    ai_items = extracted.get("action_items", [])
    if ai_items:
        if dry_run:
            print(f"  [DRY-RUN] would add {len(ai_items)} action item(s):")
            for item in ai_items:
                print(f"            • {item.get('title', '?')}")
        else:
            patch = {"add": ai_items}
            result = memory_store.update_memory("action_items", patch)
            print(f"  action items → {result}")
        counts["action_items"] += len(ai_items)

    return counts


def merge_extractions(extractions: list[dict]) -> dict:
    """Merge multiple extraction results into one (for chunked input)."""
    merged = {"summary": "", "writes": [], "action_items": []}
    summaries = []
    seen_keys: dict[str, list[str]] = {}

    for ext in extractions:
        if ext.get("summary"):
            summaries.append(ext["summary"])
        for write in ext.get("writes", []):
            key = write.get("key", "")
            content = write.get("content", "")
            if key not in seen_keys:
                seen_keys[key] = []
            seen_keys[key].append(content)
        merged["action_items"].extend(ext.get("action_items", []))

    # Combine content for the same key
    for key, contents in seen_keys.items():
        merged["writes"].append({
            "key": key,
            "content": "\n\n".join(contents),
        })

    merged["summary"] = " ".join(summaries)
    return merged


def process_input(
    client: anthropic.Anthropic,
    config: Config,
    label: str,
    text: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    # Fast path: if the input is a synthesis JSON, parse it directly — no Claude call needed
    synthesis_data = detect_synthesis(text)
    if synthesis_data:
        print(f"\nProcessing: {label} [structured synthesis — direct parse]")
        extracted = parse_synthesis(synthesis_data)
        print(f"  Summary: {extracted['summary']}")
        counts = apply_extraction(extracted, dry_run=dry_run, verbose=verbose)
        print(f"  Result: {counts['files']} file write(s), {counts['action_items']} action item(s)")
        return

    # Slow path: unstructured text — send to Claude for extraction
    chunks = chunk_text(text)
    plural = f" ({len(chunks)} chunks)" if len(chunks) > 1 else ""
    print(f"\nProcessing: {label}{plural}")

    extractions = []
    for i, chunk in enumerate(chunks):
        chunk_label = f"{label} (part {i+1}/{len(chunks)})" if len(chunks) > 1 else label
        print(f"  Extracting{' part ' + str(i+1) if len(chunks) > 1 else ''}...", end=" ", flush=True)
        try:
            ext = extract_with_claude(client, config, chunk, chunk_label)
            print("done")
            extractions.append(ext)
        except json.JSONDecodeError as e:
            print(f"failed (JSON parse error: {e})")
            continue
        except Exception as e:
            print(f"failed ({e})")
            continue

    if not extractions:
        print("  No data extracted.")
        return

    extracted = merge_extractions(extractions) if len(extractions) > 1 else extractions[0]

    print(f"  Summary: {extracted.get('summary', '?')}")
    counts = apply_extraction(extracted, dry_run=dry_run, verbose=verbose)
    print(f"  Result: {counts['files']} file write(s), {counts['action_items']} action item(s)")


def main():
    args = parse_args()

    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=config.api_key)
    memory_store.initialize_memory()

    inputs = read_inputs(args)
    if not inputs:
        print("No input provided.")
        sys.exit(1)

    print(f"\n{'='*55}")
    print(f"Memory seeder — {len(inputs)} input(s)")
    if args.dry_run:
        print("DRY-RUN: nothing will be written")
    print(f"{'='*55}")

    total_files = 0
    total_ai = 0

    for label, text in inputs:
        process_input(client, config, label, text, dry_run=args.dry_run, verbose=args.verbose)

    print(f"\n{'='*55}")
    if args.dry_run:
        print("Dry run complete — no files were written.")
    else:
        print("Seeding complete.")
        print("Run `python main.py` and ask about what was just loaded.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
