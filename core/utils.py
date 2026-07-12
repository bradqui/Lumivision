"""Helpers: video embed parsing, Open Graph link previews, image thumbnails,
video poster extraction."""

import io
import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Lumivision/1.0; +vision board link preview)"
}
FETCH_TIMEOUT = 6

_YT_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([A-Za-z0-9_-]{6,20})"),
]
_VIMEO_PATTERN = re.compile(r"vimeo\.com/(?:video/)?(\d+)")


def parse_embed(url):
    """Return dict(provider, src, thumb_url) for a YouTube/Vimeo URL, else None."""
    url = (url or "").strip()
    for pat in _YT_PATTERNS:
        m = pat.search(url)
        if m:
            vid = m.group(1)
            return {
                "provider": "youtube",
                "src": f"https://www.youtube-nocookie.com/embed/{vid}",
                "thumb_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            }
    m = _VIMEO_PATTERN.search(url)
    if m:
        vid = m.group(1)
        thumb = ""
        try:
            r = requests.get(
                "https://vimeo.com/api/oembed.json",
                params={"url": f"https://vimeo.com/{vid}"},
                headers=REQUEST_HEADERS,
                timeout=FETCH_TIMEOUT,
            )
            if r.ok:
                thumb = r.json().get("thumbnail_url", "")
        except requests.RequestException:
            pass
        return {
            "provider": "vimeo",
            "src": f"https://player.vimeo.com/video/{vid}",
            "thumb_url": thumb,
        }
    return None


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title = ""
        self._in_title = False
        self._done_head = False

    def handle_starttag(self, tag, attrs):
        if self._done_head:
            return
        if tag == "meta":
            d = dict(attrs)
            key = d.get("property") or d.get("name") or ""
            content = d.get("content") or ""
            if key and content and key not in self.meta:
                self.meta[key.lower()] = content
        elif tag == "title":
            self._in_title = True
        elif tag == "body":
            self._done_head = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 300:
            self.title += data


def fetch_og(url):
    """Fetch Open Graph metadata for a URL. Returns dict(title, description, image)."""
    result = {"title": "", "description": "", "image": ""}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return result
    try:
        r = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=FETCH_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )
        content_type = r.headers.get("content-type", "")
        if "html" not in content_type:
            return result
        # Read at most 512 KB — OG tags live in <head>.
        chunk = next(r.iter_content(512 * 1024, decode_unicode=False), b"")
        html = chunk.decode(r.encoding or "utf-8", errors="replace")
    except requests.RequestException:
        return result

    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    meta = parser.meta
    result["title"] = (meta.get("og:title") or parser.title or "").strip()[:300]
    result["description"] = (
        meta.get("og:description") or meta.get("description") or ""
    ).strip()[:500]
    image = meta.get("og:image") or meta.get("twitter:image") or ""
    if image.startswith("//"):
        image = f"{parsed.scheme}:{image}"
    elif image.startswith("/"):
        image = f"{parsed.scheme}://{parsed.netloc}{image}"
    result["image"] = image[:500]
    return result


THUMB_MAX = 900  # px, longest edge


AVATAR_SIZE = 256


def make_avatar(uploaded_file):
    """Center-crop an uploaded image to a square avatar JPEG."""
    try:
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, (7, 8, 13))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
        img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85, optimize=True)
        return ContentFile(buf.getvalue(), name="avatar.jpg")
    except Exception:
        return None


def extract_video_poster(video_path):
    """Grab a frame from an uploaded video with ffmpeg. Returns a JPEG
    ContentFile, or None when ffmpeg is unavailable or the video is unreadable
    (the asset then simply shows the styled placeholder)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    fd, out_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        # Prefer a frame at 1s (skips black lead-ins); fall back to frame 0.
        for seek in ("1", "0"):
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-ss", seek, "-i", video_path,
                    "-frames:v", "1",
                    "-vf", "scale='min(900,iw)':-2",
                    "-q:v", "3", out_path,
                ],
                capture_output=True,
                timeout=90,
            )
            if result.returncode == 0 and os.path.getsize(out_path) > 0:
                with open(out_path, "rb") as f:
                    return ContentFile(f.read(), name="poster.jpg")
    except (subprocess.SubprocessError, OSError):
        pass
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass
    return None


def make_thumbnail(uploaded_file, name_hint="thumb"):
    """Create a web-friendly JPEG thumbnail ContentFile from an uploaded image."""
    try:
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, (7, 8, 13))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82, optimize=True)
        return ContentFile(buf.getvalue(), name=f"{name_hint}.jpg")
    except Exception:
        return None
