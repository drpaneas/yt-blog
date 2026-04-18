import argparse
import json
import logging
import re
import shutil
import subprocess
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hugo_formatter import add_hugo_front_matter
from podcast_fetch import fetch_episodes, fetch_new_episodes, fetch_podcast_info
from podcast_transcript import download_audio, load_whisper_model, transcribe_audio
from state_manager import StateManager

STATE_DIR = Path.home() / ".youtube-blog-automation"
LOG_FILE = STATE_DIR / "automation.log"

_PODCASTINDEX_URL_RE = re.compile(r"podcastindex\.org/podcast/(\d+)")


def load_config(config_path: Path) -> dict:
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    paths = raw.get("paths", {})
    llmwiki_raw = paths.get("llmwiki_dir")
    return {
        "blog_repo": Path(paths["blog_repo"]).expanduser().resolve(),
        "blog_content_dir": paths.get("blog_content_dir", "content/post"),
        "blog_branch": paths.get("blog_branch", "master"),
        "youtube_repo_dir": Path(paths["youtube_repo_dir"]).expanduser().resolve(),
        "llmwiki_dir": Path(llmwiki_raw).expanduser().resolve() if llmwiki_raw else None,
        "max_parallel": raw.get("max_parallel", 1),
        "podcasts": raw.get("podcast", []),
    }


def setup_logging(verbose: bool = False) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [podcast-autopublish] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def verify_blog_repo(blog_repo: Path, expected_branch: str) -> None:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=blog_repo,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    if branch != expected_branch:
        raise RuntimeError(f"Blog repo is on branch '{branch}', expected '{expected_branch}'")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=blog_repo,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise RuntimeError("Blog repo has uncommitted changes")


def _slugify_podcast(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-") or "unknown"


def _find_existing_blog(episode_id: str, *search_dirs: Path) -> Path | None:
    for directory in search_dirs:
        if not directory.exists():
            continue
        matches = list(directory.rglob(f"podcast-blog-*-{episode_id}.md"))
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def _lint_markdown(file_path: Path) -> None:
    logger = logging.getLogger(__name__)
    prompt = (
        f"Read the markdown file at {file_path.name} and fix any markdown "
        "formatting issues in-place. Fix things like: inconsistent heading "
        "levels, missing blank lines around headings/lists/code blocks, "
        "trailing whitespace, and malformed links. Do not change the content, "
        "only fix formatting."
    )
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "-d", str(file_path.parent),
                "--dangerously-skip-permissions",
                "--allowedTools", "Read,Write,Edit",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        logger.debug("Markdown lint stdout:\n%s", result.stdout)
        if result.returncode != 0:
            logger.warning("Markdown lint returned exit code %d", result.returncode)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("Markdown lint failed: %s", exc)


def _generate_ai_tags(file_path: Path) -> list[str]:
    logger = logging.getLogger(__name__)
    prompt = (
        f"Read the blog post at {file_path.name} and return up to 5 short "
        "lowercase tags that describe the content. Return only a comma-separated "
        "list of tags, nothing else. Example: kubernetes, security, llm"
    )
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "-d", str(file_path.parent),
                "--dangerously-skip-permissions",
                "--allowedTools", "Read",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip().split("\n")[0]
            tags = [t.strip().lower() for t in raw.split(",") if t.strip()]
            tags = [re.sub(r"\s+", "-", t) for t in tags]
            tags = [re.sub(r"[^a-z0-9-]", "", t) for t in tags]
            tags = [re.sub(r"-+", "-", t).strip("-") for t in tags]
            tags = [t for t in tags if t][:5]
            logger.info("AI-generated tags: %s", tags)
            return tags
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("AI tag generation failed: %s", exc)
    return []


def push_blog_repo(blog_repo: Path, file_path: Path, titles: list[str]) -> bool:
    logger = logging.getLogger(__name__)
    try:
        rel_path = file_path.relative_to(blog_repo)
        subprocess.run(
            ["git", "add", str(rel_path)],
            cwd=blog_repo,
            check=True,
            capture_output=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=blog_repo,
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            logger.info("Nothing new to commit in blog repo")
            return True
        msg = "Add blog posts: " + ", ".join(titles)
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=blog_repo,
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Git commit failed: %s", exc.stderr)
        return False


def update_wiki(llmwiki_dir: Path) -> None:
    logger = logging.getLogger(__name__)
    ingest_prompt = (
        "I just added new sources to the raw folder. "
        "Read them and update the wiki by ingesting all of them into it."
    )
    try:
        result = subprocess.run(
            [
                "claude", "-p", ingest_prompt,
                "-d", str(llmwiki_dir),
                "--dangerously-skip-permissions",
                "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(date +*)",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        logger.debug("Wiki update stdout:\n%s", result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.error("Wiki update failed: %s", exc)


def _extract_podcast_id(url_or_id: str) -> tuple[str, str | None]:
    if url_or_id.isdigit():
        return url_or_id, None
    match = _PODCASTINDEX_URL_RE.search(url_or_id)
    if not match:
        raise ValueError(
            f"Unsupported URL format: {url_or_id}\n"
            "Only PodcastIndex URLs are supported. Examples:\n"
            "  https://podcastindex.org/podcast/6958769\n"
            "  https://podcastindex.org/podcast/6958769?episode=53451816130\n"
            "  6958769  (raw podcast ID)\n"
            "Find your podcast at https://podcastindex.org and use that URL."
        )
    podcast_id = match.group(1)
    parsed = urlparse(url_or_id)
    episode_param = parse_qs(parsed.query).get("episode", [None])[0]
    return podcast_id, episode_param


def generate_blog_post(
    transcript: dict,
    episode_id: str,
    episode_url: str,
    youtube_repo: Path,
) -> Path | None:
    logger = logging.getLogger(__name__)
    transcript_path = youtube_repo / f"_podcast_transcript_{episode_id}.json"
    transcript_path.write_text(
        json.dumps(transcript, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [
                "claude", "-p",
                f"/podcast-blog {transcript_path.name} {episode_url}",
                "-d", str(youtube_repo),
                "--dangerously-skip-permissions",
                "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(date +*)",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        logger.error("[%s] Blog generation timed out", episode_id)
        return None
    finally:
        transcript_path.unlink(missing_ok=True)
    logger.debug("[%s] claude stdout:\n%s", episode_id, result.stdout)
    logger.debug("[%s] claude stderr:\n%s", episode_id, result.stderr)
    if result.returncode != 0:
        logger.error("[%s] Blog generation failed (exit %d)", episode_id, result.returncode)
        return None
    matches = list(youtube_repo.glob(f"podcast-blog-*-{episode_id}.md"))
    if not matches:
        logger.error("[%s] No output file matching episode ID", episode_id)
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _publish_episode(
    episode_id: str,
    blog_path: Path,
    podcast_name: str,
    blog_repo: Path,
    blog_content_dir: str,
    llmwiki_dir: Path | None,
    title: str,
) -> tuple[str, bool]:
    """Copy blog to blog repo, add front matter, commit, and wiki copy.

    Returns (extracted_title, success).
    """
    logger = logging.getLogger(__name__)
    podcast_slug = _slugify_podcast(podcast_name)

    dest = blog_repo / blog_content_dir / podcast_slug / blog_path.name
    blog_copied = False
    if dest.exists():
        logger.info("[%s] Already in blog repo, skipping copy", episode_id)
    else:
        logger.info("[%s] Copying to blog repo: %s/%s", episode_id, podcast_slug, blog_path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blog_path, dest)
        blog_copied = True

    if not dest.read_text(encoding="utf-8").startswith("+++\n"):
        logger.info("[%s] Linting markdown...", episode_id)
        _lint_markdown(dest)
        logger.info("[%s] Generating AI tags...", episode_id)
        ai_tags = _generate_ai_tags(dest)
        all_tags = [podcast_slug] + ai_tags
        seen = set()
        unique_tags = []
        for t in all_tags:
            if t not in seen:
                seen.add(t)
                unique_tags.append(t)
        logger.info("[%s] Adding Hugo front matter to %s", episode_id, dest.name)
        extracted_title = add_hugo_front_matter(
            dest,
            categories=["podcast"],
            tags=unique_tags,
        )
        blog_copied = True
    else:
        logger.info("[%s] Hugo front matter already present", episode_id)
        extracted_title = title

    if blog_copied:
        logger.info("[%s] Committing to blog repo...", episode_id)
        if not push_blog_repo(blog_repo, dest, [extracted_title]):
            logger.error("[%s] Git commit failed - will not mark as seen", episode_id)
            return extracted_title, False

    if llmwiki_dir is not None:
        wiki_dest = llmwiki_dir / "raw" / blog_path.name
        if wiki_dest.exists():
            logger.info("[%s] Already in LLM wiki raw, skipping copy", episode_id)
        else:
            logger.info("[%s] Copying to LLM wiki raw: %s", episode_id, blog_path.name)
            wiki_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, wiki_dest)
            logger.info("[%s] Updating wiki...", episode_id)
            update_wiki(llmwiki_dir)

    return extracted_title, True


def run_single(
    config_path: Path,
    url: str,
    force: bool = False,
    whisper_model: str = "large-v3",
) -> int:
    config = load_config(config_path)
    state = StateManager(STATE_DIR)
    logger = logging.getLogger(__name__)

    blog_repo = config["blog_repo"]
    blog_content_dir = config["blog_content_dir"]
    blog_branch = config["blog_branch"]
    llmwiki_dir = config["llmwiki_dir"]
    youtube_repo = config["youtube_repo_dir"]

    try:
        podcast_id, episode_param = _extract_podcast_id(url)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    logger.info("Fetching podcast info for ID %s...", podcast_id)
    podcast_info = fetch_podcast_info(podcast_id)
    if not podcast_info:
        logger.error("Could not fetch podcast info for ID %s", podcast_id)
        return 1
    podcast_name = podcast_info.get("title", "unknown")
    podcast_slug = _slugify_podcast(podcast_name)
    logger.info("Podcast: %s (slug: %s)", podcast_name, podcast_slug)

    logger.info("Fetching episodes for podcast %s...", podcast_id)
    episodes = fetch_episodes(podcast_id)
    if not episodes:
        logger.error("No episodes found for podcast %s", podcast_id)
        return 1

    if episode_param:
        matching = [e for e in episodes if e["episode_id"] == episode_param]
        if not matching:
            logger.error(
                "Episode %s not found among recent episodes of podcast %s",
                episode_param, podcast_id,
            )
            return 1
        episode = matching[0]
    else:
        episode = episodes[0]

    eid = episode["episode_id"]
    episode_url = episode.get("episode_url", "")
    logger.info("[%s] Episode: %s", eid, episode["title"])

    if state.is_seen(eid) and not force:
        logger.info("[%s] Already processed, skipping. Use --force to reprocess.", eid)
        return 0

    try:
        verify_blog_repo(blog_repo, blog_branch)
    except RuntimeError as exc:
        logger.error("Blog repo check failed: %s", exc)
        return 1

    if force:
        logger.info("[%s] --force: removing existing files before regenerating", eid)
        for d in [youtube_repo, blog_repo / blog_content_dir / podcast_slug, blog_repo / blog_content_dir]:
            for f in d.glob(f"podcast-blog-*-{eid}.md"):
                logger.info("[%s] Deleting: %s", eid, f)
                f.unlink()
        if llmwiki_dir is not None:
            for f in (llmwiki_dir / "raw").glob(f"podcast-blog-*-{eid}.md"):
                logger.info("[%s] Deleting: %s", eid, f)
                f.unlink()

    search_dirs = [youtube_repo, blog_repo / blog_content_dir / podcast_slug, blog_repo / blog_content_dir]
    if llmwiki_dir is not None:
        search_dirs.append(llmwiki_dir / "raw")
    blog_path = _find_existing_blog(eid, *search_dirs)

    if blog_path is not None:
        logger.info("[%s] Found existing blog file: %s, skipping generation", eid, blog_path.name)
    else:
        model = load_whisper_model(whisper_model)
        if model is None:
            return 1

        audio_dir = Path(tempfile.mkdtemp(prefix="podcast-audio-"))
        try:
            audio_path = download_audio(episode["audio_url"], audio_dir, eid)
            if audio_path is None:
                logger.error("[%s] Audio download failed", eid)
                return 1

            transcript = transcribe_audio(audio_path, model)
            if transcript is None:
                logger.error("[%s] Transcription failed", eid)
                return 1
        finally:
            shutil.rmtree(audio_dir, ignore_errors=True)

        logger.info("[%s] Generating blog post...", eid)
        blog_path = generate_blog_post(transcript, eid, episode_url, youtube_repo)
        if blog_path is None:
            logger.error("[%s] Blog generation failed", eid)
            return 1

    extracted_title, success = _publish_episode(
        eid, blog_path, podcast_name,
        blog_repo, blog_content_dir, llmwiki_dir,
        episode["title"],
    )
    if not success:
        return 1

    state.mark_seen(eid, {
        "title": extracted_title,
        "filename": blog_path.name,
        "podcast": podcast_name,
        "published": True,
    })
    logger.info("[%s] Done! Published: %s", eid, extracted_title)
    return 0


def run(
    config_path: Path,
    dry_run: bool = False,
    whisper_model: str = "large-v3",
) -> int:
    config = load_config(config_path)
    state = StateManager(STATE_DIR)
    logger = logging.getLogger(__name__)

    blog_repo = config["blog_repo"]
    blog_content_dir = config["blog_content_dir"]
    blog_branch = config["blog_branch"]
    llmwiki_dir = config["llmwiki_dir"]
    youtube_repo = config["youtube_repo_dir"]

    if not dry_run:
        try:
            verify_blog_repo(blog_repo, blog_branch)
        except RuntimeError as exc:
            logger.error("Blog repo check failed: %s", exc)
            return 1

    logger.info("Polling PodcastIndex for %d podcasts...", len(config["podcasts"]))
    all_episodes = fetch_new_episodes(config["podcasts"])
    logger.info("Found %d total episodes across all podcasts", len(all_episodes))

    candidates = [e for e in all_episodes if not state.is_seen(e["episode_id"])]
    logger.info("New (unseen) episodes: %d", len(candidates))

    if not candidates:
        logger.info("Nothing new to process.")
        return 0

    stats = {"failed": 0, "published": 0}

    approved = []
    for episode in candidates:
        eid = episode["episode_id"]
        title = episode["title"]

        if dry_run:
            logger.info(
                "[%s] [DRY RUN] Would process: %s (podcast: %s)",
                eid, title, episode["podcast_name"],
            )
            continue

        approved.append(episode)

    if dry_run:
        return 0

    if not approved:
        logger.info("No new episodes to process.")
        return 0

    # Phase 1: Find existing blogs or transcribe + generate
    generation_results: dict[str, Path] = {}
    episodes_needing_generation: list[dict] = []

    for episode in approved:
        eid = episode["episode_id"]
        podcast_slug = _slugify_podcast(episode["podcast_name"])
        search_dirs = [youtube_repo, blog_repo / blog_content_dir / podcast_slug, blog_repo / blog_content_dir]
        if llmwiki_dir is not None:
            search_dirs.append(llmwiki_dir / "raw")
        existing = _find_existing_blog(eid, *search_dirs)
        if existing is not None:
            logger.info("[%s] Found existing blog file: %s, skipping generation", eid, existing.name)
            generation_results[eid] = existing
        else:
            episodes_needing_generation.append(episode)

    if episodes_needing_generation:
        logger.info("Loading Whisper model for %d episodes...", len(episodes_needing_generation))
        model = load_whisper_model(whisper_model)
        if model is None:
            logger.error("Cannot load Whisper model, aborting")
            return 1

        # Transcribe sequentially (Whisper needs ~10 GB RAM)
        transcripts: dict[str, dict] = {}
        audio_dir = Path(tempfile.mkdtemp(prefix="podcast-audio-"))
        try:
            for episode in episodes_needing_generation:
                eid = episode["episode_id"]
                logger.info("[%s] Downloading audio...", eid)
                audio_path = download_audio(episode["audio_url"], audio_dir, eid)
                if audio_path is None:
                    logger.error("[%s] Audio download failed, skipping", eid)
                    stats["failed"] += 1
                    continue

                logger.info("[%s] Transcribing...", eid)
                transcript = transcribe_audio(audio_path, model)
                if transcript is None:
                    logger.error("[%s] Transcription failed, skipping", eid)
                    stats["failed"] += 1
                    continue

                transcripts[eid] = transcript
                audio_path.unlink(missing_ok=True)
        finally:
            shutil.rmtree(audio_dir, ignore_errors=True)

        del model

        # Generate blog posts (parallel via ThreadPoolExecutor)
        episodes_with_transcripts = [
            e for e in episodes_needing_generation if e["episode_id"] in transcripts
        ]
        max_parallel = config["max_parallel"]
        if episodes_with_transcripts:
            logger.info(
                "Generating %d blog posts (max %d parallel)...",
                len(episodes_with_transcripts),
                max_parallel,
            )
            with ThreadPoolExecutor(max_workers=max_parallel) as pool:
                futures = {
                    pool.submit(
                        generate_blog_post,
                        transcripts[e["episode_id"]],
                        e["episode_id"],
                        e.get("episode_url", ""),
                        youtube_repo,
                    ): e
                    for e in episodes_with_transcripts
                }
                for future in as_completed(futures):
                    episode = futures[future]
                    eid = episode["episode_id"]
                    try:
                        blog_path = future.result()
                    except Exception as exc:
                        logger.error("[%s] Blog generation raised: %s", eid, exc)
                        blog_path = None
                    if blog_path is None:
                        logger.error("[%s] Blog generation failed, skipping for retry", eid)
                        stats["failed"] += 1
                    else:
                        logger.info("[%s] Blog generated: %s", eid, blog_path.name)
                        generation_results[eid] = blog_path

    # Phase 2: Publish (sequential)
    for episode in approved:
        eid = episode["episode_id"]
        blog_path = generation_results.get(eid)
        if blog_path is None:
            continue

        extracted_title, success = _publish_episode(
            eid, blog_path, episode["podcast_name"],
            blog_repo, blog_content_dir, llmwiki_dir,
            episode["title"],
        )
        if not success:
            stats["failed"] += 1
            continue

        state.mark_seen(eid, {
            "title": extracted_title,
            "filename": blog_path.name,
            "podcast": episode["podcast_name"],
            "published": True,
        })
        stats["published"] += 1

    logger.info(
        "Run complete: %d podcasts polled, %d new episodes, "
        "%d published, %d failed",
        len(config["podcasts"]),
        len(candidates),
        stats["published"],
        stats["failed"],
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-publish podcast episode blog posts",
    )
    parser.add_argument("--url", help="Process a single podcast episode URL")
    parser.add_argument(
        "--force", action="store_true",
        help="Reprocess even if already seen (only with --url)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be processed without changes",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).parent / "channels.toml",
        help="Path to channels.toml config file",
    )
    parser.add_argument(
        "--whisper-model", default="large-v3",
        help="Whisper model to use (default: large-v3)",
    )
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)
    if args.url:
        if args.dry_run:
            parser.error("--dry-run cannot be used with --url")
        return run_single(args.config, args.url, force=args.force,
                          whisper_model=args.whisper_model)
    if args.force:
        parser.error("--force can only be used with --url")
    return run(args.config, dry_run=args.dry_run,
               whisper_model=args.whisper_model)


if __name__ == "__main__":
    raise SystemExit(main())
