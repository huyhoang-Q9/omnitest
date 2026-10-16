"""TEST DOUBLE cho nhà cung cấp AI dạng OpenAI-compatible, chỉ dùng cho E2E giao diện.

Trả nội dung viết sẵn, KHÔNG phải mô hình AI thật. Mục đích: kiểm tra luồng giao diện (đề xuất, duyệt, lưu,
phân tích lỗi) khi không có khóa API. Chạy:
    uv run uvicorn tests.e2e.fake_llm:app --port 8199
rồi khởi động API với OMNITEST_AI_PROVIDER=openai_compatible, OMNITEST_AI_BASE_URL=http://127.0.0.1:8199/v1.
"""

import json
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Fake LLM (test double)")

SUGGESTION = {
    "assumptions": ["[Test double] Nội dung viết sẵn, không phải AI thật"],
    "test_cases": [
        {
            "title": "[AI giả lập] Health trả 200",
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
            "assumptions": ["Endpoint không cần đăng nhập"],
            "uncertainty": "low",
            "rationale": "Smoke test cơ bản",
        },
        {
            "title": "[AI giả lập] Định nghĩa sai",
            "definition": {"kind": "api", "steps": [{"url": "/x", "sleep": 3}]},
            "uncertainty": "high",
        },
    ],
}
ANALYSIS = {
    "summary": "[Test double] Assertion mong đợi sai mã trạng thái",
    "probable_cause": "Bước mong đợi 418 nhưng ứng dụng trả 200",
    "category": "test_script",
    "confidence": "medium",
    "evidence": ["Bước 1: mã trạng thái 200"],
    "suggestions": ["Sửa assertion về 200"],
    "assumptions": ["Nội dung viết sẵn, không phải AI thật"],
}


@app.post("/v1/chat/completions")
def chat(body: dict[str, Any]) -> dict[str, Any]:
    system = str(body["messages"][0]["content"])
    content = ANALYSIS if "phân tích lỗi" in system else SUGGESTION
    return {
        "model": "fake-llm-test-double",
        "choices": [
            {
                "message": {"content": json.dumps(content, ensure_ascii=False)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
