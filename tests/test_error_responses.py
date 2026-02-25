import pytest
from fastapi.testclient import TestClient

from app.github_client import RepoFile
from app.llm_client import LLMError
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _assert_error_shape(response, expected_status_code: int):
    assert response.status_code == expected_status_code
    data = response.json()
    assert data["status"] == "error"
    assert isinstance(data["message"], str)
    assert data["message"]


def test_missing_github_url_returns_error_shape(client):
    response = client.post("/summarize", json={})
    _assert_error_shape(response, 422)


def test_invalid_github_url_returns_error_shape(client):
    response = client.post("/summarize", json={"github_url": "not-a-github-url"})
    _assert_error_shape(response, 422)


def test_wrong_type_github_url_returns_error_shape(client):
    response = client.post("/summarize", json={"github_url": 123})
    _assert_error_shape(response, 422)


def test_malformed_json_body_returns_error_shape(client):
    response = client.post(
        "/summarize",
        data='{"github_url":',
        headers={"Content-Type": "application/json"},
    )
    _assert_error_shape(response, 422)


def test_missing_nebius_api_key_returns_error_shape(client, monkeypatch):
    async def fake_get_default_branch(self, owner, repo):
        return "main"

    async def fake_get_repo_tree(self, owner, repo, branch):
        return [RepoFile(path="README.md", size=100)]

    async def fake_collect_repo_context(*args, **kwargs):
        return "repo context"

    monkeypatch.setattr(
        "app.main.GitHubClient.get_default_branch",
        fake_get_default_branch,
    )
    monkeypatch.setattr(
        "app.main.GitHubClient.get_repo_tree",
        fake_get_repo_tree,
    )
    monkeypatch.setattr(
        "app.main.collect_repo_context",
        fake_collect_repo_context,
    )
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    response = client.post(
        "/summarize",
        json={"github_url": "https://github.com/psf/requests"},
    )
    _assert_error_shape(response, 500)
    assert "NEBIUS_API_KEY is not set" in response.json()["message"]


def test_invalid_nebius_api_key_returns_auth_message(client, monkeypatch):
    async def fake_get_default_branch(self, owner, repo):
        return "main"

    async def fake_get_repo_tree(self, owner, repo, branch):
        return [RepoFile(path="README.md", size=100)]

    async def fake_collect_repo_context(*args, **kwargs):
        return "repo context"

    class _FakeLLMClient:
        async def summarize(self, owner, repo, context):
            raise LLMError("LLM API call failed: Error code: 401 - Couldn't authenticate")

    monkeypatch.setattr(
        "app.main.GitHubClient.get_default_branch",
        fake_get_default_branch,
    )
    monkeypatch.setattr(
        "app.main.GitHubClient.get_repo_tree",
        fake_get_repo_tree,
    )
    monkeypatch.setattr(
        "app.main.collect_repo_context",
        fake_collect_repo_context,
    )
    monkeypatch.setattr("app.main._get_llm_client", lambda: _FakeLLMClient())
    monkeypatch.setenv("NEBIUS_API_KEY", "invalid-key")

    response = client.post(
        "/summarize",
        json={"github_url": "https://github.com/psf/requests"},
    )
    _assert_error_shape(response, 500)
    assert "authentication failed" in response.json()["message"].lower()

