"""TEST-PACK-45 — chat routes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from kluris.pack.config import Config
from kluris.pack.main import create_app
from kluris.pack.providers.base import LLMProvider


class _ScriptedProvider(LLMProvider):
    """Provider that emits a single canned response."""

    model = "scripted"

    async def smoke_test(self) -> None:
        return None

    async def complete_stream(self, messages, tools):
        yield {"kind": "token", "text": "hello"}
        yield {"kind": "token", "text": " world"}
        yield {"kind": "usage", "input": 5, "output": 2}
        yield {"kind": "end"}


def _build_app(api_key_config: Config):
    return create_app(
        config=api_key_config,
        provider=_ScriptedProvider(),
        allow_writable_brain=True,
    )


def test_get_root_returns_html(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "<html" in resp.text.lower()
        assert "fixture-brain" in resp.text or "Fixture Brain" in resp.text


def test_get_root_sets_session_cookie(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get("/")
        assert "kluris_session" in resp.cookies


def test_post_chat_streams_tokens(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        # Establish session
        client.get("/")
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        # Drain the stream
        text = resp.text
        assert "data: " in text
        assert "[DONE]" in text


def test_post_chat_persists_history(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        client.get("/")
        client.post("/chat", json={"message": "first"})
        # Reload to confirm history replays
        resp = client.get("/")
        assert "first" in resp.text


def test_post_chat_persists_agent_error_when_no_text(api_key_config: Config):
    """If the agent emitted only an error (no tokens), the route must
    still persist something to history so a page reload shows the
    user that this turn failed — instead of a blank assistant block.
    """
    from kluris.pack.providers.base import LLMProvider

    class _EmptyResponseProvider(LLMProvider):
        """Provider that returns a bare ``end`` event — no tokens, no
        tool_use. The agent loop turns that into an error.
        """

        model = "empty"

        async def smoke_test(self) -> None:
            return None

        async def complete_stream(self, messages, tools):
            yield {"kind": "end"}

    app = create_app(
        config=api_key_config,
        provider=_EmptyResponseProvider(),
        allow_writable_brain=True,
    )
    with TestClient(app) as client:
        client.get("/")
        client.post("/chat", json={"message": "what is x?"})
        resp = client.get("/")
        # The error must be visible in the replayed history.
        assert "[error:" in resp.text
        assert "no content" in resp.text.lower()


def test_post_chat_empty_message_400(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        client.get("/")
        resp = client.post("/chat", json={"message": "   "})
        assert resp.status_code == 400


def test_brain_tree_endpoint_returns_lobes_and_glossary(api_key_config: Config):
    """``GET /api/brain/tree`` must return the same wake_up payload
    the LLM sees — lobes, recent, glossary, brain.md body. The
    sidebar in the chat UI builds the tree from this.
    """
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get("/api/brain/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        lobe_names = {l["name"] for l in data["lobes"]}
        # fixture brain has projects / knowledge / infrastructure
        assert {"projects", "knowledge", "infrastructure"} <= lobe_names
        # glossary terms come through
        gloss_terms = {e["term"] for e in data["glossary"]}
        assert "JWT" in gloss_terms
        # brain.md body present
        assert isinstance(data["brain_md"], str)


def test_brain_neuron_endpoint_returns_frontmatter_and_body(
    api_key_config: Config,
):
    """``GET /api/brain/neuron?path=…`` returns the neuron's
    frontmatter, body, and ``deprecated`` flag — sandboxed under
    the brain root.
    """
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get(
            "/api/brain/neuron",
            params={"path": "knowledge/jwt.md"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "JSON Web Tokens" in data["body"]
        assert data["deprecated"] is False
        assert isinstance(data["frontmatter"], dict)


def test_brain_neuron_endpoint_404_on_missing_path(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get(
            "/api/brain/neuron",
            params={"path": "knowledge/does-not-exist.md"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["ok"] is False
        assert "not_found" in data["error"]


def test_brain_neuron_endpoint_400_on_path_traversal(api_key_config: Config):
    """The sandbox rejects ``../`` traversal; the route maps that to
    a 400 — the chat UI never sees host filesystem content.
    """
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get(
            "/api/brain/neuron",
            params={"path": "../../etc/passwd"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False
        assert "sandbox" in data["error"]


def test_brain_lobe_endpoint_returns_overview(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get("/api/brain/lobe", params={"lobe": "knowledge"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["lobe"] == "knowledge"
        # map_body comes through verbatim (large budget set on the
        # endpoint so the human reader doesn't get truncation).
        assert isinstance(data["map_body"], str)
        # at least the JWT neuron is reachable from the knowledge lobe
        paths = {n["path"] for n in data["neurons"]}
        assert "knowledge/jwt.md" in paths


def test_brain_lobe_endpoint_404_on_missing_lobe(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        resp = client.get("/api/brain/lobe", params={"lobe": "does-not-exist"})
        assert resp.status_code == 404
        assert resp.json()["ok"] is False


def test_brain_endpoints_dont_require_auth(api_key_config: Config):
    """The brain explorer is intentionally unauthenticated — same
    threat model as the chat UI. Public exposure is the deployer's
    responsibility (reverse proxy / VPN / cloud IAM).
    """
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        for path in ("/api/brain/tree",
                     "/api/brain/neuron?path=knowledge/jwt.md",
                     "/api/brain/lobe?lobe=knowledge"):
            resp = client.get(path)
            assert resp.status_code == 200, (
                f"{path} should be reachable without auth, got {resp.status_code}"
            )
            assert "WWW-Authenticate" not in resp.headers


def test_post_chat_new_rotates_cookie(api_key_config: Config):
    app = _build_app(api_key_config)
    with TestClient(app) as client:
        first = client.get("/")
        old_cookie = first.cookies.get("kluris_session")
        new_resp = client.post("/chat/new")
        assert new_resp.status_code == 200
        new_cookie = new_resp.cookies.get("kluris_session")
        assert new_cookie and new_cookie != old_cookie
