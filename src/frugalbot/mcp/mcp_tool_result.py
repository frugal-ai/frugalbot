from typing import Any

import pydantic
from mcp.types import AudioContent, EmbeddedResource, ImageContent, ResourceLink, TextContent, TextResourceContents

_MAX_BASE64_LENGTH = 64_000


class MCPToolResult(pydantic.BaseModel):
    """Result from an MCP tool call.

    is_error=True indicates a graceful tool-level failure (e.g., "File not found").
    """

    content: list[TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource]
    is_error: bool = False
    structured_content: dict[str, Any] | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize with base64 truncation and JSON mode compatibility."""
        # Ensure we use mode="json" so that AnyUrl and other non-standard
        # types are converted to standard JSON-serializable types.
        kwargs.setdefault("mode", "json")
        data = super().model_dump(**kwargs)
        data["content"] = self._truncate_multimodal(data.get("content", []))
        return data

    @staticmethod
    def _truncate_multimodal(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Truncate raw base64 and oversized payload data in ImageContent, AudioContent,

        and EmbeddedResources to prevent context window bloat and overflow errors.
        """
        truncated: list[dict[str, Any]] = []
        for item in content:
            item = dict(item)
            # Handle images and audio base64 payload truncation
            if item.get("type") in ("image", "audio") and isinstance(item.get("data"), str):
                if len(item["data"]) > _MAX_BASE64_LENGTH:
                    item["data"] = f"[base64 {item['type']} truncated: {len(item['data'])} chars, limit {_MAX_BASE64_LENGTH}]"

            # Handle embedded resources with potentially large contents
            elif item.get("type") == "resource":
                res = item.get("resource", {})
                if isinstance(res, dict):
                    res = dict(res)
                    if "blob" in res and isinstance(res["blob"], str) and len(res["blob"]) > _MAX_BASE64_LENGTH:
                        res["blob"] = f"[base64 blob truncated: {len(res['blob'])} chars, limit {_MAX_BASE64_LENGTH}]"
                    if "text" in res and isinstance(res["text"], str) and len(res["text"]) > _MAX_BASE64_LENGTH * 2:
                        res["text"] = f"[text resource truncated: {len(res['text'])} chars, limit {_MAX_BASE64_LENGTH * 2}]"
                    item["resource"] = res

            truncated.append(item)
        return truncated

    def to_text(self) -> str:
        """Extract text content only. Available for TUI display or debugging."""
        text_parts = []
        for block in self.content:
            if isinstance(block, TextContent):
                text_parts.append(block.text)
            elif isinstance(block, EmbeddedResource):
                if isinstance(block.resource, TextResourceContents):
                    text_parts.append(block.resource.text)
            elif isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                elif block.get("type") == "resource" and isinstance(block.get("resource"), dict):
                    res_text = block["resource"].get("text")
                    if isinstance(res_text, str):
                        text_parts.append(res_text)
        return "\n".join(text_parts)
