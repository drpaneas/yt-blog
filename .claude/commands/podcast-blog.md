---
description: Write a pedagogic developer blog post from a PodcastIndex URL
argument-hint: [--episode-id <id>] <podcastindex-url>
disable-model-invocation: true
allowed-tools: Read Write Edit Glob Grep Bash(python3 podcast_transcript_cli.py *) Bash(date +%Y%m%d-%H%M%S)
---

Turn the PodcastIndex URL in `$ARGUMENTS` into a polished pedagogic Markdown blog post.

Follow this workflow exactly.

## 1. Validate the input and locate the local files

- `$ARGUMENTS` may arrive in two forms:
  1. **Interactive:** a PodcastIndex URL (e.g. `podcastindex.org/podcast/<id>` or `podcastindex.org/podcast/<id>?episode=<eid>`) or a raw numeric podcast ID.
  2. **Batch:** a transcript JSON filename followed by a URL and an optional `--episode-id <id>` flag (e.g. `_podcast_transcript_123_slug.json https://example.com/feed --episode-id 123`).
- Accept both forms. If `--episode-id <id>` is present anywhere in `$ARGUMENTS`, extract that numeric ID and use it for filename naming (see Section 5).
- If `$ARGUMENTS` matches neither form, stop and tell the user to run `/podcast-blog <podcastindex-url>` with a valid URL or the batch argument format.
- Locate `podcast_transcript_cli.py` and `pedagogic.md` in the current project.
- Prefer the workspace-root copies if multiple matches exist.
- If either file is missing, stop and report which file is missing.

## 2. Extract the source text

- Run exactly `python3 podcast_transcript_cli.py --json --whisper-model base "$ARGUMENTS"` from the directory that contains `podcast_transcript_cli.py`.
- For URL inputs, `podcast_transcript_cli.py` is the only supported transcript-ingestion path.
- Treat the JSON stdout from that command as the transcript contract for this workflow.
- Read the structured transcript output carefully before drafting anything.
- If the transcript exceeds approximately 30,000 words, summarize the excess portions rather than trying to process the full text. Focus the article on the most substantive segments.
- Keep the article grounded in the transcript.
- Do not add factual claims that are not supported by the source text.
- For strong claims about products, benchmarks, security issues, or other contested points, make it clear that they are the speaker's claims or that they were presented that way in the episode.
- Do not run audio download tools directly, do not try alternative transcription approaches, and do not search for or switch to local audio files as an improvised fallback for URL inputs.
- If transcript extraction fails, is empty, or is too weak to support a real article, stop with a concise error instead of guessing.
- If the structured transcript metadata says `language` is `en`, use the cleaned transcript text directly as the source text for the article.
- If the structured transcript metadata says `language` is not `en`, first convert the cleaned transcript text into clear, faithful English prose, then use that English translation as the source text for outlining and article writing.
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
- Use the `<episode-id>` from the `--episode-id <id>` argument in `$ARGUMENTS` if provided
- Otherwise extract `<episode-id>` from the PodcastIndex URL query parameter `?episode=<eid>` when available
- If no episode ID can be determined from either source, use `podcast-blog-<slug>-<timestamp>.md` (timestamp from `date +%Y%m%d-%H%M%S` when you need a disambiguator)
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

- After the opening `In this post` block (still near the top), include a visible attribution line with the PodcastIndex URL the user passed in `$ARGUMENTS`, for example: `Source: https://podcastindex.org/podcast/...` (use the real URL string, not a placeholder); always keep that source URL present and unchanged in the output (link enrichment is additive only)
- Link enrichment (balanced, not web-research mode): the visible `Source:` PodcastIndex URL is mandatory and unchanged; treat it as the required outbound link to the episode. Add at most about 2 to 4 additional outbound links for the whole article unless the transcript is dominated by clearly distinct canonical entities, and stay conservative rather than linking every proper noun. Add a non-source link only when you can point to one canonical public URL with high confidence from what the transcript states (or from brief, decisive confirmation); if you are not sure, omit the link and keep plain text. Prefer one canonical link per distinct entity; never guess, interpolate, or invent URLs to "cover" mentions. Reliable lookup or browsing tools, when available, may be used sparingly only to confirm a small number of high-signal links you already mean to include, not to expand link coverage; if lookup is unavailable or inconclusive, ship with only the `Source:` line plus any links you were already sure about
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
