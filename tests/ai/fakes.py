"""Test double cho nhà cung cấp AI: máy chủ giả lập định dạng Messages API của Anthropic qua httpx.MockTransport.

Đây KHÔNG phải kết quả AI thật. Nội dung trả về được viết sẵn trong test để kiểm tra đường đi của dữ liệu:
định dạng request, xử lý phản hồi, kiểm tra schema, phân quyền, audit. Chất lượng đề xuất của mô hình thật
chưa được kiểm chứng trong môi trường này (không có khóa API).
"""

import json
from typing import Any

import httpx
from omnitest_ai.providers import AIConfig, AnthropicProvider

FAKE_KEY = "sk-ant-test-khong-phai-khoa-that"


class FakeAnthropic:
    def __init__(self, reply: Any, status: int = 200, stop_reason: str = "end_turn") -> None:
        self.reply = reply
        self.status = status
        self.stop_reason = stop_reason
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "lỗi giả lập"}})
        text = (
            self.reply
            if isinstance(self.reply, str)
            else json.dumps(self.reply, ensure_ascii=False)
        )
        return httpx.Response(
            200,
            json={
                "model": "claude-test-double",
                "content": [{"type": "text", "text": text}],
                "stop_reason": self.stop_reason,
                "usage": {"input_tokens": 123, "output_tokens": 45},
            },
        )

    def provider(self) -> AnthropicProvider:
        cfg = AIConfig(provider="anthropic", model="claude-test-double", api_key=FAKE_KEY)
        return AnthropicProvider(cfg, transport=httpx.MockTransport(self.handler))

    def sent_body(self, index: int = -1) -> dict[str, Any]:
        return dict(json.loads(self.requests[index].content))


API_DRAFT: dict[str, Any] = {
    "title": "Health trả 200",
    "description": "Kiểm tra dịch vụ sống",
    "priority": "high",
    "tags": ["smoke"],
    "expected_result": "Mã 200",
    "definition": {
        "kind": "api",
        "steps": [
            {
                "name": "Health",
                "url": "/api/health",
                "assertions": [{"type": "status", "equals": 200}],
            }
        ],
    },
    "assumptions": ["Endpoint /api/health không cần đăng nhập"],
    "uncertainty": "low",
    "rationale": "Smoke test",
}
