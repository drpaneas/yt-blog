import logging
import subprocess

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = (
    "Is this YouTube video about AI, machine learning, or related topics? "
    "Answer only YES or NO. Title: {title}"
)


def _parse_response(response: str) -> bool:
    return response.strip().lower().startswith("yes")


def is_ai_related(title: str) -> bool | None:
    prompt = PROMPT_TEMPLATE.format(title=title)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.error("Relevance filter failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.error(
            "Relevance filter returned exit code %d: %s",
            result.returncode,
            result.stderr,
        )
        return None
    return _parse_response(result.stdout)
