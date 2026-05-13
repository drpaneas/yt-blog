---
description: Write a pedagogic developer blog post from a YouTube URL, with extracted video frames (code, diagrams, slides)
argument-hint: <youtube-url>
disable-model-invocation: true
allowed-tools: Read Write Edit Glob Grep Bash(python3 transcript_cli.py *) Bash(video-frames *) Bash(frame-at *) Bash(date +%Y%m%d-%H%M%S)
---

Turn the YouTube URL in `$ARGUMENTS` into a polished pedagogic Markdown blog post enriched with visual content extracted from the video.

This command extends `/youtube-blog` with a vision pipeline: it extracts key frames (code screenshots, diagrams, slides) from the video and uses them in the article.

Follow this workflow exactly.

## 1. Validate the input and locate the local files

- Ensure `$ARGUMENTS` looks like a valid YouTube URL.
- Accept common YouTube URL forms such as `youtube.com/watch`, `youtu.be/...`, `m.youtube.com/...`, `youtube.com/shorts/...`, and `youtube.com/live/...`.
- If it is not a usable YouTube URL, stop and tell the user to run `/youtube-eyes <youtube-url>` with a valid URL.
- Locate `transcript_cli.py` and `pedagogic.md` in the current project.
- Prefer the workspace-root copies if multiple matches exist.
- If `transcript_cli.py` or `pedagogic.md` is missing, stop and report which file is missing.
- Verify that `video-frames` and `frame-at` commands are available on PATH (try `video-frames --help`). If not available, warn but continue without frame extraction (degrade to transcript-only mode).

## 2. Extract the source text

- Run exactly `python3 transcript_cli.py --json --allow-non-english "$ARGUMENTS"` from the directory that contains `transcript_cli.py`.
- For URL inputs, `transcript_cli.py` is the only supported transcript-ingestion path.
- Treat the JSON stdout from that command as the transcript contract for this workflow.
- Read the structured transcript output carefully before drafting anything.
- Keep the article grounded in the transcript.
- Do not add factual claims that are not supported by the source text.
- For strong claims about products, benchmarks, security issues, or other contested points, make it clear that they are the speaker's claims or that they were presented that way in the talk.
- Do not run `yt-dlp` directly, do not try alternative extractor arguments, do not retry with different subtitle languages, and do not search for or switch to local `.vtt` files as an improvised fallback for URL inputs.
- If transcript extraction fails, is empty, or is too weak to support a real article, stop with a concise error instead of guessing.
- If the structured transcript metadata says `language` is `en`, use the cleaned transcript text directly as the source text for the article.
- If the structured transcript metadata says `language` is not `en`, first convert the cleaned transcript text into clear, faithful English prose, then use that English translation as the source text for outlining and article writing.
- Keep the final blog post in English. Do not add a source-language disclosure block or a note that the transcript was translated unless the user explicitly asks for that behavior.

## 3. Extract video frames

- Derive the video ID from the YouTube URL (e.g. `Gv2I7qTux7g` from `youtube.com/watch?v=Gv2I7qTux7g`).
- Determine the article's output directory name: `youtube-blog-<slug>-<video-id>` (you will finalize `<slug>` in step 5, so use a temporary slug like `draft` for now; you can rename the directory later).
- Create the output directory at the workspace root.
- Run `video-frames --json --output-dir <output-dir> "$ARGUMENTS"` (uses the installed entry point which has access to the ML dependencies).
- If frame extraction succeeds, read the metadata JSON output. It contains:
  - `total_duration_sec` - total video length
  - `video_path` - path to the downloaded video file (kept in a temp directory for on-demand frame extraction later)
  - `frames` - array of extracted frames, each with `file` (filename), `timestamp_sec` (when in the video), `type` (`code`, `slide`, or `diagram`), and `ocr_text` (extracted text, or null for diagrams)
- Note the `video_path` - you will need it in step 6 to extract additional frames on demand.
- If frame extraction fails (video unavailable, ffmpeg missing, etc.), log a warning and continue without frames. The article will be transcript-only, identical to what `/youtube-blog` produces. Write a flat `.md` file instead of a page bundle.
- Do not retry frame extraction or try alternative approaches if it fails.

## 4. Read the style reference

- Read `pedagogic.md` carefully.
- Use it as a style reference, not as content to copy.
- Match its teaching-first structure and direct tone.
- Ignore malformed, noisy, or contradictory examples in `pedagogic.md` if they conflict with the explicit writing rules in this command.

## 5. Build a source-specific outline before drafting

Derive a concrete outline that fits this specific source text.

The article must:

- open with a short `In this post` section in pedagogic style (this is the first prose after the H1; the visible `Source:` line comes after this opening, not before it)
- explain the core underlying technology first, because part of the audience may know related tools or ideas but not this exact topic
- retell the original author's point of view as guided lessons, including what problem they saw, why they reacted that way, and what they built or argued for
- end with practical takeaways for developers
- note where extracted frames can enhance sections (match frame timestamps proportionally against the transcript's linear flow to place visuals near the right discussion)

Target audience:

- developers with mixed familiarity
- teach without talking down
- assume the reader may have heard of the topic, but may not fully understand it yet

## 6. Write the article

Write a polished Markdown article as `index.md` inside the output directory (Hugo page bundle format).

Filename and directory rules:

- The article lives at `youtube-blog-<slug>-<video-id>/index.md`
- After you finalize the article's main title, set the Markdown H1 to that title, then derive `<slug>` from that exact final H1 text:
  - Use a short, lowercase, ASCII-only slug (drop or strip non-ASCII characters rather than inventing transliterations)
  - Replace internal whitespace with single `-` characters
  - Remove or replace characters that are invalid in cross-platform filenames: `\`, `/`, `:`, `*`, `?`, `"`, `<`, `>`, `|` (and any other characters you would not trust in a portable filename)
  - Collapse consecutive `-` into a single `-`
  - Trim leading and trailing `-` and `.` (including repeated trims until stable)
  - Cap the `<slug>` segment at 50 ASCII characters; if longer after sanitization, truncate from the right until it fits
- If sanitization yields an empty slug, use `post` as the slug
- If no usable video ID can be derived from the URL, use a timestamp from `date +%Y%m%d-%H%M%S` as the disambiguator
- Rename the directory to its final name if the slug changed from the draft name used in step 3
- If the target directory already exists, append `-2`, `-3`, and so on until the name is unique; do not overwrite
- If no frames were extracted (step 3 failed), write a flat `youtube-blog-<slug>-<video-id>.md` file instead of a page bundle

Writing rules:

- After the opening `In this post` block (still near the top), include a visible attribution line with the actual YouTube URL the user passed in `$ARGUMENTS`, for example: `Source: https://...` (use the real URL string, not a placeholder); always keep that source-video URL present and unchanged in the output (link enrichment is additive only)
- Link enrichment (balanced, not web-research mode): the visible `Source:` YouTube URL is mandatory and unchanged; treat it as the required outbound link to the video. Add at most about 2 to 4 additional outbound links for the whole article unless the transcript is dominated by clearly distinct canonical entities, and stay conservative rather than linking every proper noun. Add a non-source link only when you can point to one canonical public URL with high confidence from what the transcript states (or from brief, decisive confirmation); if you are not sure, omit the link and keep plain text. Prefer one canonical link per distinct entity; never guess, interpolate, or invent URLs to "cover" mentions. Reliable lookup or browsing tools, when available, may be used sparingly only to confirm a small number of high-signal links you already mean to include, not to expand link coverage; if lookup is unavailable or inconclusive, ship with only the `Source:` line plus any links you were already sure about
- Niche or geeky references (proper nouns readers may not know, for example `Omakub`): on first mention, you may add one short clause that ties the term to this article only using what the transcript supports or a safe, minimal public gloss (for example "a Linux distro" or "a Ruby version manager") without mini-essays, speculation, or tone shifts; skip the clause if the source does not give enough to anchor it; keep the default voice teaching-first and magazine-like, using extra flavor only where it sharpens clarity or adds human texture without drifting into a different register
- Quotes: use quotation marks only when the exact wording materially clarifies a technical point or strengthens a line of argument that paraphrase would weaken; do not quote mainly for punch, vibe, or rhetorical flourish. Cap total quoted sentences for the whole article at roughly 3 to 5 unless the transcript is unusually built around repeated verbatim refrains; keep quotes sparse within sections (about one strong quote per major section at most); avoid stacking multiple quotes or rhetorical devices in the same few sentences
- **Concrete examples over abstract explanations.** When explaining a behavior, limitation, bug, optimization, or edge case, show a minimal code snippet or observable result first, then keep the explanation brief and directly tied to the observed behavior. Do not write "Kelley showed two large numbers that produce a result off by two" - instead, show the actual numbers and the actual wrong result so the reader can see the problem immediately. Favor minimal reproducible examples, short code snippets, direct observable outcomes, and examples that make the failure obvious. Avoid long theoretical digressions, textbook-style explanations, and abstract descriptions without concrete demonstration.
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

### Frame-aware writing rules

When frames were successfully extracted (step 3), use them to enrich the article:

- **Show, don't narrate.** When the transcript describes code being shown, demonstrated, or run on screen, do NOT paraphrase what the code does in prose. Instead, find the matching frame by timestamp, transcribe the actual code, and present it as a fenced code block. Readers want to see `let x = 1 + 2;`, not "the speaker showed a variable being assigned the sum of one and two." If the transcript says something like "here's an example" or "let's look at this code" or "I'm going to show you," there is almost certainly a frame nearby with the actual code - find it and include it. This is the most important rule: the article should contain the code the speaker showed, not a description of it.
- **Correlating frames to text**: use the frame `timestamp_sec` values proportionally against `total_duration_sec` to estimate where in the transcript each frame belongs. The transcript flows linearly from start to end of the video; a frame at timestamp 600s in a 3600s video corresponds roughly to 1/6 of the way through the transcript.
- **Code frames** (`type: "code"`): prefer using the `ocr_text` to create a fenced code block with the appropriate language tag (e.g. ` ```zig`, ` ```c`). Clean up obvious OCR artifacts in code (misread characters, missing indentation) when the correct code is clear from context. If the OCR text is garbled, incomplete, or clearly wrong, do NOT just embed the screenshot - instead, read the frame image file yourself using the Read tool, visually transcribe the code you see in the image, and write it as a fenced code block. Only embed the screenshot image as a last resort if you genuinely cannot read the code from the image either.
- **Diagram frames** (`type: "diagram"`): read the frame image file yourself using the Read tool to understand what it shows. Prefer reconstructing the content in text form: use ASCII art for flowcharts, box diagrams, or arrow-based visuals; use Markdown tables for tabular content; use bullet lists for hierarchical structures. Only embed the screenshot image if the visual is too complex to reproduce faithfully in text (e.g. photographs, detailed technical schematics, graphs with many data points).
- **Slide frames** (`type: "slide"`): read the frame image file yourself using the Read tool if `ocr_text` is missing or garbled. Reconstruct the slide content as Markdown: use headings for titles, bullet lists for points, tables for comparisons. Embed the screenshot image only if the slide relies on visual layout, color coding, or spatial arrangement that text cannot capture. Skip title slides or slides that just repeat section headings already in the article.
- **Placement**: embed each visual near the paragraph that discusses the same topic. Do not cluster all images at the end or dump them in sequence.
- **On-demand frame extraction** (max 5 additional frames): as you read the transcript and write the article, watch for moments where the speaker narrates something visual that is NOT covered by any existing frame. Cues include: "let me type this," "if I run this," "you can see here," "look at this output," or describing code/results that don't match any nearby frame's OCR text or timestamp. When you identify such a gap, use the `video_path` from `frames.json` and the `frame-at` tool to grab a frame at the estimated timestamp: `frame-at <video_path> <timestamp_sec> <output-dir>/frame-<timestamp>s.png`. Then read the resulting image to transcribe the code or content. This is essential for live-typed code and REPL demos that scene detection misses. Limit on-demand extractions to at most 5 per article - prioritize the most important gaps where visual content is critical to the explanation.
- **Selectivity**: do not embed every frame. Only include frames that genuinely help the reader understand the content. Skip redundant frames, transitional slides, and frames whose content is already fully covered by the article text.
- **Cleanup**: after writing the article:
  1. Delete any frame PNG files from the output directory that are not referenced in the final article.
  2. Delete the video file by running `video-frames --cleanup-video <output-dir>/frames.json`. This safely removes the video (500MB+) and its temp directory.
  3. Delete the `frames.json` metadata file from the output directory (it was only needed during writing).
- Image references use simple relative paths since the article is `index.md` inside the page bundle directory.

## 7. Optional illustrations

- If your runtime supports image generation and no video frames were extracted, you may create 1 to 3 original monochrome technical-comic PNG illustrations with a dry explainer feel and embed them near the relevant sections
- Do not imitate `xkcd` or any named artist directly
- If image generation is unavailable, skip images entirely without blocking the article
- If video frames were successfully extracted, skip generated illustrations - the real screenshots are better

## 8. Final response

- Tell the user which directory and file you wrote (e.g. `youtube-blog-what-happens-...-Gv2I7qTux7g/index.md`)
- Report how many video frames were embedded in the article vs how many were extracted
- Mention whether any frames were deleted as unused
