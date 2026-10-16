"""Lớp AI: định dạng request tới nhà cung cấp, xử lý lỗi, kiểm tra kết quả bằng schema (dùng test double)."""

import json

import httpx
import pytest
from omnitest_ai.providers import AIConfig, AIError, OpenAICompatibleProvider, build_provider
from omnitest_ai.tasks import analyze_failure, extract_json, suggest_test_cases

from tests.ai.fakes import API_DRAFT, FAKE_KEY, FakeAnthropic


def test_disabled_without_configuration() -> None:
    assert build_provider(AIConfig(provider="none", model="x")) is None
    assert build_provider(AIConfig(provider="anthropic", model="x")) is None  # thiếu khóa
    assert build_provider(AIConfig(provider="openai_compatible", model="x")) is None  # thiếu URL


async def test_anthropic_request_format_and_valid_draft() -> None:
    fake = FakeAnthropic({"assumptions": ["A"], "test_cases": [API_DRAFT]})
    res = await suggest_test_cases(fake.provider(), "Kiểm tra API health của kho hàng", "api", 3)
    req = fake.requests[0]
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == FAKE_KEY and req.headers["anthropic-version"] == "2023-06-01"
    body = fake.sent_body()
    assert body["model"] == "claude-test-double" and body["max_tokens"] == 4096
    # Yêu cầu của người dùng nằm trong thẻ dữ liệu, tách khỏi chỉ dẫn hệ thống; schema định nghĩa có trong system.
    assert (
        "<du_lieu>\nKiểm tra API health của kho hàng\n</du_lieu>" in body["messages"][0]["content"]
    )
    assert '"ApiStep"' in body["system"]
    assert res.assumptions == ["A"] and (res.input_tokens, res.output_tokens) == (123, 45)
    d = res.drafts[0]
    assert d.valid and d.errors == [] and d.test_type == "api" and d.uncertainty == "low"
    assert d.definition["steps"][0]["method"] == "GET"  # đã chuẩn hóa theo schema


async def test_invalid_definitions_are_flagged_not_dropped() -> None:
    bad_step = {
        **API_DRAFT,
        "title": "Sai",
        "definition": {"kind": "api", "steps": [{"url": "/x", "sleep": 5}]},
    }
    wrong_kind = {
        **API_DRAFT,
        "title": "Sai loại",
        "definition": {"kind": "web", "steps": [{"name": "a", "action": "goto", "value": "/"}]},
    }
    fake = FakeAnthropic({"test_cases": [API_DRAFT, bad_step, wrong_kind]})
    res = await suggest_test_cases(fake.provider(), "Yêu cầu bất kỳ đủ dài", "api", 5)
    assert [d.valid for d in res.drafts] == [True, False, False]
    assert any("sleep" in e for e in res.drafts[1].errors)
    assert "không đúng loại" in res.drafts[2].errors[0]


async def test_count_limit_and_fenced_json() -> None:
    reply = "```json\n" + json.dumps({"test_cases": [API_DRAFT] * 4}) + "\n```"
    res = await suggest_test_cases(
        FakeAnthropic(reply).provider(), "Yêu cầu bất kỳ đủ dài", "api", 2
    )
    assert len(res.drafts) == 2
    assert extract_json('Đây là kết quả: {"a": 1} xong') == {"a": 1}


@pytest.mark.parametrize(
    ("reply", "status", "stop", "message"),
    [
        ("không phải JSON", 200, "end_turn", "JSON"),
        ({"test_cases": "x"}, 200, "end_turn", "cấu trúc"),
        ({"test_cases": []}, 200, "max_tokens", "bị cắt"),
        ({}, 401, "end_turn", "xác thực"),
        ({}, 429, "end_turn", "tần suất"),
        ({}, 500, "end_turn", "đang lỗi"),
    ],
)
async def test_errors_are_clear_and_never_contain_key(
    reply: object, status: int, stop: str, message: str
) -> None:
    fake = FakeAnthropic(reply, status=status, stop_reason=stop)
    with pytest.raises(AIError, match=message) as exc:
        await suggest_test_cases(fake.provider(), "Yêu cầu bất kỳ đủ dài", "api", 1)
    assert FAKE_KEY not in str(exc.value)


async def test_network_error_and_timeout() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("hết giờ")

    cfg = AIConfig(provider="openai_compatible", model="m", base_url="http://llm.local/v1")
    p = OpenAICompatibleProvider(cfg, transport=httpx.MockTransport(boom))
    with pytest.raises(AIError, match="Hết thời gian"):
        await p.complete("s", "u")


async def test_openai_compatible_format() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            200,
            json={
                "model": "llama",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    cfg = AIConfig(
        provider="openai_compatible", model="llama", base_url="http://llm.local/v1/", api_key="k"
    )
    res = await OpenAICompatibleProvider(cfg, transport=httpx.MockTransport(handler)).complete(
        "hệ thống", "người dùng"
    )
    assert str(seen[0].url) == "http://llm.local/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert [m["role"] for m in json.loads(seen[0].content)["messages"]] == ["system", "user"]
    assert (res.text, res.input_tokens, res.output_tokens) == ("{}", 7, 3)


async def test_failure_analysis_schema() -> None:
    fake = FakeAnthropic(
        {
            "summary": "Thiếu token",
            "probable_cause": "Bước gọi /api/items không gửi Authorization",
            "category": "test_script",
            "confidence": "high",
            "evidence": ["Bước 1: mã 401"],
            "suggestions": ["Thêm bước đăng nhập"],
        }
    )
    res = await analyze_failure(fake.provider(), {"steps": [{"error": "401"}]})
    assert res.category == "test_script" and res.assumptions == []
    with pytest.raises(AIError):
        await analyze_failure(FakeAnthropic({"summary": "x", "category": "khác"}).provider(), {})
