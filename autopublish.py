import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from feed_checker import fetch_new_videos
from hugo_formatter import add_hugo_front_matter
from publish_utils import (
    DEFAULT_STATE_DIR,
    generate_ai_tags,
    lint_markdown,
    push_blog_repo,
    setup_logging,
    slugify,
    verify_blog_repo,
)
from state_manager import StateManager


def load_config(config_path: Path) -> dict:
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    paths = raw.get("paths", {})
    hugo = raw.get("hugo", {})
    llmwiki_raw = paths.get("llmwiki_dir")
    state_dir_raw = raw.get("state_dir")
    blog_repo_raw = paths.get("blog_repo")
    blog_repo = Path(blog_repo_raw).expanduser().resolve() if blog_repo_raw else None
    return {
        "state_dir": Path(state_dir_raw).expanduser().resolve() if state_dir_raw else DEFAULT_STATE_DIR,
        "blog_repo": blog_repo,
        "blog_content_dir": paths.get("blog_content_dir", "content/post") if blog_repo else None,
        "blog_branch": paths.get("blog_branch", "master") if blog_repo else None,
        "youtube_repo_dir": Path(paths["youtube_repo_dir"]).expanduser().resolve(),
        "llmwiki_dir": Path(llmwiki_raw).expanduser().resolve() if llmwiki_raw else None,
        "hugo_categories": hugo.get("categories", ["youtube"]),
        "hugo_tags": hugo.get("tags", ["ai", "youtube"]),
        "max_parallel": raw.get("max_parallel", 1),
        "channels": raw.get("channel", []),
    }


def _find_blog_output(youtube_repo: Path, video_id: str) -> Path | None:
    """Find a generated blog post by video ID, checking both flat files and page bundles."""
    flat = list(youtube_repo.glob(f"youtube-blog-*-{video_id}.md"))
    bundles = [
        p for p in youtube_repo.glob(f"youtube-blog-*-{video_id}/index.md")
    ]
    candidates = flat + bundles
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def generate_blog_post(
    video_url: str,
    video_id: str,
    youtube_repo: Path,
    use_eyes: bool = False,
) -> Path | None:
    logger = logging.getLogger(__name__)
    if use_eyes:
        command_name = "/youtube-eyes"
        allowed_tools = "Read,Write,Edit,Glob,Grep,Bash(python3 transcript_cli.py *),Bash(python3 video_frames_cli.py *),Bash(date +*)"
        timeout = 1200
    else:
        command_name = "/youtube-blog"
        allowed_tools = "Read,Write,Edit,Glob,Grep,Bash(python3 transcript_cli.py *),Bash(date +*)"
        timeout = 900

    try:
        result = subprocess.run(
            [
                "claude", "-p", f"{command_name} {video_url}",
                "-d", str(youtube_repo),
                "--dangerously-skip-permissions",
                "--allowedTools", allowed_tools,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error("[%s] Blog generation timed out after %ds", video_id, timeout)
        return None
    logger.debug("[%s] claude stdout:\n%s", video_id, result.stdout)
    logger.debug("[%s] claude stderr:\n%s", video_id, result.stderr)
    if result.returncode != 0:
        logger.error("[%s] Blog generation failed (exit %d): %s", video_id, result.returncode, result.stderr)
        return None
    blog_path = _find_blog_output(youtube_repo, video_id)
    if blog_path is None:
        logger.error("[%s] Blog generation produced no file matching video ID", video_id)
        return None
    return blog_path


def _detect_channel_name(video_url: str) -> str:
    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            ["yt-dlp", "--print", "channel", "--skip-download", "--no-warnings", video_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            name = result.stdout.strip().split("\n")[0].strip()
            logger.info("Detected channel name: %s", name)
            return name
        logger.warning("yt-dlp returned no channel name (exit %d): %s", result.returncode, result.stderr.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("Channel detection failed: %s", exc)
    return "manual"


def _find_existing_blog(video_id: str, *search_dirs: Path) -> Path | None:
    for directory in search_dirs:
        if not directory.exists():
            continue
        flat = list(directory.rglob(f"youtube-blog-*-{video_id}.md"))
        bundles = list(directory.rglob(f"youtube-blog-*-{video_id}/index.md"))
        candidates = flat + bundles
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
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


def run_single(config_path: Path, video_url: str, force: bool = False, use_eyes: bool = False) -> int:
    config = load_config(config_path)
    state = StateManager(config["state_dir"], prefix="youtube:")
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

    if blog_repo is not None:
        try:
            verify_blog_repo(blog_repo, blog_branch)
        except RuntimeError as exc:
            logger.error("Blog repo check failed: %s", exc)
            return 1

    logger.info("[%s] Detecting channel name...", vid)
    channel_name = _detect_channel_name(video_url)
    channel_slug = slugify(channel_name)
    logger.info("[%s] Channel: %s (slug: %s)", vid, channel_name, channel_slug)

    if force:
        logger.info("[%s] --force: removing existing files before regenerating", vid)
        for f in youtube_repo.glob(f"youtube-blog-*-{vid}.md"):
            logger.info("[%s] Deleting: %s", vid, f)
            f.unlink()
        for d in youtube_repo.glob(f"youtube-blog-*-{vid}"):
            if d.is_dir():
                logger.info("[%s] Deleting bundle: %s", vid, d)
                shutil.rmtree(d)
        if blog_repo is not None:
            for search_d in [blog_repo / blog_content_dir / channel_slug, blog_repo / blog_content_dir]:
                for f in search_d.glob(f"youtube-blog-*-{vid}.md"):
                    logger.info("[%s] Deleting: %s", vid, f)
                    f.unlink()
                for d in search_d.glob(f"youtube-blog-*-{vid}"):
                    if d.is_dir():
                        logger.info("[%s] Deleting bundle: %s", vid, d)
                        shutil.rmtree(d)
        if llmwiki_dir is not None:
            for f in (llmwiki_dir / "raw").glob(f"youtube-blog-*-{vid}.md"):
                logger.info("[%s] Deleting: %s", vid, f)
                f.unlink()

    search_dirs = [youtube_repo]
    if blog_repo is not None:
        search_dirs.extend([blog_repo / blog_content_dir / channel_slug, blog_repo / blog_content_dir])
    if llmwiki_dir is not None:
        search_dirs.append(llmwiki_dir / "raw")
    blog_path = _find_existing_blog(vid, *search_dirs)
    if blog_path is not None:
        logger.info("[%s] Found existing blog file: %s, skipping generation", vid, blog_path.name)
    else:
        logger.info("[%s] Generating blog post for: %s", vid, video_url)
        blog_path = generate_blog_post(video_url, vid, youtube_repo, use_eyes=use_eyes)
        if blog_path is None:
            logger.error("[%s] Blog generation failed", vid)
            return 1

    if blog_path.name == "index.md":
        extracted_title = blog_path.parent.name
    else:
        extracted_title = blog_path.stem
    is_bundle = blog_path.name == "index.md"
    blog_src_dir = blog_path.parent if is_bundle else None
    blog_copy_name = blog_src_dir.name if is_bundle else blog_path.name

    if blog_repo is not None:
        dest_parent = blog_repo / blog_content_dir / channel_slug
        if is_bundle:
            dest_dir = dest_parent / blog_copy_name
            dest_md = dest_dir / "index.md"
        else:
            dest_dir = None
            dest_md = dest_parent / blog_copy_name

        blog_copied = False
        if dest_md.exists():
            logger.info("[%s] Already in blog repo, skipping copy", vid)
        else:
            logger.info("[%s] Copying to blog repo: %s", vid, blog_copy_name)
            if is_bundle:
                shutil.copytree(blog_src_dir, dest_dir)
            else:
                dest_parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(blog_path, dest_md)
            blog_copied = True

        if not dest_md.read_text(encoding="utf-8").startswith("+++\n"):
            logger.info("[%s] Linting markdown...", vid)
            lint_markdown(dest_md)
            logger.info("[%s] Generating AI tags...", vid)
            ai_tags = generate_ai_tags(dest_md)
            all_tags = list(config["hugo_tags"]) + [channel_slug] + ai_tags
            seen = set()
            unique_tags = []
            for t in all_tags:
                if t not in seen:
                    seen.add(t)
                    unique_tags.append(t)
            logger.info("[%s] Adding Hugo front matter to %s", vid, dest_md.name)
            extracted_title = add_hugo_front_matter(
                dest_md,
                categories=config["hugo_categories"],
                tags=unique_tags,
            )
            blog_copied = True
        else:
            logger.info("[%s] Hugo front matter already present", vid)
            text = dest_md.read_text(encoding="utf-8")
            for line in text.split("\n"):
                m = re.match(r'^title\s*=\s*"(.+)"', line)
                if m:
                    extracted_title = m.group(1)
                    break

        if blog_copied:
            commit_path = dest_dir if is_bundle else dest_md
            logger.info("[%s] Committing to blog repo...", vid)
            if not push_blog_repo(blog_repo, commit_path, [extracted_title]):
                logger.error("[%s] Git commit failed - will not mark as seen", vid)
                return 1
    else:
        text = blog_path.read_text(encoding="utf-8")
        for line in text.split("\n"):
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                extracted_title = m.group(1).strip()
                break

    if llmwiki_dir is not None:
        wiki_src = dest_md if blog_repo is not None else blog_path
        if is_bundle:
            wiki_dest = llmwiki_dir / "raw" / blog_copy_name
            if wiki_dest.exists():
                logger.info("[%s] Already in LLM wiki raw, skipping copy", vid)
            else:
                logger.info("[%s] Copying bundle to LLM wiki raw: %s", vid, blog_copy_name)
                src_dir = dest_dir if blog_repo is not None else blog_src_dir
                shutil.copytree(src_dir, wiki_dest)
        else:
            wiki_dest = llmwiki_dir / "raw" / blog_copy_name
            if wiki_dest.exists():
                logger.info("[%s] Already in LLM wiki raw, skipping copy", vid)
            else:
                logger.info("[%s] Copying to LLM wiki raw: %s", vid, blog_copy_name)
                wiki_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(wiki_src, wiki_dest)

    state.mark_seen(vid, {
        "title": extracted_title,
        "filename": blog_path.name,
        "channel": channel_name,
        "published": True,
    })
    logger.info("[%s] Done! Published: %s", vid, extracted_title)
    return 0


def run(config_path: Path, dry_run: bool = False, use_eyes: bool = False) -> int:
    config = load_config(config_path)
    state = StateManager(config["state_dir"], prefix="youtube:")
    logger = logging.getLogger(__name__)

    blog_repo = config["blog_repo"]
    blog_content_dir = config["blog_content_dir"]
    blog_branch = config["blog_branch"]
    llmwiki_dir = config["llmwiki_dir"]
    youtube_repo = config["youtube_repo_dir"]

    if not dry_run and blog_repo is not None:
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

    stats = {"failed": 0, "published": 0}

    approved = []
    for video in candidates:
        vid = video["video_id"]
        title = video["title"]

        if dry_run:
            logger.info("[%s] [DRY RUN] Would process: %s (%s)", vid, title, video["url"])
            continue

        approved.append(video)

    if dry_run:
        return 0

    if not approved:
        logger.info("No new videos to process.")
        return 0

    # Phase 2: Generate (parallel)
    generation_results = {}
    videos_needing_generation = []

    for video in approved:
        vid = video["video_id"]
        channel_slug = slugify(video["channel"])
        search_dirs = [youtube_repo]
        if blog_repo is not None:
            search_dirs.extend([blog_repo / blog_content_dir / channel_slug, blog_repo / blog_content_dir])
        if llmwiki_dir is not None:
            search_dirs.append(llmwiki_dir / "raw")
        existing = _find_existing_blog(vid, *search_dirs)
        if existing is not None:
            logger.info("[%s] Found existing blog file: %s, skipping generation", vid, existing.name)
            generation_results[vid] = existing
        else:
            videos_needing_generation.append(video)

    max_parallel = config["max_parallel"]
    if videos_needing_generation:
        logger.info(
            "Generating %d blog posts (max %d parallel)...",
            len(videos_needing_generation),
            max_parallel,
        )
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {
                pool.submit(generate_blog_post, v["url"], v["video_id"], youtube_repo, use_eyes=use_eyes): v
                for v in videos_needing_generation
            }
            for future in as_completed(futures):
                video = futures[future]
                vid = video["video_id"]
                try:
                    blog_path = future.result()
                except Exception as exc:
                    logger.error("[%s] Blog generation raised: %s", vid, exc)
                    blog_path = None
                if blog_path is None:
                    logger.error("[%s] Blog generation failed, skipping for retry", vid)
                    stats["failed"] += 1
                else:
                    logger.info("[%s] Blog generated: %s", vid, blog_path.name)
                    generation_results[vid] = blog_path

    # Phase 3: Publish (sequential)
    for video in approved:
        vid = video["video_id"]
        title = video["title"]
        channel_name = video["channel"]
        channel_slug = slugify(channel_name)
        blog_path = generation_results.get(vid)
        if blog_path is None:
            continue

        extracted_title = title
        is_bundle = blog_path.name == "index.md"
        blog_src_dir = blog_path.parent if is_bundle else None
        blog_copy_name = blog_src_dir.name if is_bundle else blog_path.name

        if blog_repo is not None:
            dest_parent = blog_repo / blog_content_dir / channel_slug
            if is_bundle:
                dest_dir = dest_parent / blog_copy_name
                dest_md = dest_dir / "index.md"
            else:
                dest_dir = None
                dest_md = dest_parent / blog_copy_name

            blog_copied = False
            if dest_md.exists():
                logger.info("[%s] Already in blog repo, skipping copy", vid)
            else:
                logger.info("[%s] Copying to blog repo: %s/%s", vid, channel_slug, blog_copy_name)
                if is_bundle:
                    shutil.copytree(blog_src_dir, dest_dir)
                else:
                    dest_parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(blog_path, dest_md)
                blog_copied = True

            if not dest_md.read_text(encoding="utf-8").startswith("+++\n"):
                logger.info("[%s] Linting markdown...", vid)
                lint_markdown(dest_md)
                logger.info("[%s] Generating AI tags...", vid)
                ai_tags = generate_ai_tags(dest_md)
                all_tags = list(config["hugo_tags"]) + [channel_slug] + ai_tags
                seen = set()
                unique_tags = []
                for t in all_tags:
                    if t not in seen:
                        seen.add(t)
                        unique_tags.append(t)
                logger.info("[%s] Adding Hugo front matter to %s", vid, dest_md.name)
                extracted_title = add_hugo_front_matter(
                    dest_md,
                    categories=config["hugo_categories"],
                    tags=unique_tags,
                )
                blog_copied = True
            else:
                logger.info("[%s] Hugo front matter already present", vid)

            if blog_copied:
                commit_path = dest_dir if is_bundle else dest_md
                logger.info("[%s] Committing to blog repo...", vid)
                if not push_blog_repo(blog_repo, commit_path, [extracted_title]):
                    logger.error("[%s] Git commit failed - will not mark as seen", vid)
                    stats["failed"] += 1
                    continue

        if llmwiki_dir is not None:
            wiki_src = dest_md if blog_repo is not None else blog_path
            if is_bundle:
                wiki_dest = llmwiki_dir / "raw" / blog_copy_name
                if wiki_dest.exists():
                    logger.info("[%s] Already in LLM wiki raw, skipping copy", vid)
                else:
                    logger.info("[%s] Copying bundle to LLM wiki raw: %s", vid, blog_copy_name)
                    src_dir = dest_dir if blog_repo is not None else blog_src_dir
                    shutil.copytree(src_dir, wiki_dest)
            else:
                wiki_dest = llmwiki_dir / "raw" / blog_copy_name
                if wiki_dest.exists():
                    logger.info("[%s] Already in LLM wiki raw, skipping copy", vid)
                else:
                    logger.info("[%s] Copying to LLM wiki raw: %s", vid, blog_copy_name)
                    wiki_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(wiki_src, wiki_dest)

        state.mark_seen(vid, {
            "title": extracted_title,
            "filename": blog_path.name,
            "channel": channel_name,
            "published": True,
        })
        stats["published"] += 1

    logger.info(
        "Run complete: %d channels polled, %d new videos, "
        "%d published, %d failed",
        len(config["channels"]),
        len(candidates),
        stats["published"],
        stats["failed"],
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-publish YouTube video blog posts",
    )
    parser.add_argument(
        "--url",
        help="Process a single YouTube video URL (skips RSS polling)",
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
        "--cookies-from-browser",
        metavar="BROWSER",
        default=None,
        help="Use cookies from BROWSER (e.g. chrome) to authenticate yt-dlp requests and avoid 429 rate limits.",
    )
    parser.add_argument(
        "--use-eyes",
        action="store_true",
        help="Use /youtube-eyes instead of /youtube-blog (extracts video frames with YOLOv8 + OCR).",
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
    if args.cookies_from_browser:
        os.environ["YOUTUBE_TRANSCRIPT_COOKIES_BROWSER"] = args.cookies_from_browser
    config = load_config(args.config)
    setup_logging("autopublish", verbose=args.verbose,
                  log_file=config["state_dir"] / "automation.log")
    if args.url:
        if args.dry_run:
            parser.error("--dry-run cannot be used with --url")
        return run_single(args.config, args.url, force=args.force, use_eyes=args.use_eyes)
    if args.force:
        parser.error("--force can only be used with --url")
    return run(args.config, dry_run=args.dry_run, use_eyes=args.use_eyes)


if __name__ == "__main__":
    raise SystemExit(main())
