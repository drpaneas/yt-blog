import logging
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


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
        entries.append({
            "video_id": video_id_el.text.strip(),
            "title": title_el.text.strip() if title_el.text else "",
            "url": link_el.get("href", "") if link_el is not None else "",
            "published": published_el.text.strip() if published_el is not None and published_el.text else "",
        })
    return entries


def fetch_new_videos(channels: list[dict]) -> list[dict]:
    all_videos = []
    for ch in channels:
        url = FEED_URL.format(channel_id=ch["channel_id"])
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                xml_text = resp.read().decode("utf-8")
        except OSError as exc:
            logger.error("Failed to fetch feed for %s: %s", ch["name"], exc)
            continue
        try:
            entries = parse_atom_feed(xml_text)
        except ET.ParseError as exc:
            logger.error("Failed to parse feed for %s: %s", ch["name"], exc)
            continue
        for entry in entries:
            entry["channel"] = ch["name"]
        all_videos.extend(entries)
    return all_videos
