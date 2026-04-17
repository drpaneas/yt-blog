import argparse
import logging
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from feed_checker import fetch_new_videos
from hugo_formatter import add_hugo_front_matter
from relevance_filter import is_ai_related
from state_manager import StateManager

STATE_DIR = Path.home() / ".youtube-blog-automation"
LOG_FILE = STATE_DIR / "automation.log"


def load_config(config_path: Path) -> dict:
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    paths = raw.get("paths", {})
    hugo = raw.get("hugo", {})
    llmwiki_raw = paths.get("llmwiki_dir")
    return {
        "blog_repo": Path(paths["blog_repo"]).expanduser().resolve(),
        "blog_content_dir": paths.get("blog_content_dir", "content/post"),
        "blog_branch": paths.get("blog_branch", "master"),
        "youtube_repo_dir": Path(paths["youtube_repo_dir"]).expanduser().resolve(),
        "llmwiki_dir": Path(llmwiki_raw).expanduser().resolve() if llmwiki_raw else None,
        "hugo_categories": hugo.get("categories", ["youtube"]),
        "hugo_tags": hugo.get("tags", ["ai", "youtube"]),
        "channels": raw.get("channel", []),
    }


def setup_logging(verbose: bool = False) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [autopublish] %(levelname)s: %(message)s",
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


def generate_blog_post(video_url: str, youtube_repo: Path) -> Path | None:
    logger = logging.getLogger(__name__)
    before = set(youtube_repo.glob("youtube-blog-*.md"))
    result = subprocess.run(
        [
            "claude", "-p", f"/youtube-blog {video_url}",
            "-d", str(youtube_repo),
            "--dangerously-skip-permissions",
            "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(python3 transcript_cli.py *),Bash(date +*)",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    logger.debug("claude stdout:\n%s", result.stdout)
    logger.debug("claude stderr:\n%s", result.stderr)
    if result.returncode != 0:
        logger.error("Blog generation failed (exit %d): %s", result.returncode, result.stderr)
        return None
    after = set(youtube_repo.glob("youtube-blog-*.md"))
    new_files = after - before
    if not new_files:
        logger.error("Blog generation produced no new file")
        return None
    return max(new_files, key=lambda p: p.stat().st_mtime)


def push_blog_repo(blog_repo: Path, content_dir: str, titles: list[str]) -> bool:
    try:
        subprocess.run(
            ["git", "add", content_dir + "/"],
            cwd=blog_repo,
            check=True,
            capture_output=True,
        )
        msg = "Add blog posts: " + ", ".join(titles)
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=blog_repo,
            check=True,
            capture_output=True,
        )
        # TODO: re-enable push when ready
        # subprocess.run(
        #     ["git", "push"],
        #     cwd=blog_repo,
        #     check=True,
        #     capture_output=True,
        # )
        return True
    except subprocess.CalledProcessError as exc:
        logging.error("Git commit failed: %s", exc.stderr)
        return False


def update_wiki(filename: str, llmwiki_dir: Path) -> None:
    logger = logging.getLogger(__name__)
    ingest_prompt = (
        f"I just added {filename} to the raw folder. "
        "Read it and update the wiki"
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

    lint_prompt = "please lint the wiki and fix any issues you find"
    try:
        result = subprocess.run(
            [
                "claude", "-p", lint_prompt,
                "-d", str(llmwiki_dir),
                "--dangerously-skip-permissions",
                "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(date +*)",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        logger.debug("Wiki lint stdout:\n%s", result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.error("Wiki lint failed: %s", exc)


def _find_existing_blog(video_id: str, youtube_repo: Path) -> Path | None:
    matches = list(youtube_repo.glob(f"youtube-blog-*-{video_id}.md"))
    if matches:
        return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def _extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path.rstrip("/") == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        for prefix in ("/shorts/", "/live/", "/embed/"):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix):].split("/")[0] or None
    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/").split("/")[0] or None
    return None


def run_single(config_path: Path, video_url: str, force: bool = False) -> int:
    config = load_config(config_path)
    state = StateManager(STATE_DIR)
    logger = logging.getLogger(__name__)

    blog_repo = config["blog_repo"]
    blog_content_dir = config["blog_content_dir"]
    blog_branch = config["blog_branch"]
    llmwiki_dir = config["llmwiki_dir"]
    youtube_repo = config["youtube_repo_dir"]

    vid = _extract_video_id(video_url)
    if not vid:
        logger.error("Could not extract video ID from URL: %s", video_url)
        return 1

    if state.is_seen(vid) and not force:
        logger.info("[%s] Already processed, skipping. Use --force to reprocess.", vid)
        return 0

    try:
        verify_blog_repo(blog_repo, blog_branch)
    except RuntimeError as exc:
        logger.error("Blog repo check failed: %s", exc)
        return 1

    blog_path = _find_existing_blog(vid, youtube_repo)
    if blog_path is not None:
        logger.info("[%s] Found existing blog file: %s, skipping generation", vid, blog_path.name)
    else:
        logger.info("[%s] Generating blog post for: %s", vid, video_url)
        blog_path = generate_blog_post(video_url, youtube_repo)
        if blog_path is None:
            logger.error("[%s] Blog generation failed", vid)
            return 1

    has_front_matter = blog_path.read_text(encoding="utf-8").startswith("+++\n")
    if has_front_matter:
        logger.info("[%s] Hugo front matter already present, skipping", vid)
        lines = blog_path.read_text(encoding="utf-8").split("\n")
        extracted_title = blog_path.stem
        for line in lines:
            if line.startswith("title = "):
                extracted_title = line.split('"')[1] if '"' in line else blog_path.stem
                break
    else:
        logger.info("[%s] Adding Hugo front matter to %s", vid, blog_path.name)
        extracted_title = add_hugo_front_matter(
            blog_path,
            categories=config["hugo_categories"],
            tags=config["hugo_tags"],
        )

    dest = blog_repo / blog_content_dir / blog_path.name
    if dest.exists():
        logger.info("[%s] Already in blog repo, skipping copy", vid)
    else:
        logger.info("[%s] Copying to blog repo: %s", vid, blog_path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blog_path, dest)

    if llmwiki_dir is not None:
        wiki_dest = llmwiki_dir / "raw" / blog_path.name
        if wiki_dest.exists():
            logger.info("[%s] Already in LLM wiki raw, skipping copy", vid)
        else:
            logger.info("[%s] Copying to LLM wiki raw: %s", vid, blog_path.name)
            wiki_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(blog_path, wiki_dest)
            logger.info("[%s] Updating wiki...", vid)
            update_wiki(blog_path.name, llmwiki_dir)

    logger.info("Pushing to blog repo...")
    if not push_blog_repo(blog_repo, blog_content_dir, [extracted_title]):
        logger.error("Git push failed - will not mark as seen")
        return 1

    state.mark_seen(vid, {
        "title": extracted_title,
        "filename": blog_path.name,
        "channel": "manual",
        "published": True,
    })
    logger.info("[%s] Done! Published: %s", vid, extracted_title)
    return 0


def run(config_path: Path, dry_run: bool = False) -> int:
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

    logger.info("Polling RSS feeds for %d channels...", len(config["channels"]))
    all_videos = fetch_new_videos(config["channels"])
    logger.info("Found %d total videos across all channels", len(all_videos))

    candidates = [v for v in all_videos if not state.is_seen(v["video_id"])]
    logger.info("New (unseen) videos: %d", len(candidates))

    if not candidates:
        logger.info("Nothing new to process.")
        return 0

    stats = {"skipped_irrelevant": 0, "failed": 0}
    published_titles = []
    published_entries = []

    for video in candidates:
        vid = video["video_id"]
        title = video["title"]
        url = video["url"]
        logger.info("[%s] Checking relevance: %s", vid, title)

        if dry_run:
            logger.info("[%s] [DRY RUN] Would check relevance for: %s (%s)", vid, title, url)
            continue

        relevant = is_ai_related(title)
        if relevant is None:
            logger.warning("[%s] Relevance check failed, skipping for retry", vid)
            stats["failed"] += 1
            continue
        if not relevant:
            logger.info("[%s] Not AI-related, skipping: %s", vid, title)
            state.mark_seen(vid, {
                "title": title,
                "filename": "",
                "channel": video["channel"],
                "published": False,
            })
            stats["skipped_irrelevant"] += 1
            continue

        logger.info("[%s] AI-related! Processing: %s", vid, title)
        blog_path = _find_existing_blog(vid, youtube_repo)
        if blog_path is not None:
            logger.info("[%s] Found existing blog file: %s, skipping generation", vid, blog_path.name)
        else:
            logger.info("[%s] Generating blog post for: %s", vid, url)
            blog_path = generate_blog_post(url, youtube_repo)
            if blog_path is None:
                logger.error("[%s] Blog generation failed, skipping for retry", vid)
                stats["failed"] += 1
                continue

        has_front_matter = blog_path.read_text(encoding="utf-8").startswith("+++\n")
        if has_front_matter:
            logger.info("[%s] Hugo front matter already present, skipping", vid)
            extracted_title = title
        else:
            logger.info("[%s] Adding Hugo front matter to %s", vid, blog_path.name)
            extracted_title = add_hugo_front_matter(
                blog_path,
                categories=config["hugo_categories"],
                tags=config["hugo_tags"],
            )

        dest = blog_repo / blog_content_dir / blog_path.name
        if dest.exists():
            logger.info("[%s] Already in blog repo, skipping copy", vid)
        else:
            logger.info("[%s] Copying to blog repo: %s", vid, blog_path.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(blog_path, dest)
        published_titles.append(extracted_title)

        if llmwiki_dir is not None:
            wiki_dest = llmwiki_dir / "raw" / blog_path.name
            if wiki_dest.exists():
                logger.info("[%s] Already in LLM wiki raw, skipping copy", vid)
            else:
                logger.info("[%s] Copying to LLM wiki raw: %s", vid, blog_path.name)
                wiki_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(blog_path, wiki_dest)
                logger.info("[%s] Updating wiki...", vid)
                update_wiki(blog_path.name, llmwiki_dir)

        published_entries.append({
            "video_id": vid,
            "title": title,
            "filename": blog_path.name,
            "channel": video["channel"],
        })

    if dry_run:
        return 0

    if published_titles:
        logger.info("Pushing %d new posts to blog repo...", len(published_titles))
        if not push_blog_repo(blog_repo, blog_content_dir, published_titles):
            logger.error("Git push failed - entries will not be marked as seen")
            return 1

        for entry in published_entries:
            state.mark_seen(entry["video_id"], {
                "title": entry["title"],
                "filename": entry["filename"],
                "channel": entry["channel"],
                "published": True,
            })

    logger.info(
        "Run complete: %d channels polled, %d new videos, "
        "%d published, %d skipped (not AI), %d failed",
        len(config["channels"]),
        len(candidates),
        len(published_titles),
        stats["skipped_irrelevant"],
        stats["failed"],
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-publish YouTube video blog posts",
    )
    parser.add_argument(
        "--url",
        help="Process a single YouTube video URL (skips RSS polling and relevance filter)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess a video even if already seen (only with --url)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes (not compatible with --url)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging (shows claude output, detailed diagnostics)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "channels.toml",
        help="Path to channels.toml config file",
    )
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)
    if args.url:
        if args.dry_run:
            parser.error("--dry-run cannot be used with --url")
        return run_single(args.config, args.url, force=args.force)
    if args.force:
        parser.error("--force can only be used with --url")
    return run(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
