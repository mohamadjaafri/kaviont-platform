"""Read-only GitHub API client for the Kaviont engineering portal."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from app.owasp_mapping import extract_cwes, map_owasp_2025

import httpx


class GitHubIntegrationNotConfigured(Exception):
    """Raised when a GitHub token has not been configured."""


class GitHubAPIError(Exception):
    """A sanitized GitHub API failure."""

    def __init__(self, status_code: int, message: str = "GitHub API request failed"):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class GitHubClient:
    """Minimal, read-only GitHub REST client with bounded pagination."""

    def __init__(
        self,
        token: str,
        *,
        api_url: str = "https://api.github.com",
        timeout_seconds: float = 12.0,
    ) -> None:
        self._token = token.strip()
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout_seconds

    @classmethod
    def from_environment(cls) -> "GitHubClient":
        token = (
            os.getenv("KAVIONT_GITHUB_TOKEN", "").strip()
            or os.getenv("GITHUB_TOKEN", "").strip()
        )
        if not token:
            raise GitHubIntegrationNotConfigured
        api_url = os.getenv("GITHUB_API_URL", "https://api.github.com").strip()
        if not api_url.startswith("https://"):
            raise ValueError("GITHUB_API_URL must use HTTPS")
        return cls(token, api_url=api_url)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Kaviont-Engineering-Platform",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = httpx.get(
                f"{self._api_url}{path}",
                headers=self._headers(),
                params=params,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise GitHubAPIError(504, "GitHub API timed out") from exc
        except httpx.HTTPError as exc:
            raise GitHubAPIError(502, "GitHub API is unavailable") from exc

        if response.status_code >= 400:
            if response.status_code in {401, 403, 404, 429}:
                message = {
                    401: "GitHub rejected the configured token",
                    403: "GitHub denied access or the API rate limit was reached",
                    404: "GitHub resource was not found or is not accessible",
                    429: "GitHub API rate limit was reached",
                }[response.status_code]
            else:
                message = "GitHub API request failed"
            raise GitHubAPIError(response.status_code, message)

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubAPIError(502, "GitHub returned an invalid response") from exc

    @staticmethod
    def _repo_path(owner: str, repo: str) -> str:
        safe_owner = quote(owner.strip(), safe="")
        safe_repo = quote(repo.strip(), safe="")
        if not safe_owner or not safe_repo or "/" in owner or "/" in repo:
            raise ValueError("owner and repo must be single path segments")
        return f"/repos/{safe_owner}/{safe_repo}"

    @staticmethod
    def _repository_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "full_name": item.get("full_name"),
            "description": item.get("description"),
            "html_url": item.get("html_url"),
            "private": bool(item.get("private")),
            "archived": bool(item.get("archived")),
            "fork": bool(item.get("fork")),
            "default_branch": item.get("default_branch"),
            "language": item.get("language"),
            "topics": item.get("topics") or [],
            "visibility": item.get("visibility"),
            "open_issues_count": item.get("open_issues_count", 0),
            "updated_at": item.get("updated_at"),
            "pushed_at": item.get("pushed_at"),
        }

    def list_repositories(
        self,
        *,
        search: str = "",
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        per_page = min(max(int(per_page), 1), 100)
        payload: list[dict[str, Any]] = []
        for page in range(1, 11):
            batch = self._get(
                "/user/repos",
                {
                    "affiliation": "owner,collaborator,organization_member",
                    "visibility": "all",
                    "sort": "pushed",
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page,
                },
            )
            if not isinstance(batch, list):
                raise GitHubAPIError(502, "GitHub returned an unexpected repository list")
            payload.extend(batch)
            if len(batch) < per_page:
                break
        items = [self._repository_summary(item) for item in payload]
        normalized_search = search.strip().lower()
        if normalized_search:
            items = [
                item for item in items
                if normalized_search in str(item.get("full_name", "")).lower()
                or normalized_search in str(item.get("description") or "").lower()
                or normalized_search in str(item.get("language") or "").lower()
                or any(normalized_search in topic.lower() for topic in item["topics"])
            ]
        return items

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        payload = self._get(self._repo_path(owner, repo))
        return self._repository_summary(payload)

    def workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        payload = self._get(
            f"{self._repo_path(owner, repo)}/actions/runs",
            {"per_page": min(max(per_page, 1), 50)},
        )
        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        return [
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "workflow_name": run.get("display_title") or run.get("name"),
                "run_number": run.get("run_number"),
                "event": run.get("event"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_branch": run.get("head_branch"),
                "head_sha": run.get("head_sha"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "html_url": run.get("html_url"),
            }
            for run in runs
        ]

    def open_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        payload = self._get(
            f"{self._repo_path(owner, repo)}/pulls",
            {"state": "open", "per_page": min(max(per_page, 1), 50), "sort": "updated"},
        )
        return [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "draft": item.get("draft"),
                "user": (item.get("user") or {}).get("login"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "html_url": item.get("html_url"),
                "head": (item.get("head") or {}).get("ref"),
                "base": (item.get("base") or {}).get("ref"),
            }
            for item in (payload if isinstance(payload, list) else [])
        ]

    def open_issues(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        payload = self._get(
            f"{self._repo_path(owner, repo)}/issues",
            {"state": "open", "per_page": min(max(per_page, 1), 50), "sort": "updated"},
        )
        return [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "user": (item.get("user") or {}).get("login"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "html_url": item.get("html_url"),
                "is_pull_request": "pull_request" in item,
            }
            for item in (payload if isinstance(payload, list) else [])
            if "pull_request" not in item
        ]

    @staticmethod
    def _dependabot_finding(item: dict[str, Any]) -> dict[str, Any]:
        vulnerability = item.get("security_vulnerability") or {}
        package = vulnerability.get("package") or {}
        advisory = item.get("security_advisory") or {}
        cwes = advisory.get("cwes") or []
        dependency = item.get("dependency") or {}
        return {
            "source": "Dependabot",
            "kind": "dependency",
            "number": item.get("number"),
            "state": item.get("state"),
            "severity": vulnerability.get("severity") or advisory.get("severity") or "unknown",
            "package": package.get("name"),
            "ecosystem": package.get("ecosystem"),
            "manifest": dependency.get("manifest_path"),
            "summary": advisory.get("summary") or advisory.get("description"),
            "ghsa_id": advisory.get("ghsa_id"),
            "cve_id": next(
                (identifier.get("value") for identifier in advisory.get("identifiers", [])
                 if identifier.get("type") == "CVE"),
                None,
            ),
            "cwes": [cwe.get("cwe_id") for cwe in cwes if cwe.get("cwe_id")],
            "fixed_in": (vulnerability.get("first_patched_version") or {}).get("identifier"),
            "owasp_mapping": map_owasp_2025(dependency=True),
            "created_at": item.get("created_at"),
            "html_url": item.get("html_url"),
        }

    @staticmethod
    def _code_scanning_finding(item: dict[str, Any]) -> dict[str, Any]:
        rule = item.get("rule") or {}
        tool = item.get("tool") or {}
        instances = item.get("most_recent_instance") or {}
        location = instances.get("location") or {}
        physical = location.get("physical_location") or {}
        artifact = physical.get("artifact_location") or {}
        region = physical.get("region") or {}
        tags = rule.get("tags") or []
        cwes = extract_cwes(tags)
        return {
            "source": tool.get("name") or "Code Scanning",
            "kind": "code",
            "number": item.get("number"),
            "state": item.get("state"),
            "severity": (
                rule.get("security_severity_level")
                or rule.get("severity")
                or item.get("rule", {}).get("security_severity_level")
                or "unknown"
            ),
            "rule_id": rule.get("id"),
            "cwes": cwes,
            "owasp_mapping": map_owasp_2025(tags),
            "summary": rule.get("description") or rule.get("name"),
            "file": artifact.get("uri"),
            "line": region.get("start_line"),
            "created_at": item.get("created_at"),
            "html_url": item.get("html_url"),
        }

    def security_findings(self, owner: str, repo: str) -> dict[str, Any]:
        base = self._repo_path(owner, repo)
        sources: dict[str, dict[str, Any]] = {}
        findings: list[dict[str, Any]] = []

        for source, endpoint, mapper in (
            (
                "dependabot",
                f"{base}/dependabot/alerts",
                self._dependabot_finding,
            ),
            (
                "code_scanning",
                f"{base}/code-scanning/alerts",
                self._code_scanning_finding,
            ),
        ):
            try:
                payload = self._get(endpoint, {"state": "open", "per_page": 100})
                items = payload if isinstance(payload, list) else []
                sources[source] = {"status": "available", "count": len(items)}
                findings.extend(mapper(item) for item in items)
            except GitHubAPIError as exc:
                if exc.status_code == 404:
                    state = "not_enabled_or_not_available"
                elif exc.status_code == 403:
                    state = "missing_permission_or_plan"
                elif exc.status_code == 401:
                    state = "invalid_token"
                else:
                    state = "unavailable"
                sources[source] = {"status": state, "count": 0}

        severity_order = {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}
        findings.sort(
            key=lambda item: (
                severity_order.get(str(item.get("severity", "")).lower(), 4),
                str(item.get("created_at") or ""),
            )
        )
        counts = {key: 0 for key in ("critical", "high", "medium", "low", "unknown")}
        for finding in findings:
            severity = str(finding.get("severity") or "unknown").lower()
            if severity == "moderate":
                severity = "medium"
            counts[severity if severity in counts else "unknown"] += 1

        return {
            "repository": f"{owner}/{repo}",
            "frameworks": {"owasp_top_10": "2025", "owasp_asvs": "5.0.0", "mapping_note": "Heuristic source-to-category mapping; not an ASVS compliance assessment."},
            "sources": sources,
            "total_open": len(findings),
            "counts": counts,
            "findings": findings,
        }

    def list_knowledge_documents(self) -> list[dict[str, Any]]:
        knowledge_repository = os.getenv("KAVIONT_KNOWLEDGE_REPOSITORY", "mohamadjaafri/kaviont-platform").strip()
        owner, separator, name = knowledge_repository.partition("/")
        if not separator or not owner or not name or "/" in name:
            raise ValueError("KAVIONT_KNOWLEDGE_REPOSITORY must use owner/name format")
        payload = self._get(f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/contents/docs")
        if not isinstance(payload, list):
            return []
        return [
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "type": item.get("type"),
                "html_url": item.get("html_url"),
            }
            for item in payload
            if item.get("type") == "file"
            and str(item.get("name", "")).lower().endswith((".md", ".mdx"))
        ]
