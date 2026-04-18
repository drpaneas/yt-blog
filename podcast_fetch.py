import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

PODCASTINDEX_API_BASE = "https://api.podcastindex.org/api/1.0"
MAX_EPISODES_PER_PODCAST = 3


def _podcastindex_headers() -> dict[str, str]:
    api_key = os.environ.get("PODCASTINDEX_API_KEY", "").strip()
    api_secret = os.environ.get("PODCASTINDEX_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError(
            "PODCASTINDEX_API_KEY and PODCASTINDEX_API_SECRET environment "
            "variables are required"
        )
    epoch = str(int(time.time()))
    auth_hash = hashlib.sha1(
        (api_key + api_secret + epoch).encode()
    ).hexdigest()
    return {
        "User-Agent": "youtube-blog-automation/1.0",
        "X-Auth-Key": api_key,
        "X-Auth-Date": epoch,
        "Authorization": auth_hash,
    }


def _api_get(endpoint: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{PODCASTINDEX_API_BASE}/{endpoint}?{query}"
    headers = _podcastindex_headers()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_podcast_info(podcast_id: str) -> dict | None:
    try:
        data = _api_get("podcasts/byfeedid", {"id": podcast_id})
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to fetch podcast info for %s: %s", podcast_id, exc)
        return None
    feeds = data.get("feeds", [])
    if not feeds:
        logger.error("No feed data returned for podcast %s", podcast_id)
        return None
    return feeds[0]


def fetch_episodes(podcast_id: str) -> list[dict]:
    try:
        data = _api_get("episodes/byfeedid", {"id": podcast_id, "max": str(MAX_EPISODES_PER_PODCAST + 2)})
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to fetch episodes for %s: %s", podcast_id, exc)
        return []
    items = data.get("items", [])
    episodes = []
    for item in items:
        audio_url = item.get("enclosureUrl", "")
        if not audio_url:
            continue
        episode_id = str(item.get("id", ""))
        if not episode_id:
            continue
        episodes.append({
            "episode_id": episode_id,
            "title": item.get("title", ""),
            "audio_url": audio_url,
            "published": item.get("datePublished", ""),
            "episode_url": item.get("link", ""),
            "duration": item.get("duration", 0),
        })
    return episodes


def fetch_new_episodes(podcasts: list[dict]) -> list[dict]:
    all_episodes = []
    for podcast in podcasts:
        pid = podcast["podcast_id"]
        name = podcast["name"]
        episodes = fetch_episodes(pid)
        if not episodes:
            logger.warning("No episodes found for podcast %s (%s)", name, pid)
            continue
        logger.debug(
            "Found %d episodes for %s", len(episodes), name
        )
        episodes = episodes[:MAX_EPISODES_PER_PODCAST]
        for ep in episodes:
            ep["podcast_name"] = name
            ep["podcast_id"] = pid
        all_episodes.extend(episodes)
    return all_episodes
