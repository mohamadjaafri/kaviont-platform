from fastapi.testclient import TestClient

from app.main import app
from app.github_integration import GitHubAPIError, GitHubClient

client = TestClient(app)


class FakeGitHubClient:
    def list_repositories(self, *, search="", per_page=50):
        return [
            {
                "id": 1,
                "name": "api",
                "full_name": "example/api",
                "description": "Example API",
                "html_url": "https://github.com/example/api",
                "private": True,
                "archived": False,
                "fork": False,
                "default_branch": "main",
                "language": "Python",
                "topics": ["service", "fastapi"],
                "visibility": "private",
                "open_issues_count": 2,
                "updated_at": "2026-11-20T10:00:00Z",
                "pushed_at": "2026-11-20T10:00:00Z",
            },
            {
                "id": 2,
                "name": "infra",
                "full_name": "example/infra",
                "description": "Terraform foundation",
                "html_url": "https://github.com/example/infra",
                "private": False,
                "archived": False,
                "fork": False,
                "default_branch": "main",
                "language": "HCL",
                "topics": ["terraform", "platform"],
                "visibility": "public",
                "open_issues_count": 0,
                "updated_at": "2026-11-19T10:00:00Z",
                "pushed_at": "2026-11-19T10:00:00Z",
            },
        ]

    def get_repository(self, owner, repo):
        return {
            "full_name": f"{owner}/{repo}",
            "html_url": f"https://github.com/{owner}/{repo}",
            "private": True,
            "default_branch": "main",
            "language": "Python",
            "topics": ["service"],
            "open_issues_count": 2,
        }

    def open_pull_requests(self, owner, repo, per_page=20):
        return [{"number": 7, "title": "Improve API", "html_url": "https://github.com/example/api/pull/7"}]

    def open_issues(self, owner, repo, per_page=20):
        return [{"number": 8, "title": "Add tests", "html_url": "https://github.com/example/api/issues/8"}]

    def workflow_runs(self, owner, repo, per_page=20):
        return [
            {"id": 12, "name": "CI", "status": "completed", "conclusion": "failure", "html_url": "https://github.com/example/api/actions/runs/12"},
            {"id": 11, "name": "CI", "status": "completed", "conclusion": "success", "html_url": "https://github.com/example/api/actions/runs/11"},
        ]

    def security_findings(self, owner, repo):
        return {
            "repository": f"{owner}/{repo}",
            "frameworks": {
                "owasp_top_10": "2025",
                "owasp_asvs": "5.0.0",
                "mapping_note": "heuristic",
            },
            "sources": {
                "dependabot": {"status": "available", "count": 1},
                "code_scanning": {"status": "available", "count": 1},
            },
            "total_open": 2,
            "counts": {"critical": 1, "high": 1, "medium": 0, "low": 0, "unknown": 0},
            "findings": [
                {"source": "Dependabot", "severity": "critical", "owasp_mapping": "A03:2025 Software Supply Chain Failures"},
                {"source": "CodeQL", "severity": "high", "owasp_mapping": "A05:2025 Injection"},
            ],
        }

    def list_knowledge_documents(self):
        return [{"name": "architecture.md", "path": "docs/architecture.md", "type": "file", "html_url": "https://github.com/example/api/blob/main/docs/architecture.md"}]


def test_engineering_status_reports_integrations(monkeypatch):
    monkeypatch.setenv("KAVIONT_GITHUB_TOKEN", "test-token")
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("KUBERNETES_API_URL", raising=False)

    response = client.get("/v1/engineering/status")

    assert response.status_code == 200
    assert response.json()["github_configured"] is True
    assert response.json()["kubernetes_configured"] is False


def test_engineering_status_does_not_require_github_token(monkeypatch):
    monkeypatch.delenv("KAVIONT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    response = client.get("/v1/engineering/status")

    assert response.status_code == 200
    assert response.json()["github_configured"] is False


def test_list_repositories(monkeypatch):
    import app.engineering_api as api
    monkeypatch.setattr(api, "get_github_client", lambda: FakeGitHubClient())

    response = client.get("/v1/engineering/repositories")

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["repositories"][0]["full_name"] == "example/api"


def test_repository_detail_returns_pull_requests_and_issues(monkeypatch):
    import app.engineering_api as api
    monkeypatch.setattr(api, "get_github_client", lambda: FakeGitHubClient())

    response = client.get("/v1/engineering/repositories/example/api")

    assert response.status_code == 200
    assert response.json()["repository"]["full_name"] == "example/api"
    assert response.json()["open_pull_requests"][0]["number"] == 7
    assert response.json()["open_issues"][0]["number"] == 8


def test_pipeline_route_summarizes_run_conclusions(monkeypatch):
    import app.engineering_api as api
    monkeypatch.setattr(api, "get_github_client", lambda: FakeGitHubClient())

    response = client.get("/v1/engineering/repositories/example/api/pipelines")

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["failed"] == 1
    assert response.json()["successful"] == 1


def test_security_route_exposes_owasp_versions_and_findings(monkeypatch):
    import app.engineering_api as api
    monkeypatch.setattr(api, "get_github_client", lambda: FakeGitHubClient())

    response = client.get("/v1/engineering/repositories/example/api/security")

    assert response.status_code == 200
    assert response.json()["frameworks"]["owasp_top_10"] == "2025"
    assert response.json()["frameworks"]["owasp_asvs"] == "5.0.0"
    assert response.json()["counts"]["critical"] == 1
    assert response.json()["findings"][0]["owasp_mapping"].startswith("A03:2025")


def test_service_catalog_uses_repository_topics(monkeypatch):
    import app.engineering_api as api
    monkeypatch.setattr(api, "get_github_client", lambda: FakeGitHubClient())

    response = client.get("/v1/engineering/services")

    assert response.status_code == 200
    services = response.json()["services"]
    assert services[0]["service_type"] == "microservice"
    assert services[1]["service_type"] == "infrastructure"
    assert services[0]["owner_team"] is None


def test_knowledge_route_lists_repository_documents(monkeypatch):
    import app.engineering_api as api
    monkeypatch.setattr(api, "get_github_client", lambda: FakeGitHubClient())

    response = client.get("/v1/engineering/knowledge")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["documents"][0]["name"] == "architecture.md"


def test_template_catalog_lists_engineering_blueprints():
    response = client.get("/v1/engineering/templates")

    assert response.status_code == 200
    template_ids = {item["id"] for item in response.json()["templates"]}
    assert {"python-fastapi-service", "terraform-module", "helm-workload"} <= template_ids


def test_github_integration_requires_token(monkeypatch):
    monkeypatch.delenv("KAVIONT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    response = client.get("/v1/engineering/repositories")

    assert response.status_code == 503
    assert "KAVIONT_GITHUB_TOKEN" in response.json()["detail"]


def test_kubernetes_endpoint_reports_disabled_without_cluster(monkeypatch):
    import app.engineering_api as api
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("KUBERNETES_API_URL", raising=False)
    monkeypatch.setattr(api.os.path, "isfile", lambda _path: False)

    response = client.get("/v1/engineering/kubernetes")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["pods"] == []


def test_github_client_filters_repositories_and_sends_token(monkeypatch):
    payload = [
        {
            "id": 1,
            "name": "platform",
            "full_name": "example/platform",
            "description": "Internal platform",
            "html_url": "https://github.com/example/platform",
            "private": True,
            "archived": False,
            "fork": False,
            "default_branch": "main",
            "language": "Python",
            "topics": ["platform"],
            "visibility": "private",
            "open_issues_count": 0,
            "updated_at": None,
            "pushed_at": None,
        },
        {
            "id": 2,
            "name": "docs",
            "full_name": "example/docs",
            "description": "Documentation",
            "html_url": "https://github.com/example/docs",
            "private": False,
            "archived": False,
            "fork": False,
            "default_branch": "main",
            "language": "Markdown",
            "topics": [],
            "visibility": "public",
            "open_issues_count": 0,
            "updated_at": None,
            "pushed_at": None,
        },
    ]
    seen = {}

    def fake_get(url, headers, params, timeout, follow_redirects):
        seen["url"] = url
        seen["authorization"] = headers["Authorization"]
        return __import__("httpx").Response(200, json=payload, request=__import__("httpx").Request("GET", url))

    import app.github_integration as github
    monkeypatch.setattr(github.httpx, "get", fake_get)
    client_instance = GitHubClient("secret-token")

    results = client_instance.list_repositories(search="platform")

    assert seen["authorization"] == "Bearer secret-token"
    assert len(results) == 1
    assert results[0]["full_name"] == "example/platform"


def test_owasp_mapping_does_not_force_unknown_cwe():
    from app.owasp_mapping import map_owasp_2025

    assert map_owasp_2025(["external/cwe/cwe-89"]) == "A05:2025 Injection"
    assert map_owasp_2025(["CWE-999999"]) is None
    assert map_owasp_2025(dependency=True) == "A03:2025 Software Supply Chain Failures"
