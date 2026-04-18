---
description: Write a pedagogic developer blog post from a podcast transcript
argument-hint: <transcript-file> <episode-url>
disable-model-invocation: true
allowed-tools: Read Write Edit Glob Grep Bash(date +%Y%m%d-%H%M%S)
---

Turn a pre-generated podcast transcript into a polished pedagogic Markdown blog post.

`$ARGUMENTS` contains two space-separated values: the path to a transcript JSON file and the episode source URL.

Follow this workflow exactly.

## 1. Validate the input and locate the local files

- Split `$ARGUMENTS` on the first space into two parts: the transcript file path (first) and the episode URL (second).
- If either part is missing, stop and tell the user to run `/podcast-blog <transcript-file> <episode-url>`.
- Verify the transcript file exists and is readable JSON with at least a `"text"` key (expected shape: `{"text": "...", "language": "en"}`).
- If the file does not exist, is not valid JSON, or lacks a `"text"` key, stop and report the problem.
- Verify the episode URL looks like a plausible URL (starts with `http://` or `https://`). If not, stop and ask the user to provide a valid URL.
- Locate `pedagogic.md` in the current project.
- Prefer the workspace-root copy if multiple matches exist.
- If `pedagogic.md` is missing, stop and report that it is missing.

## 2. Extract the source text

- Read the transcript JSON file directly (do not run `transcript_cli.py` or any external transcript tool).
- Parse the JSON and extract the `"text"` field as the raw transcript.
- Read the structured transcript output carefully before drafting anything.
- Keep the article grounded in the transcript.
- Do not add factual claims that are not supported by the source text.
- For strong claims about products, benchmarks, security issues, or other contested points, make it clear that they are the speaker's claims or that they were presented that way in the episode.
- If the transcript text is empty or too weak to support a real article, stop with a concise error instead of guessing.
- If the JSON includes a `"language"` field set to `en`, use the cleaned transcript text directly as the source text for the article.
- If the `"language"` field is present and not `en`, first convert the cleaned transcript text into clear, faithful English prose, then use that English translation as the source text for outlining and article writing.
- If no `"language"` field is present, assume English.
- Keep the final blog post in English. Do not add a source-language disclosure block or a note that the transcript was translated unless the user explicitly asks for that behavior.

## 3. Read the style reference

- Read `pedagogic.md` carefully.
- Use it as a style reference, not as content to copy.
- Match its teaching-first structure and direct tone.
- Ignore malformed, noisy, or contradictory examples in `pedagogic.md` if they conflict with the explicit writing rules in this command.

## 4. Build a source-specific outline before drafting

Derive a concrete outline that fits this specific source text.

The article must:

- open with a short `In this post` section in pedagogic style (this is the first prose after the H1; the visible `Source:` line comes after this opening, not before it)
- explain the core underlying technology first, because part of the audience may know related tools or ideas but not this exact topic
- retell the original author's point of view as guided lessons, including what problem they saw, why they reacted that way, and what they built or argued for
- end with practical takeaways for developers

Target audience:

- developers with mixed familiarity
- teach without talking down
- assume the reader may have heard of the topic, but may not fully understand it yet

## 5. Write the article

Write a polished Markdown article to the workspace root.

Filename rules:

- Save as `podcast-blog-<slug>-<episode-id>.md` (do not use `podcast-blog-<episode-id>.md` alone as the default name)
- If the transcript filename matches the pattern `_podcast_transcript_<episode-id>.json`, extract `<episode-id>` from it
- If no episode ID can be extracted from the filename, use `podcast-blog-<slug>-<timestamp>.md` (timestamp from `date +%Y%m%d-%H%M%S` when you need a disambiguator)
- After you finalize the article's main title, set the Markdown H1 to that title, then derive `<slug>` from that exact final H1 text:
  - Use a short, lowercase, ASCII-only slug (drop or strip non-ASCII characters rather than inventing transliterations)
  - Replace internal whitespace with single `-` characters
  - Remove or replace characters that are invalid in cross-platform filenames: `\`, `/`, `:`, `*`, `?`, `"`, `<`, `>`, `|` (and any other characters you would not trust in a portable filename)
  - Collapse consecutive `-` into a single `-`
  - Trim leading and trailing `-` and `.` (including repeated trims until stable)
  - Cap the `<slug>` segment at 50 ASCII characters; if longer after sanitization, truncate from the right until it fits
- If sanitization yields an empty slug, use `post` as the slug
- If the target filename already exists, append `-2`, `-3`, and so on immediately before `.md` until the name is unique; do not overwrite

Writing rules:

- After the opening `In this post` block (still near the top), include a visible attribution line with the episode URL the user passed in `$ARGUMENTS`, for example: `Source: https://...` (use the real URL string, not a placeholder); always keep that source URL present and unchanged in the output (link enrichment is additive only)
- Link enrichment (balanced, not web-research mode): the visible `Source:` episode URL is mandatory and unchanged; treat it as the required outbound link to the episode. Add at most about 2 to 4 additional outbound links for the whole article unless the transcript is dominated by clearly distinct canonical entities, and stay conservative rather than linking every proper noun. Add a non-source link only when you can point to one canonical public URL with high confidence from what the transcript states (or from brief, decisive confirmation); if you are not sure, omit the link and keep plain text. Prefer one canonical link per distinct entity; never guess, interpolate, or invent URLs to "cover" mentions. Reliable lookup or browsing tools, when available, may be used sparingly only to confirm a small number of high-signal links you already mean to include, not to expand link coverage; if lookup is unavailable or inconclusive, ship with only the `Source:` line plus any links you were already sure about
- Niche or geeky references (proper nouns readers may not know): on first mention, you may add one short clause that ties the term to this article only using what the transcript supports or a safe, minimal public gloss (for example "a Linux distro" or "a Ruby version manager") without mini-essays, speculation, or tone shifts; skip the clause if the source does not give enough to anchor it; keep the default voice teaching-first and magazine-like, using extra flavor only where it sharpens clarity or adds human texture without drifting into a different register
- Quotes: use quotation marks only when the exact wording materially clarifies a technical point or strengthens a line of argument that paraphrase would weaken; do not quote mainly for punch, vibe, or rhetorical flourish. Cap total quoted sentences for the whole article at roughly 3 to 5 unless the transcript is unusually built around repeated verbatim refrains; keep quotes sparse within sections (about one strong quote per major section at most); avoid stacking multiple quotes or rhetorical devices in the same few sentences
- Use short sections, direct explanations, and concrete examples
- Translate the source author's opinions into teachable ideas without losing the author's voice
- Keep jargon when it is useful, but explain it on first mention
- Use a guided explainer structure rather than a bare summary
- Do not use ASCII art boxes (e.g. `+----+` borders) for any section including the "In this post" summary; use plain Markdown bullet lists instead
- Do not use Mermaid
- Do not use `graph LR`
- Review the draft like an experienced editor-in-chief from a serious technical magazine
- If a section feels too thin, expand it so the article reads like a real narrative feature, not just notes
- Do one final tone pass and, if it helps, add a slightly sharper and drier edge in an editorial, measured voice, keeping it professional and not rant-led
- Do not turn the output into generic documentation about the process; write the article itself

## 6. Optional illustrations

- If your runtime supports image generation, you may create 1 to 3 original monochrome technical-comic PNG illustrations with a dry explainer feel and embed them near the relevant sections
- Do not imitate `xkcd` or any named artist directly
- If image generation is unavailable, skip images entirely without blocking the article

## 7. Final response

- Tell the user which file you wrote
- Mention whether images were generated or skipped
