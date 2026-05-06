#!/usr/bin/env python3
"""Lightweight mock MCP server for end-to-end testing.

Simulates image_understand, imagen_generate, and file upload
with realistic response formats so the full pipeline can be validated
without a real mcpserver.

Usage:
    python3 mock_mcp_server.py [--port 8080]

Provides:
    POST /message       — MCP JSON-RPC 2.0 (tools/list, tools/call)
    POST /upload        — File upload (returns mock hosted URL)
    GET  /mock-image/*  — Downloadable 1x1 PNG (for imagen_generate results)
    GET  /sse           — SSE endpoint (returns session)
"""

import io
import json
import sys
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8080

# 1x1 red PNG (89 bytes)
_MOCK_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
    b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
    b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)

MOCK_PHOTO_ANALYSIS = {
    "scene": "A cozy indoor dining scene with steaming hot pot",
    "people": "Two adults seated at a round table",
    "action": "Sharing a hot pot meal, dipping ingredients",
    "mood": "warm, joyful, intimate",
    "location": "Restaurant interior with warm lighting",
    "time_of_day": "evening",
    "objects": ["hot pot", "chopsticks", "vegetables", "plates"],
    "narrative_hook": "The warmth of shared meals brings people closer",
    "orientation_correct": True,
    "quality_score": 8,
    "composition_score": 7,
    "interest_score": 8,
    "emotion_score": 9,
    "narrative_score": 8,
    "tier": "hero",
}

MOCK_COMIC_ANALYSIS = {
    "scene_summary": "A cozy indoor dining scene with steaming hot pot",
    "character_desc": "Two adults in casual wear, smiling warmly",
    "action_desc": "Sharing a hot pot meal together",
    "emotion": "warm, joyful",
    "environment": "Cozy restaurant with warm lighting",
    "time_of_day": "evening",
    "comic_panel_desc": "Two friends enjoying hot pot, steam rising, warm golden tones",
    "quality_score": 8,
    "composition_score": 7,
    "interest_score": 8,
    "emotion_score": 9,
    "narrative_score": 8,
    "tier": "hero",
}

MOCK_BLOG_CONTENT = {
    "title": "A Warm Evening Together",
    "description": {"text": "An evening of shared warmth and flavor."},
    "insights": [
        {"photo_index": 0, "text": "The golden glow of the hot pot steam creates an intimate atmosphere.", "mood": "warm"},
        {"photo_index": 1, "text": "Laughter echoes between bites of perfectly seasoned broth.", "mood": "joyful"},
        {"photo_index": 2, "text": "Simple moments around the table become lasting memories.", "mood": "nostalgic"},
    ],
    "suggested_themes": ["Flavors of Friendship", "Table Stories", "Evening Warmth"],
}

MOCK_STORYBOARD = {
    "theme": "Warmth in Every Bite",
    "emotional_arc": "From anticipation to shared joy",
    "panels": [
        {"panel_index": 0, "source_photo_index": 0, "scene_description": "Two friends arrive at the restaurant.", "emotion_tag": "anticipation", "panel_composition": "wide shot"},
        {"panel_index": 1, "source_photo_index": 1, "scene_description": "The hot pot arrives, steam rising.", "emotion_tag": "delight", "panel_composition": "medium shot"},
        {"panel_index": 2, "source_photo_index": 2, "scene_description": "Sharing ingredients and laughter.", "emotion_tag": "warmth", "panel_composition": "close-up"},
    ],
    "narrative": {"title": "Warmth in Every Bite", "body": "In the steam and warmth, ordinary moments become extraordinary."},
    "footer_date": "2026-04-24",
    "suggested_themes": ["Evening Glow", "Flavor Atlas", "Together at the Table"],
}

_upload_counter = 0


def _handle_batch_understand(params: dict) -> dict:
    prompt = params.get("prompt", "")
    image_urls = params.get("image_urls", [])
    prompt_lower = prompt.lower()

    if not image_urls:
        if "storyboard" in prompt_lower or "comic" in prompt_lower or "scriptwriter" in prompt_lower:
            panel_count = 3
            for word in prompt.split():
                if word.isdigit():
                    panel_count = int(word)
                    break
            sb = json.loads(json.dumps(MOCK_STORYBOARD))
            while len(sb["panels"]) < panel_count:
                idx = len(sb["panels"])
                sb["panels"].append({
                    "panel_index": idx,
                    "source_photo_index": idx,
                    "scene_description": f"Panel {idx+1} scene.",
                    "emotion_tag": "calm",
                    "panel_composition": "medium shot",
                })
            sb["panels"] = sb["panels"][:panel_count]
            return {"content": [{"type": "text", "text": json.dumps(sb, ensure_ascii=False)}]}

        blog = json.loads(json.dumps(MOCK_BLOG_CONTENT))
        return {"content": [{"type": "text", "text": json.dumps(blog, ensure_ascii=False)}]}

    n = len(image_urls)
    if "comic" in prompt_lower or "漫画" in prompt_lower:
        results = []
        for i in range(n):
            item = json.loads(json.dumps(MOCK_COMIC_ANALYSIS))
            item["scene_summary"] = f"Scene {i+1}: " + item["scene_summary"]
            results.append(item)
        return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False)}]}

    results = []
    for i in range(n):
        item = json.loads(json.dumps(MOCK_PHOTO_ANALYSIS))
        item["scene"] = f"Scene {i+1}: " + item["scene"]
        results.append(item)
    return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False)}]}


def _handle_imagen_generate(params: dict, port: int) -> dict:
    uid = uuid.uuid4().hex[:8]
    url = f"http://localhost:{port}/mock-image/{uid}.png"
    text = f"Image generated successfully!\n\n\U0001f5bc️  图片下载Link:\n  [Image 1]: {url}\n"
    return {"content": [{"type": "text", "text": text}]}


class MCPHandler(BaseHTTPRequestHandler):
    server_port = PORT

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        if self.path.startswith("/upload"):
            self._handle_upload(raw)
            return

        if not raw:
            self._send_json(400, {"error": "empty body"})
            return

        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._handle_upload_multipart(raw)
            return

        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id", 1)

        if method == "tools/list":
            result = {"tools": [
                {"name": "image_understand", "description": "Batch image understanding",
                 "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "image_urls": {"type": "array"}}}},
                {"name": "imagen_generate", "description": "Image generation",
                 "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "image_urls": {"type": "array"}}}},
            ]}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            if tool_name == "image_understand":
                result = _handle_batch_understand(args)
            elif tool_name == "imagen_generate":
                result = _handle_imagen_generate(args, self.server_port)
            else:
                result = {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}
        else:
            result = {"error": {"code": -32601, "message": f"Method not found: {method}"}}

        resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
        self._send_json(200, resp)

    def _handle_upload(self, raw_body):
        global _upload_counter
        _upload_counter += 1
        uid = uuid.uuid4().hex[:8]
        url = f"http://localhost:{self.server_port}/mock-image/upload_{_upload_counter}_{uid}.jpg"
        resp = {"code": 0, "results": {"url": url, "file_id": uid}}
        self._send_json(200, resp)

    def _handle_upload_multipart(self, raw_body):
        self._handle_upload(raw_body)

    def do_GET(self):
        if self.path.startswith("/mock-image/"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(_MOCK_PNG)))
            self.end_headers()
            self.wfile.write(_MOCK_PNG)
        elif self.path.startswith("/sse"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            session_id = uuid.uuid4().hex
            msg = f"data: {{\"endpoint\": \"/message?session_id={session_id}\"}}\n\n"
            self.wfile.write(msg.encode())
            self.wfile.flush()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Mock MCP Server running\n")

    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"  [MOCK] {args[0]}")


def main():
    port = PORT
    if len(sys.argv) > 1 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    elif len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    MCPHandler.server_port = port
    server = HTTPServer(("", port), MCPHandler)
    print(f"Mock MCP Server on http://localhost:{port}")
    print(f"  /message   — MCP JSON-RPC")
    print(f"  /upload    — File upload")
    print(f"  /mock-image/* — Downloadable mock images")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
