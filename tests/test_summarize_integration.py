import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _skip_if_no_api_key():
    if not os.environ.get("NEBIUS_API_KEY"):
        pytest.skip("NEBIUS_API_KEY not set - skipping integration test")


@pytest.mark.integration
class TestSummarizeIntegration:
    """Optional integration tests that hit the real GitHub + LLM APIs. Skipped by default in pytest.ini"""

    def _check_valid_summary(self, client, github_url):
        _skip_if_no_api_key()
        response = client.post("/summarize", json={"github_url": github_url})

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()

        assert isinstance(data.get("summary"), str)
        assert len(data["summary"]) > 10
        assert isinstance(data.get("technologies"), list)
        assert len(data["technologies"]) > 0
        assert isinstance(data.get("structure"), str)
        assert len(data["structure"]) > 10

    def test_popular_repo_returns_valid_summary(self, client):
        self._check_valid_summary(client, "https://github.com/psf/requests")

    def test_huge_repo_returns_valid_summary(self, client):
        self._check_valid_summary(client, "https://github.com/git/git")
