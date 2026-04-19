import logging
import re
import subprocess
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".youtube-blog-automation"
LOG_FILE = DEFAULT_STATE_DIR / "automation.log"


def setup_logging(log_tag: str, verbose: bool = False, log_file: Path | None = None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    target = log_file if log_file is not None else LOG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format=f"%(asctime)s [{log_tag}] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(target, encoding="utf-8"),
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
    if result.returncode != 0:
        raise RuntimeError(
            f"Blog repo at '{blog_repo}' is not a valid git repository"
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
        # TODO: re-enable push when ready
        # subprocess.run(
        #     ["git", "push"],
        #     cwd=blog_repo,
        #     check=True,
        #     capture_output=True,
        # )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Git commit failed: %s", exc.stderr)
        return False


def lint_markdown(file_path: Path) -> None:
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


def generate_ai_tags(file_path: Path) -> list[str]:
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

    # TODO: re-enable wiki lint when ready
    # lint_prompt = "please lint the wiki and fix any issues you find"
    # try:
    #     result = subprocess.run(
    #         [
    #             "claude", "-p", lint_prompt,
    #             "-d", str(llmwiki_dir),
    #             "--dangerously-skip-permissions",
    #             "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(date +*)",
    #         ],
    #         capture_output=True,
    #         text=True,
    #         timeout=600,
    #         check=True,
    #     )
    #     logger.debug("Wiki lint stdout:\n%s", result.stdout)
    # except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
    #     logger.error("Wiki lint failed: %s", exc)


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-") or "unknown"
