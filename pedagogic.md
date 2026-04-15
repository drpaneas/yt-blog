# Pedagogic Writing Style Guide

Use this file as a style reference for blog posts generated from transcripts.

The goal is not to sound academic. The goal is to teach clearly, keep the reader moving, and explain enough that a developer with mixed familiarity can follow without feeling talked down to.

## Audience

Assume the reader:

- is technical
- may know adjacent tools or ideas
- may not know this exact topic well
- wants the point quickly, but still wants real explanation

## Required article shape

Every article should follow this broad structure:

1. H1 title
2. `## In this post`
3. visible `Source:` line near the top
4. first concept section that explains the core technology or idea
5. guided lesson sections that walk through the speaker's argument
6. practical takeaways for developers

## In this post

Start with a short orientation block so the reader knows what they are about to learn.

Good pattern:

```text
## In this post

What you'll learn:
+----------------------------------------------+
|  - Core idea behind the topic                |
|  - Why the speaker cared about it            |
|  - What developers can take away             |
+----------------------------------------------+
```

Keep this short. It is a map, not the article.

## Core writing principles

- Teach first.
- Explain the core technology before diving into the speaker's opinions.
- Use direct language and short sections.
- Prefer concrete examples over abstract summary.
- Translate opinions into lessons, but keep the speaker's personality visible.
- Keep jargon when it helps precision, but explain it on first mention.

## Tone

Aim for:

- calm
- sharp
- editorial
- readable

Avoid:

- hype
- marketing language
- academic stiffness
- smugness
- ranting for its own sake

A little dryness is good. A little wit is good. The article should still feel measured and professional.

## Quotes

Use quotes when the exact wording earns its place.

Good reasons to quote:

- the speaker compresses an important point into one strong line
- the exact wording carries voice that paraphrase would flatten
- the line helps the article turn a corner

Bad reasons to quote:

- the line is merely spicy
- the quote repeats what you already explained
- you are using quotes to avoid analysis

Keep quotes sparse. The article should mostly stay in its own voice.

## Links

Always keep the source video link.

For additional links:

- link only high-signal references
- prefer one canonical link per thing
- skip a link if you are not confident
- do not turn the article into a directory of URLs

## Niche references

When a transcript mentions something niche or geeky, add one short clause on first mention if it helps the reader.

Example:

- weak: `He uses Omakub.`
- better: `He uses Omakub, a packaged Linux desktop setup aimed at developers.`

Do not turn these into mini essays.

## Visual structure

ASCII boxes are welcome when they clarify a comparison or workflow.

Example:

```text
Old workflow:
+----------------------------------------------+
|  Human does every step by hand               |
+----------------------------------------------+

New workflow:
+----------------------------------------------+
|  Human sets direction, tool does first pass  |
+----------------------------------------------+
```

Do not use Mermaid.
Do not use `graph LR`.

## What to avoid

- generic "this is important" filler
- unexplained buzzwords
- too many quotes in one section
- too many rhetorical tricks in one paragraph
- pretending weak evidence is strong evidence
- turning transcript facts into universal truths without saying whose claim it is

## Final check

Before calling the article done, ask:

- Did I explain the topic before judging it?
- Did I help the reader learn something concrete?
- Is the structure easy to scan?
- Are the quotes earned?
- Are the links useful and restrained?
- Does this sound like a real article instead of notes glued together?
