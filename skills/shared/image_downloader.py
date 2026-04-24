"""Download images from MCP tool responses (imagen_generate output)."""

import os
import re
import uuid
from typing import Optional

import httpx


class DownloadError(Exception):
    pass


def extract_image_urls(text: str) -> list[str]:
    """Extract image download URLs from imagen_generate MCP response text.

    Expected format:
        [Image 1]: https://...
        [Image 2]: https://...
    """
    return re.findall(r"\[Image \d+\]:\s*(https?://\S+)", text)


def download_image(url: str, save_path: str, timeout: float = 120) -> str:
    """Download an image from URL and save to disk. Returns absolute path."""
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(resp.content)
    except httpx.HTTPStatusError as e:
        raise DownloadError(f"Download failed: HTTP {e.response.status_code} from {url}")
    except httpx.ConnectError as e:
        raise DownloadError(f"Cannot connect to download URL {url}: {e}")
    return os.path.abspath(save_path)
