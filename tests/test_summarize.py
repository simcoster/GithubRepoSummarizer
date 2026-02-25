import pytest
from fastapi.testclient import TestClient

from app.github_client import RepoFile
from app.main import app
from app.models import SummarizeResponse


@pytest.fixture()
def client():
    return TestClient(app)
def _mock_github_client(monkeypatch: pytest.MonkeyPatch, files_with_content: dict[str, str]):
    async def fake_get_default_branch(self, owner, repo):
        return "main"

    async def fake_get_repo_tree(self, owner, repo, branch):
        return [
            RepoFile(path=path, size=len(content), download_url=f"https://example.test/{path}")
            for path, content in files_with_content.items()
        ]

    async def fake_fetch_file_content(self, file: RepoFile):
        return files_with_content.get(file.path)

    monkeypatch.setattr("app.main.GitHubClient.get_default_branch", fake_get_default_branch)
    monkeypatch.setattr("app.main.GitHubClient.get_repo_tree", fake_get_repo_tree)
    monkeypatch.setattr("app.main.GitHubClient.fetch_file_content", fake_fetch_file_content)


class _FakeLLMClient:
    def __init__(self, result: SummarizeResponse, capture: dict[str, str]):
        self._result = result
        self._capture = capture

    async def summarize(self, owner: str, repo: str, context: str) -> SummarizeResponse:
        self._capture["owner"] = owner
        self._capture["repo"] = repo
        self._capture["context"] = context
        return self._result


class TestSummarizeDeterministic:
    def test_returns_expected_summary_and_context_contains_evidence(self, client, monkeypatch):
        files = {
            "README.md": "# Requests\nPython HTTP library for humans.",
            "requests/api.py": "import http.client\n\ndef get(url):\n    return url\n",
            "tests/test_api.py": "def test_get():\n    assert True\n",
            "pyproject.toml": "[project]\nname='requests'\n",
        }
        _mock_github_client(monkeypatch, files)

        expected = SummarizeResponse(
            summary="Requests is a Python HTTP client library focused on simple, human-friendly API usage.",
            technologies=["Python", "HTTP"],
            structure="Core request logic lives in the requests package while tests cover behavior from a separate tests directory.",
        )
        capture: dict[str, str] = {}
        monkeypatch.setattr("app.main._get_llm_client", lambda: _FakeLLMClient(expected, capture))

        response = client.post("/summarize", json={"github_url": "https://github.com/psf/requests"})

        assert response.status_code == 200
        assert response.json() == expected.model_dump()

        # Validate that pipeline context includes concrete repository evidence.
        assert capture["owner"] == "psf"
        assert capture["repo"] == "requests"
        assert "## Directory Structure" in capture["context"]
        assert "README.md" in capture["context"]
        assert "requests/api.py" in capture["context"]
        assert "tests/test_api.py" in capture["context"]

    def test_empty_repo_returns_400(self, client, monkeypatch):
        async def fake_get_default_branch(self, owner, repo):
            return "main"

        async def fake_get_repo_tree(self, owner, repo, branch):
            return []

        monkeypatch.setattr("app.main.GitHubClient.get_default_branch", fake_get_default_branch)
        monkeypatch.setattr("app.main.GitHubClient.get_repo_tree", fake_get_repo_tree)

        response = client.post("/summarize", json={"github_url": "https://github.com/acme/empty-repo"})

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "Repository appears to be empty."

    def test_invalid_url_returns_422(self, client):
        response = client.post("/summarize", json={"github_url": "not-a-github-url"})
        assert response.status_code == 422

    def test_missing_github_url_returns_422(self, client):
        response = client.post("/summarize", json={})
        assert response.status_code == 422
