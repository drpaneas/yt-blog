import html
import re

_INLINE_TIMESTAMP_RE = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>")
_TAG_RE = re.compile(r"<[^>]+>")
_BRACKETED_CUE_RE = re.compile(r"\[[^\]]+\]")
_SPEAKER_MARKER_RE = re.compile(r"\s*>>\s*")
_LEADING_FILLER_RE = re.compile(r"^(?:uh+|um+|erm+|er+|ah+|hmm+)\b(?:[\s,.-]+)?", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;!?])")
_PUNCT_TOKEN_RE = re.compile(r"[^0-9A-Za-z']+")
_HEADER_PREFIXES = ("WEBVTT", "Kind:", "Language:", "NOTE")


def clean_vtt_text(vtt_text: str) -> str:
    cue_texts = []
    current_lines = []
    in_cue = False

    for raw_line in vtt_text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_lines:
                cue_texts.append(" ".join(current_lines))
                current_lines = []
            in_cue = False
            continue

        if line.startswith(_HEADER_PREFIXES):
            continue

        if "-->" in line:
            in_cue = True
            continue

        if in_cue:
            current_lines.append(line)

    if current_lines:
        cue_texts.append(" ".join(current_lines))

    merged_tokens = []
    merged_keys = []

    for cue_text in cue_texts:
        cleaned = html.unescape(cue_text).replace("\xa0", " ")
        cleaned = _INLINE_TIMESTAMP_RE.sub("", cleaned)
        cleaned = _TAG_RE.sub("", cleaned)
        cleaned = _SPEAKER_MARKER_RE.sub(" ", cleaned)
        cleaned = _BRACKETED_CUE_RE.sub(" ", cleaned)
        cleaned = _LEADING_FILLER_RE.sub("", cleaned)
        cleaned = _SPACE_RE.sub(" ", cleaned).strip()
        cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)

        if not cleaned:
            continue

        cue_tokens = cleaned.split()
        cue_keys = []
        for token in cue_tokens:
            token_key = _PUNCT_TOKEN_RE.sub("", token.lower())
            cue_keys.append(token_key or token.lower())

        max_overlap = min(len(merged_keys), len(cue_keys), 60)
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if merged_keys[-size:] == cue_keys[:size]:
                overlap = size
                break

        merged_tokens.extend(cue_tokens[overlap:])
        merged_keys.extend(cue_keys[overlap:])

    result = " ".join(merged_tokens)
    result = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", result)
    return result.strip()
