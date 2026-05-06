"""Direct Compass Gemini API client — fallback when MCP proxy is unavailable.

Implements the same call_tool() interface as MCPClient so callers
(image_analyzer, blog_generator, etc.) work without changes.

Protocol matches mcpserver/internal/client/gemini/image.go:
  POST {base_url}/models/{model}:generateContent
  Authorization: Bearer {client_token}
"""

import base64
import json
import os
import re
import uuid
from typing import Any, Optional

import httpx


class CompassAPIError(Exception):
    pass


def _guess_mime(url: str) -> str:
    low = url.lower().split("?")[0]
    if low.endswith(".png"):
        return "image/png"
    if low.endswith(".webp"):
        return "image/webp"
    if low.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


class CompassClient:
    """Direct Compass Gemini API client with MCPClient-compatible call_tool()."""

    def __init__(
        self,
        base_url: str,
        client_token: str,
        service_name: str = "",
        understanding_model: str = "gemini-2.0-flash",
        generation_model: str = "gemini-2.0-flash-preview-image-generation",
        timeout: float = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_token = client_token
        self.service_name = service_name
        self.understanding_model = understanding_model
        self.generation_model = generation_model
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def connect(self):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.client_token}",
        }
        if self.service_name:
            headers["X-Service-Name"] = self.service_name
        self._client = httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(self.timeout, connect=15.0),
        )

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def call_tool(self, name: str, arguments: dict[str, Any], timeout: Optional[float] = None) -> dict:
        if not self._client:
            self.connect()

        if name == "image_understand":
            text = self._understand(arguments, timeout)
            return {"content": [{"type": "text", "text": text}]}
        elif name == "imagen_generate":
            return self._generate_image(arguments, timeout)
        else:
            raise CompassAPIError(f"Unsupported tool: {name}")

    def _post_generate(self, model: str, body: dict, timeout: Optional[float] = None) -> dict:
        effective_timeout = timeout or self.timeout
        url = f"{self.base_url}/models/{model}:generateContent"
        try:
            resp = self._client.post(url, json=body, timeout=effective_timeout)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise CompassAPIError(
                f"Compass API error: HTTP {e.response.status_code} — {e.response.text[:500]}"
            )
        except httpx.ConnectError as e:
            raise CompassAPIError(f"Cannot connect to Compass API at {self.base_url}: {e}")
        except httpx.TimeoutException as e:
            raise CompassAPIError(f"Compass API timed out after {effective_timeout}s: {e}")

        return resp.json()

    def _understand(self, arguments: dict, timeout: Optional[float] = None) -> str:
        prompt = arguments.get("prompt", "")
        image_urls = arguments.get("image_urls", [])

        parts = []
        if prompt:
            parts.append({"text": prompt})
        for url in image_urls:
            parts.append({"fileData": {"fileUri": url, "mimeType": _guess_mime(url)}})

        body = {"contents": [{"role": "user", "parts": parts}]}
        result = self._post_generate(self.understanding_model, body, timeout)

        if "error" in result:
            raise CompassAPIError(f"Gemini API error: {result['error'].get('message', str(result['error']))}")

        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise CompassAPIError(f"Unexpected response format: {json.dumps(result)[:500]}")

    def _generate_image(self, arguments: dict, timeout: Optional[float] = None) -> dict:
        prompt = arguments.get("prompt", "")
        image_urls = arguments.get("image_urls", [])

        parts = []
        for url in image_urls:
            parts.append({"fileData": {"fileUri": url, "mimeType": _guess_mime(url)}})
        if prompt:
            parts.append({"text": prompt})

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            },
        }

        result = self._post_generate(self.generation_model, body, timeout)

        if "error" in result:
            raise CompassAPIError(f"Gemini API error: {result['error'].get('message', str(result['error']))}")

        images = []
        text_parts = []
        try:
            for part in result["candidates"][0]["content"]["parts"]:
                if "text" in part:
                    text_parts.append(part["text"])
                elif "inlineData" in part:
                    images.append(part["inlineData"])
        except (KeyError, IndexError):
            raise CompassAPIError(f"Unexpected response format: {json.dumps(result)[:500]}")

        output_lines = []
        if text_parts:
            output_lines.append("\n".join(text_parts))

        for i, img in enumerate(images, 1):
            b64 = img.get("data", "")
            mime = img.get("mimeType", "image/png")
            output_lines.append(f"[Image {i}]: data:{mime};base64,{b64}")

        return {
            "content": [{"type": "text", "text": "\n".join(output_lines)}],
            "_images": images,
        }

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()


def create_compass_client(cfg: dict) -> Optional["CompassClient"]:
    """Create CompassClient from config.json or env vars. Returns None if unconfigured."""
    base_url = (
        os.environ.get("COMPASS_BASE_URL")
        or cfg.get("compass_api", {}).get("base_url", "")
    )
    client_token = (
        os.environ.get("COMPASS_CLIENT_TOKEN")
        or cfg.get("compass_api", {}).get("client_token", "")
    )

    if not base_url or not client_token:
        return None

    service_name = cfg.get("compass_api", {}).get("service_name", "")
    understanding_model = cfg.get("compass_api", {}).get("understanding_model", "gemini-2.0-flash")
    generation_model = cfg.get("compass_api", {}).get("generation_model", "gemini-2.0-flash-preview-image-generation")
    timeout = cfg.get("compass_api", {}).get("timeout", 300)

    return CompassClient(
        base_url=base_url,
        client_token=client_token,
        service_name=service_name,
        understanding_model=understanding_model,
        generation_model=generation_model,
        timeout=timeout,
    )
