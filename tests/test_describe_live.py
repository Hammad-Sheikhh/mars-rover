"""Live photo descriptions, with the vision AI replaced by a fake: no internet, no key."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from earth_station import config
from earth_station.describe import DescribeError, _describe_live, describe

PHOTO = b"\xff\xd8\xff\xe0 pretend jpeg \xff\xd9"
SCENE = {
    "summary": "Table leg about 40 cm ahead. Open floor to the right.",
    "obstacle_ahead": True,
    "clear_side": "right",
    "hazards": ["cable on floor"],
}


class FakeClaude:
    """Answers like client.beta.messages.create, and remembers the request."""

    def __init__(self, text="", stop_reason="end_turn", error=None):
        self.text, self.stop_reason, self.error = text, stop_reason, error
        self.request = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **request):
        self.request = request
        if self.error:
            raise self.error
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=self.text)],
        )


@pytest.fixture
def live(settings):
    return replace(settings, describe_mode="live", vision_api_key="test-key")


def run(jpeg, s, fake):
    return asyncio.run(_describe_live(jpeg, s, client=fake))


def test_good_answer_becomes_a_scene(live):
    fake = FakeClaude(json.dumps(SCENE))
    assert run(PHOTO, live, fake) == SCENE


def test_request_sends_the_photo_and_asks_for_the_agreed_shape(live):
    fake = FakeClaude(json.dumps(SCENE))
    run(PHOTO, live, fake)
    req = fake.request
    assert req["model"] == "claude-opus-5-5"
    image, prompt = req["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/jpeg"
    assert "rover" in prompt["text"]
    fmt = req["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert set(fmt["schema"]["required"]) == set(SCENE)
    assert req["output_config"]["effort"] == "low"
    assert req["fallbacks"] == "default"


def test_models_without_fallback_support_get_no_fallback(live):
    fake = FakeClaude(json.dumps(SCENE))
    run(PHOTO, replace(live, vision_model="claude-haiku-4-5"), fake)
    assert "fallbacks" not in fake.request and "betas" not in fake.request


def test_not_a_jpeg_is_rejected_before_calling_claude(live):
    fake = FakeClaude(json.dumps(SCENE))
    with pytest.raises(DescribeError, match="JPEG"):
        run(b"<html>oops</html>", live, fake)
    assert fake.request is None


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        (FakeClaude("{}", stop_reason="refusal"), "declined"),
        (FakeClaude('{"summary": "Tab', stop_reason="max_tokens"), "cut off"),
        (FakeClaude("not json"), "agreed format"),
    ],
)
def test_bad_answers_become_describe_errors(live, fake, message):
    with pytest.raises(DescribeError, match=message):
        run(PHOTO, live, fake)


def _http_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("nope", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (_http_error(anthropic.AuthenticationError, 401), "VISION_API_KEY"),
        (_http_error(anthropic.RateLimitError, 429), "rate limit"),
        (_http_error(anthropic.InternalServerError, 500), "error 500"),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "online",
        ),
    ],
)
def test_api_problems_become_describe_errors(live, error, message):
    # The station catches DescribeError, logs it and keeps going: the safety
    # gate then stops the rover because the scene gets too old.
    with pytest.raises(DescribeError, match=message):
        run(PHOTO, live, FakeClaude(error=error))


def test_answer_still_goes_through_the_shape_check(live, monkeypatch):
    too_long = dict(SCENE, summary="x" * 400)
    fake = FakeClaude(json.dumps(too_long))
    monkeypatch.setattr("earth_station.describe._client", lambda s: fake)
    with pytest.raises(DescribeError, match="too long"):
        asyncio.run(describe(PHOTO, live))


def test_live_mode_needs_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DESCRIBE_MODE", "live")
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="VISION_API_KEY"):
        config.load(env_file=tmp_path / "missing.env")


def test_effort_must_be_a_known_level(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_EFFORT", "turbo")
    with pytest.raises(config.ConfigError, match="VISION_EFFORT"):
        config.load(env_file=tmp_path / "missing.env")


# ============================== Gemini ========================================

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent"
GEMINI_OK = {
    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(SCENE)}]}}]
}


class FakeGemini:
    """Answers like httpx2.AsyncClient.post to Gemini, and remembers the request."""

    def __init__(self, data=None, status=200, error=None):
        self.data, self.status, self.error = data, status, error
        self.request = None

    async def post(self, path, json=None):
        self.request = {"path": path, "json": json}
        if self.error:
            raise self.error
        request = httpx2.Request("POST", GEMINI_URL)
        response = httpx2.Response(self.status, request=request, json=self.data)
        response.raise_for_status()
        return response


@pytest.fixture
def gemini(live):
    return replace(live, vision_provider="gemini", vision_model="gemini-flash-lite-latest")


def run_gemini(jpeg, s, fake):
    return asyncio.run(_describe_live(jpeg, s, client=fake))


def test_gemini_good_answer_becomes_a_scene(gemini):
    assert run_gemini(PHOTO, gemini, FakeGemini(GEMINI_OK)) == SCENE


def test_gemini_request_sends_photo_schema_and_no_thinking(gemini):
    fake = FakeGemini(GEMINI_OK)
    run_gemini(PHOTO, gemini, fake)
    req = fake.request
    assert req["path"].endswith("models/gemini-flash-lite-latest:generateContent")
    image, prompt = req["json"]["contents"][0]["parts"]
    assert image["inline_data"]["mime_type"] == "image/jpeg"
    assert "rover" in prompt["text"]
    cfg = req["json"]["generationConfig"]
    # Flash-Lite cannot switch thinking off (the API 400s), so nothing is sent.
    assert "thinkingConfig" not in cfg
    schema = cfg["responseSchema"]
    assert set(schema["required"]) == set(SCENE)
    assert "additionalProperties" not in schema


def test_gemini_flash_models_that_can_get_thinking_budget_zero(gemini):
    fake = FakeGemini(GEMINI_OK)
    run_gemini(PHOTO, replace(gemini, vision_model="gemini-3-flash"), fake)
    cfg = fake.request["json"]["generationConfig"]
    assert cfg["thinkingConfig"] == {"thinkingBudget": 0}


def test_gemini_prompt_mentions_the_focus_list(gemini):
    fake = FakeGemini(GEMINI_OK)
    run_gemini(PHOTO, replace(gemini, vision_focus="stairs or drops"), fake)
    prompt = fake.request["json"]["contents"][0]["parts"][1]["text"]
    assert "stairs or drops" in prompt


def test_gemini_not_a_jpeg_is_rejected_before_calling(gemini):
    fake = FakeGemini(GEMINI_OK)
    with pytest.raises(DescribeError, match="JPEG"):
        run_gemini(b"<html>oops</html>", gemini, fake)
    assert fake.request is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        # SAFETY/RECITATION finish, or no candidates at all: no description.
        ({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}, "declined"),
        ({}, "declined"),
        (
            {
                "candidates": [
                    {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"sum'}]}}
                ]
            },
            "cut off",
        ),
        (
            {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}
                ]
            },
            "agreed format",
        ),
    ],
)
def test_gemini_bad_answers_become_describe_errors(gemini, data, message):
    with pytest.raises(DescribeError, match=message):
        run_gemini(PHOTO, gemini, FakeGemini(data))


def _gemini_http_error(status, message):
    request = httpx2.Request("POST", GEMINI_URL)
    body = {"error": {"code": status, "message": message}}
    response = httpx2.Response(status, request=request, json=body)
    return httpx2.HTTPStatusError("nope", request=request, response=response)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            _gemini_http_error(400, "API key not valid. Please pass a valid API key."),
            "VISION_API_KEY",
        ),
        (_gemini_http_error(403, "PERMISSION_DENIED"), "VISION_API_KEY"),
        (_gemini_http_error(429, "RESOURCE_EXHAUSTED"), "rate limit"),
        (_gemini_http_error(400, "Invalid JSON payload received."), "error 400"),
        (_gemini_http_error(500, "INTERNAL"), "error 500"),
        (
            httpx2.ConnectError(
                "nope", request=httpx2.Request("POST", "https://generativelanguage.googleapis.com")
            ),
            "online",
        ),
        (
            httpx2.ReadTimeout(
                "slow", request=httpx2.Request("POST", "https://generativelanguage.googleapis.com")
            ),
            "took too long",
        ),
    ],
)
def test_gemini_api_problems_become_describe_errors(gemini, error, message):
    with pytest.raises(DescribeError, match=message):
        run_gemini(PHOTO, gemini, FakeGemini(error=error))


def test_gemini_live_mode_needs_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DESCRIBE_MODE", "live")
    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="aistudio.google.com"):
        config.load(env_file=tmp_path / "missing.env")


def test_provider_must_be_known(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_PROVIDER", "openai")
    with pytest.raises(config.ConfigError, match="VISION_PROVIDER"):
        config.load(env_file=tmp_path / "missing.env")
