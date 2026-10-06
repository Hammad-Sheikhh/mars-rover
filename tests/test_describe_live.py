"""Live photo descriptions, with Claude replaced by a fake: no internet, no key."""

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
