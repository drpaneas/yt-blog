import re
from datetime import datetime, timezone
from pathlib import Path


def add_hugo_front_matter(
    md_path: Path,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    if categories is None:
        categories = ["youtube"]
    if tags is None:
        tags = ["ai", "youtube"]
    text = md_path.read_text(encoding="utf-8")
    title, body = _extract_title_and_body(text, md_path.stem)
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    cat_str = "[" + ", ".join(f'"{c}"' for c in categories) + "]"
    tag_str = "[" + ", ".join(f'"{t}"' for t in tags) + "]"
    front_matter = (
        f"+++\n"
        f"categories = {cat_str}\n"
        f'date = "{now}"\n'
        f"tags = {tag_str}\n"
        f'title = "{escaped_title}"\n'
        f"+++\n"
    )
    body = body.lstrip("\n")
    result = front_matter + "\n" + body
    md_path.write_text(result, encoding="utf-8")
    return title


def _extract_title_and_body(text: str, fallback_title: str) -> tuple[str, str]:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        match = re.match(r"^#\s+(.+)$", line)
        if match:
            title = match.group(1).strip()
            body = "\n".join(lines[:i] + lines[i + 1:])
            return title, body
    return fallback_title, text
