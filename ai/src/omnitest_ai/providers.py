"""Nhà cung cấp mô hình ngôn ngữ. Khóa API chỉ lấy từ cấu hình máy chủ, không ghi log, không trả về client.

Hỗ trợ:
- anthropic: Messages API của Anthropic (Claude).
- openai_compatible: API dạng /chat/completions (OpenAI, Azure OpenAI qua gateway, Ollama, vLLM...).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

ProviderName = Literal["none", "anthropic", "openai_compatible"]
ANTHROPIC_VERSION = "2023-06-01"


class AIError(Exception):
    """Lỗi khi gọi nhà cung cấp AI; thông điệp an toàn để hiển thị (không chứa khóa)."""


@dataclass(frozen=True)
class AIConfig:
    provider: ProviderName
    model: str
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 60
    max_output_tokens: int = 4096

    @property
    def enabled(self) -> bool:
        if self.provider == "anthropic":
            return bool(self.api_key and self.model)
        if self.provider == "openai_compatible":
            return bool(self.base_url and self.model)
        return False


@dataclass(frozen=True)
class AIText:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None


class AIProvider(Protocol):
    name: str
    model: str

    async def complete(self, system: str, user: str) -> AIText: ...


def _status_error(status: int) -> AIError:
    if status in (401, 403):
        return AIError("Nhà cung cấp AI từ chối xác thực: kiểm tra khóa API trong cấu hình máy chủ")
    if status == 429:
        return AIError("Nhà cung cấp AI đang giới hạn tần suất, thử lại sau")
    if status >= 500:
        return AIError("Nhà cung cấp AI đang lỗi, thử lại sau")
    return AIError(f"Nhà cung cấp AI trả lỗi {status}")


class _HttpProvider:
    name = "base"

    def __init__(self, config: AIConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.config = config
        self.model = config.model
        self._transport = transport

    async def _post(
        self, url: str, headers: dict[str, str], body: dict[str, object]
    ) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds, transport=self._transport
            ) as client:
                res = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise AIError("Hết thời gian chờ nhà cung cấp AI") from exc
        except httpx.HTTPError as exc:
            raise AIError(f"Không kết nối được nhà cung cấp AI ({exc.__class__.__name__})") from exc
        if res.status_code >= 400:
            raise _status_error(res.status_code)
        try:
            data = res.json()
        except ValueError as exc:
            raise AIError("Nhà cung cấp AI trả dữ liệu không phải JSON") from exc
        if not isinstance(data, dict):
            raise AIError("Phản hồi của nhà cung cấp AI không đúng định dạng")
        return data


class AnthropicProvider(_HttpProvider):
    name = "anthropic"

    async def complete(self, system: str, user: str) -> AIText:
        base = (self.config.base_url or "https://api.anthropic.com").rstrip("/")
        data = await self._post(
            f"{base}/v1/messages",
            {"x-api-key": self.config.api_key or "", "anthropic-version": ANTHROPIC_VERSION},
            {
                "model": self.model,
                "max_tokens": self.config.max_output_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        blocks = data.get("content")
        text = (
            "".join(
                str(b.get("text", ""))
                for b in blocks or []
                if isinstance(b, dict) and b.get("type") == "text"
            )
            if isinstance(blocks, list)
            else ""
        )
        if data.get("stop_reason") == "max_tokens":
            raise AIError("Kết quả AI bị cắt do vượt giới hạn độ dài; hãy thu hẹp yêu cầu")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        return AIText(
            text,
            str(data.get("model") or self.model),
            _int(usage.get("input_tokens")),
            _int(usage.get("output_tokens")),
        )


class OpenAICompatibleProvider(_HttpProvider):
    name = "openai_compatible"

    async def complete(self, system: str, user: str) -> AIText:
        base = (self.config.base_url or "").rstrip("/")
        headers = {"authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        data = await self._post(
            f"{base}/chat/completions",
            headers,
            {
                "model": self.model,
                "max_tokens": self.config.max_output_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else {}
        message = first.get("message") if isinstance(first, dict) else None
        text = str(message.get("content") or "") if isinstance(message, dict) else ""
        if isinstance(first, dict) and first.get("finish_reason") == "length":
            raise AIError("Kết quả AI bị cắt do vượt giới hạn độ dài; hãy thu hẹp yêu cầu")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        return AIText(
            text,
            str(data.get("model") or self.model),
            _int(usage.get("prompt_tokens")),
            _int(usage.get("completion_tokens")),
        )


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def build_provider(
    config: AIConfig, transport: httpx.AsyncBaseTransport | None = None
) -> AIProvider | None:
    """None khi AI tắt hoặc thiếu cấu hình: mọi chức năng khác vẫn chạy bình thường."""
    if not config.enabled:
        return None
    if config.provider == "anthropic":
        return AnthropicProvider(config, transport)
    return OpenAICompatibleProvider(config, transport)
