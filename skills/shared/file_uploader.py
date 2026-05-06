"""Image upload to videometa API — converts local image bytes to hosted URLs."""

import os
import uuid
from typing import Optional

import httpx


class UploadError(Exception):
    pass


class FileUploader:
    """Uploads image bytes to videometa API, returns hosted URLs."""

    def __init__(self, cfg: dict, timeout: float = 60):
        self.url = (
            os.environ.get("FILE_UPLOAD_URL")
            or cfg.get("file_upload", {}).get("url", "")
        )
        if not self.url:
            base = (
                os.environ.get("COMPASS_BASE_URL")
                or cfg.get("compass_api", {}).get("base_url", "")
            )
            if base:
                base = base.split("/inbeeai/compass-api")[0]
                self.url = base.rstrip("/") + "/inbeeai/api/v1/media/upload"

        if not self.url:
            raise UploadError(
                "Upload URL not configured. Set FILE_UPLOAD_URL env var "
                "or add file_upload.url to config.json"
            )

        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if not self._client:
            self._client = httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10.0))
        return self._client

    def upload_bytes(self, data: bytes, filename: str, mime_type: str = "image/jpeg") -> str:
        """Upload image bytes and return the hosted URL."""
        client = self._get_client()
        files = {"file": (filename, data, mime_type)}
        form_data = {"filename": filename, "mime_type": mime_type}

        try:
            resp = client.post(self.url, files=files, data=form_data)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise UploadError(f"Upload failed: HTTP {e.response.status_code}")
        except httpx.ConnectError as e:
            raise UploadError(f"Cannot connect to upload server at {self.url}: {e}")

        result = resp.json()
        if result.get("code", -1) != 0:
            raise UploadError(f"Upload API error: {result.get('message', 'unknown')}")

        url = result.get("results", {}).get("url", "")
        if not url:
            raise UploadError(f"Upload succeeded but no URL in response: {result}")
        return url

    def upload_batch(self, items: list[tuple[bytes, str, str]]) -> list[str]:
        """Upload multiple images. Each item is (data, filename, mime_type). Returns URLs."""
        urls = []
        for data, filename, mime_type in items:
            urls.append(self.upload_bytes(data, filename, mime_type))
        return urls

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
