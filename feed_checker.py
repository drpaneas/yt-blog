import json
import logging
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
CHANNEL_URL = "https://www.youtube.com/channel/{channel_id}/videos"
YTDLP_MAX_ITEMS = 15


def parse_atom_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        video_id_el = entry.find(f"{{{YT_NS}}}videoId")
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        link_el = entry.find(f"{{{ATOM_NS}}}link[@rel='alternate']")
        published_el = entry.find(f"{{{ATOM_NS}}}published")
        if video_id_el is None or title_el is None:
            continue
        vid_text = video_id_el.text
        if not vid_text or not vid_text.strip():
            continue
        entries.append({
            "video_id": vid_text.strip(),
            "title": title_el.text.strip() if title_el.text else "",
            "url": link_el.get("href", "") if link_el is not None else "",
            "published": published_el.text.strip() if published_el is not None and published_el.text else "",
        })
    return entries


def _is_valid_atom_feed(xml_text: str) -> bool:
    try:
        root = ET.fromstring(xml_text)
        return root.tag == f"{{{ATOM_NS}}}feed"
    except ET.ParseError:
        return False


def _fetch_via_rss(channel_id: str) -> list[dict] | None:
    url = FEED_URL.format(channel_id=channel_id)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            xml_text = resp.read().decode("utf-8")
    except OSError as exc:
        logger.debug("RSS fetch failed for %s: %s", channel_id, exc)
        return None
    if not _is_valid_atom_feed(xml_text):
        logger.debug("RSS response for %s is not a valid Atom feed", channel_id)
        return None
    try:
        entries = parse_atom_feed(xml_text)
    except ET.ParseError:
        return None
    return entries if entries else None


def _fetch_via_ytdlp(channel_id: str) -> list[dict] | None:
    channel_url = CHANNEL_URL.format(channel_id=channel_id)
    try:
        result = subprocess.run(
            [
                "yt-dlp", "--flat-playlist", "-j",
                "--playlist-items", f"1:{YTDLP_MAX_ITEMS}",
                channel_url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.error("yt-dlp fallback failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.error("yt-dlp fallback returned exit code %d", result.returncode)
        return None
    entries = []
    for line in result.stdout.strip().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = item.get("id", "")
        if not vid:
            continue
        entries.append({
            "video_id": vid,
            "title": item.get("title", ""),
            "url": item.get("webpage_url") or item.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "published": item.get("upload_date", ""),
        })
    return entries if entries else None


MAX_VIDEOS_PER_CHANNEL = 3


def fetch_new_videos(channels: list[dict]) -> list[dict]:
    all_videos = []
    for ch in channels:
        entries = _fetch_via_rss(ch["channel_id"])
        if entries is not None:
            logger.debug("RSS feed worked for %s (%d videos)", ch["name"], len(entries))
        else:
            logger.info("RSS feed unavailable for %s, falling back to yt-dlp", ch["name"])
            entries = _fetch_via_ytdlp(ch["channel_id"])
        if entries is None:
            logger.error("Failed to fetch videos for %s via both RSS and yt-dlp", ch["name"])
            continue
        entries = entries[:MAX_VIDEOS_PER_CHANNEL]
        for entry in entries:
            entry["channel"] = ch["name"]
        all_videos.extend(entries)
    return all_videos
