"""Engineering portal API routes for repository, delivery and runtime intelligence."""

from __future__ import annotations

import io
import os
import re
import zipfile
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.engineering_templates import get_template, list_templates
from app.github_integration import (
    GitHubAPIError,
    GitHubClient,
    GitHubIntegrationNotConfigured,
)

router = APIRouter(prefix="/v1/engineering", tags=["engineering"])


def get_github_client() -> GitHubClient:
    return GitHubClient.from_environment()


def _client_or_503() -> GitHubClient:
    try:
        return get_github_client()
    except GitHubIntegrationNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail="GitHub integration is not configured. Set KAVIONT_GITHUB_TOKEN.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _github_error(exc: GitHubAPIError) -> HTTPException:
    if exc.status_code in {401, 403, 404, 429, 502, 504}:
        return HTTPException(status_code=exc.status_code, detail=exc.message)
    return HTTPException(status_code=502, detail="GitHub API request failed")


@router.get("/status")
def engineering_status() -> dict[str, Any]:
    token_configured = bool(
        os.getenv("KAVIONT_GITHUB_TOKEN", "").strip()
        or os.getenv("GITHUB_TOKEN", "").strip()
    )
    return {
        "github_configured": token_configured,
        "github_api_url": os.getenv("GITHUB_API_URL", "https://api.github.com"),
        "kubernetes_configured": bool(
            os.getenv("KUBERNETES_API_URL", "").strip()
            or os.getenv("KUBERNETES_SERVICE_HOST", "").strip()
        ),
        "modules": {
            "repositories": "github",
            "security": "github_code_scanning_and_dependabot",
            "pipelines": "github_actions",
            "runtime": "kubernetes_read_only",
            "cloud_iac": "trivy_and_terraform",
            "knowledge": "repository_docs",
            "self_service": "template_catalog",
        },
    }


@router.get("/overview")
def engineering_overview() -> dict[str, Any]:
    client = _client_or_503()
    try:
        repositories = client.list_repositories(per_page=100)
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc

    languages: dict[str, int] = {}
    for repository in repositories:
        language = repository.get("language") or "Other"
        languages[language] = languages.get(language, 0) + 1

    return {
        "repository_count": len(repositories),
        "private_count": sum(1 for item in repositories if item["private"]),
        "public_count": sum(1 for item in repositories if not item["private"]),
        "archived_count": sum(1 for item in repositories if item["archived"]),
        "languages": [
            {"language": language, "count": count}
            for language, count in sorted(
                languages.items(), key=lambda entry: (-entry[1], entry[0])
            )
        ],
        "recent_repositories": repositories[:8],
    }


@router.get("/repositories")
def list_repositories(
    search: str = Query(default="", max_length=100),
    per_page: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    client = _client_or_503()
    try:
        repositories = client.list_repositories(search=search, per_page=per_page)
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc
    return {"count": len(repositories), "repositories": repositories}


@router.get("/repositories/{owner}/{repo}")
def repository_detail(owner: str, repo: str) -> dict[str, Any]:
    client = _client_or_503()
    try:
        repository = client.get_repository(owner, repo)
        pulls = client.open_pull_requests(owner, repo, per_page=10)
        issues = client.open_issues(owner, repo, per_page=10)
    except (GitHubAPIError, ValueError) as exc:
        if isinstance(exc, GitHubAPIError):
            raise _github_error(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "repository": repository,
        "open_pull_requests": pulls,
        "open_issues": issues,
    }


@router.get("/repositories/{owner}/{repo}/pipelines")
def repository_pipelines(owner: str, repo: str) -> dict[str, Any]:
    client = _client_or_503()
    try:
        runs = client.workflow_runs(owner, repo)
    except (GitHubAPIError, ValueError) as exc:
        if isinstance(exc, GitHubAPIError):
            raise _github_error(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "repository": f"{owner}/{repo}",
        "count": len(runs),
        "runs": runs,
        "failed": sum(
            1 for run in runs
            if run.get("conclusion") in {"failure", "timed_out", "startup_failure"}
        ),
        "successful": sum(1 for run in runs if run.get("conclusion") == "success"),
    }


@router.get("/repositories/{owner}/{repo}/security")
def repository_security(owner: str, repo: str) -> dict[str, Any]:
    client = _client_or_503()
    try:
        return client.security_findings(owner, repo)
    except (GitHubAPIError, ValueError) as exc:
        if isinstance(exc, GitHubAPIError):
            raise _github_error(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/services")
def service_catalog() -> dict[str, Any]:
    """Use GitHub repositories as the initial service catalog source."""
    client = _client_or_503()
    try:
        repositories = client.list_repositories(per_page=100)
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc

    services = [
        {
            **item,
            "service_type": (
                "microservice" if "service" in item["topics"]
                else "infrastructure" if any(
                    topic in item["topics"] for topic in ("terraform", "infrastructure", "platform")
                )
                else "library" if any(
                    topic in item["topics"] for topic in ("library", "sdk", "package")
                )
                else "repository"
            ),
            "owner_team": None,
            "lifecycle": "unknown",
            "criticality": "unclassified",
        }
        for item in repositories
    ]
    return {"count": len(services), "services": services}


@router.get("/security/frameworks")
def security_frameworks() -> dict[str, Any]:
    return {
        "owasp_top_10": {
            "version": "2025",
            "url": "https://top10.owasp.org/2025/",
            "categories": [
                {"id": "A01:2025", "name": "Broken Access Control"},
                {"id": "A02:2025", "name": "Security Misconfiguration"},
                {"id": "A03:2025", "name": "Software Supply Chain Failures"},
                {"id": "A04:2025", "name": "Cryptographic Failures"},
                {"id": "A05:2025", "name": "Injection"},
                {"id": "A06:2025", "name": "Insecure Design"},
                {"id": "A07:2025", "name": "Authentication Failures"},
                {"id": "A08:2025", "name": "Software or Data Integrity Failures"},
                {"id": "A09:2025", "name": "Security Logging and Alerting Failures"},
                {"id": "A10:2025", "name": "Mishandling of Exceptional Conditions"},
            ],
        },
        "owasp_asvs": {
            "version": "5.0.0",
            "url": "https://asvs.owasp.org/",
            "purpose": "Security verification requirements; automated scan findings do not establish ASVS compliance.",
        },
    }


@router.get("/cloud")
def cloud_iac_inventory() -> dict[str, Any]:
    """Discover infrastructure repositories; provider flags show config presence only."""
    client = _client_or_503()
    try:
        repositories = client.list_repositories(per_page=100)
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc

    infrastructure = [
        item for item in repositories
        if str(item.get("language") or "").lower() in {"hcl", "bicep"}
        or any(
            topic in item.get("topics", [])
            for topic in ("terraform", "infrastructure", "iac", "platform", "cloud")
        )
    ]
    return {
        "infrastructure_repository_count": len(infrastructure),
        "infrastructure_repositories": infrastructure,
        "provider_configuration": {
            "azure": {
                "configuration_present": bool(
                    os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
                    and os.getenv("AZURE_TENANT_ID", "").strip()
                ),
                "inventory_status": "not_connected",
            },
            "aws": {
                "configuration_present": bool(
                    os.getenv("AWS_ROLE_ARN", "").strip()
                    or os.getenv("AWS_PROFILE", "").strip()
                ),
                "inventory_status": "not_connected",
            },
            "gcp": {
                "configuration_present": bool(
                    os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
                    or os.getenv("GCP_PROJECT", "").strip()
                ),
                "inventory_status": "not_connected",
            },
        },
        "message": "Cloud provider configuration is not the same as a verified cloud inventory connection.",
    }


@router.get("/kubernetes")
def kubernetes_runtime() -> dict[str, Any]:
    """Read namespaced pod/deployment health using the service-account identity."""
    api_url = os.getenv("KUBERNETES_API_URL", "").strip()
    service_host = os.getenv("KUBERNETES_SERVICE_HOST", "").strip()
    service_port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443").strip()
    api_url = api_url or (
        f"https://{service_host}:{service_port}" if service_host else ""
    )
    namespace = os.getenv("KAVIONT_KUBERNETES_NAMESPACE", "default").strip()
    parsed_api_url = urlparse(api_url)
    namespace_valid = bool(
        re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", namespace)
        and len(namespace) <= 63
    )
    api_url_valid = bool(
        parsed_api_url.scheme == "https"
        and parsed_api_url.hostname
        and not parsed_api_url.username
        and not parsed_api_url.password
        and parsed_api_url.path in ("", "/")
        and not parsed_api_url.query
        and not parsed_api_url.fragment
    )
    if not namespace_valid or (api_url and not api_url_valid):
        return {
            "configured": False,
            "authorized": False,
            "namespace": namespace,
            "message": "Kubernetes namespace or API URL configuration is invalid.",
            "deployments": [],
            "pods": [],
            "events": [],
        }
    token_path = os.getenv(
        "KUBERNETES_TOKEN_FILE",
        "/var/run/secrets/kubernetes.io/serviceaccount/token",
    )
    ca_path = os.getenv(
        "KUBERNETES_CA_FILE",
        "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
    )

    if not api_url or not os.path.isfile(token_path):
        return {
            "configured": False,
            "namespace": namespace,
            "message": "Kubernetes read-only access is not configured for this deployment.",
            "deployments": [],
            "pods": [],
        }

    try:
        with open(token_path, encoding="utf-8") as token_file:
            token = token_file.read().strip()
        verify: str | bool = ca_path if os.path.isfile(ca_path) else True
        with httpx.Client(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=8.0,
            verify=verify,
        ) as client:
            deployment_response = client.get(
                f"/apis/apps/v1/namespaces/{namespace}/deployments"
            )
            pod_response = client.get(f"/api/v1/namespaces/{namespace}/pods")
            event_response = client.get(
                f"/api/v1/namespaces/{namespace}/events",
                params={"limit": 30},
            )
        for response in (deployment_response, pod_response, event_response):
            if response.status_code == 403:
                return {
                    "configured": True,
                    "authorized": False,
                    "namespace": namespace,
                    "message": "The Kaviont service account needs read-only access to pods, deployments and events.",
                    "deployments": [],
                    "pods": [],
                    "events": [],
                }
            response.raise_for_status()

        deployment_items = deployment_response.json().get("items", [])
        pod_items = pod_response.json().get("items", [])
        event_items = event_response.json().get("items", [])
        deployments = []
        for item in deployment_items:
            status = item.get("status", {})
            spec = item.get("spec", {})
            deployments.append({
                "name": item.get("metadata", {}).get("name"),
                "replicas": spec.get("replicas", 0),
                "ready_replicas": status.get("readyReplicas", 0),
                "available_replicas": status.get("availableReplicas", 0),
                "updated_replicas": status.get("updatedReplicas", 0),
                "image": (
                    (spec.get("template", {}).get("spec", {}).get("containers") or [{}])[0].get("image")
                ),
            })
        pods = []
        for item in pod_items:
            status = item.get("status", {})
            container_statuses = status.get("containerStatuses") or []
            pods.append({
                "name": item.get("metadata", {}).get("name"),
                "phase": status.get("phase"),
                "node": item.get("spec", {}).get("nodeName"),
                "restarts": sum(int(container.get("restartCount", 0)) for container in container_statuses),
                "ready": all(
                    container.get("ready", False) for container in container_statuses
                ) if container_statuses else False,
            })
        events = [
            {
                "type": item.get("type"),
                "reason": item.get("reason"),
                "message": item.get("message"),
                "object": (item.get("involvedObject") or {}).get("name"),
                "last_timestamp": item.get("lastTimestamp") or item.get("eventTime"),
            }
            for item in event_items
        ]
        return {
            "configured": True,
            "authorized": True,
            "namespace": namespace,
            "deployment_count": len(deployments),
            "pod_count": len(pods),
            "not_ready_pods": sum(1 for pod in pods if not pod["ready"]),
            "restart_count": sum(pod["restarts"] for pod in pods),
            "deployments": deployments,
            "pods": pods,
            "events": events,
        }
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return {
            "configured": True,
            "authorized": False,
            "namespace": namespace,
            "message": "Kubernetes API could not be queried. Check the service account and cluster connection.",
            "deployments": [],
            "pods": [],
            "events": [],
        }


@router.get("/knowledge")
def engineering_knowledge() -> dict[str, Any]:
    client = _client_or_503()
    try:
        documents = client.list_knowledge_documents()
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc
    return {"count": len(documents), "documents": documents}


@router.get("/templates")
def engineering_templates() -> dict[str, Any]:
    templates = list_templates()
    return {"count": len(templates), "templates": templates}


@router.get("/templates/{template_id}/download")
def download_engineering_template(template_id: str) -> Response:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Engineering template not found")

    archive = io.BytesIO()
    archive_root = f"kaviont-{template_id}"
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative_path, content in template["files"].items():
            if relative_path.startswith("/") or ".." in relative_path.split("/"):
                raise HTTPException(status_code=500, detail="Template contains an unsafe file path")
            bundle.writestr(f"{archive_root}/{relative_path}", content)

    filename = f"kaviont-{template_id}.zip"
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
