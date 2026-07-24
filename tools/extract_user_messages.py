"""Mechanical extract: user messages only from Cursor agent transcripts.

No LLM. No interpretation. Parse JSONL, keep role=user text, write one dump + index.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


PROJECTS_ROOT = Path.home() / ".cursor" / "projects"
OUT_DIR = Path(__file__).resolve().parents[1] / ".cursor" / "corpus"
DUMP_PATH = OUT_DIR / "user-messages-only.md"
INDEX_PATH = OUT_DIR / "user-messages-index.json"
USER_QUERY_RE = re.compile(
    r"<user_query>\s*(.*?)\s*</user_query>",
    re.DOTALL | re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(
    r"<timestamp>\s*(.*?)\s*</timestamp>",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class UserMessage:
    project: str
    conversation_id: str
    line_no: int
    timestamp: str
    text: str


def iter_parent_jsonl(projects_root: Path) -> Iterator[tuple[str, Path]]:
    if not projects_root.is_dir():
        raise FileNotFoundError(
            f"projects root missing: {projects_root}. "
            "Expected Cursor projects under ~/.cursor/projects."
        )
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue
        transcripts = project_dir / "agent-transcripts"
        if not transcripts.is_dir():
            continue
        for jsonl in transcripts.rglob("*.jsonl"):
            if "subagents" in jsonl.parts:
                continue
            yield project_dir.name, jsonl


def extract_text_from_message(message: object) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def normalize_user_text(raw: str) -> tuple[str, str]:
    timestamp_match = TIMESTAMP_RE.search(raw)
    timestamp = timestamp_match.group(1).strip() if timestamp_match else ""
    query_match = USER_QUERY_RE.search(raw)
    if query_match:
        return timestamp, query_match.group(1).strip()
    cleaned = TIMESTAMP_RE.sub("", raw).strip()
    return timestamp, cleaned


def extract_from_jsonl(project: str, path: Path) -> list[UserMessage]:
    conversation_id = path.stem
    out: list[UserMessage] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("role") != "user":
                continue
            raw = extract_text_from_message(row.get("message"))
            if not raw:
                continue
            timestamp, text = normalize_user_text(raw)
            if not text:
                continue
            out.append(
                UserMessage(
                    project=project,
                    conversation_id=conversation_id,
                    line_no=line_no,
                    timestamp=timestamp,
                    text=text,
                )
            )
    return out


def write_dump(messages: list[UserMessage], dump_path: Path) -> None:
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# user-messages-only",
        "",
        "Mechanical extract. Role=user only. No assistant text. No interpretation.",
        "",
    ]
    current_key = ""
    msg_index = 0
    for msg in messages:
        key = f"{msg.project}/{msg.conversation_id}"
        if key != current_key:
            current_key = key
            lines.append(f"## {key}")
            lines.append("")
        msg_index += 1
        meta = f"### U{msg_index:05d} | line={msg.line_no}"
        if msg.timestamp:
            meta = f"{meta} | {msg.timestamp}"
        lines.append(meta)
        lines.append("")
        lines.append(msg.text)
        lines.append("")
        lines.append("---")
        lines.append("")
    dump_path.write_text("\n".join(lines), encoding="utf-8")


def write_index(
    messages: list[UserMessage],
    conversations_scanned: int,
    index_path: Path,
) -> None:
    by_project: dict[str, int] = {}
    by_conversation: dict[str, int] = {}
    for msg in messages:
        by_project[msg.project] = by_project.get(msg.project, 0) + 1
        conv = f"{msg.project}/{msg.conversation_id}"
        by_conversation[conv] = by_conversation.get(conv, 0) + 1
    payload = {
        "source_root": str(PROJECTS_ROOT),
        "conversations_scanned": conversations_scanned,
        "user_messages": len(messages),
        "projects_with_user_messages": len(by_project),
        "messages_by_project": dict(sorted(by_project.items(), key=lambda x: (-x[1], x[0]))),
        "top_conversations_by_message_count": dict(
            sorted(by_conversation.items(), key=lambda x: (-x[1], x[0]))[:50]
        ),
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    all_messages: list[UserMessage] = []
    scanned = 0
    for project, path in iter_parent_jsonl(PROJECTS_ROOT):
        scanned += 1
        all_messages.extend(extract_from_jsonl(project, path))
    write_dump(all_messages, DUMP_PATH)
    write_index(all_messages, scanned, INDEX_PATH)
    print(
        json.dumps(
            {
                "conversations_scanned": scanned,
                "user_messages": len(all_messages),
                "dump": str(DUMP_PATH),
                "index": str(INDEX_PATH),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
