#!/usr/bin/env python3
"""Validate Kaviont Argo CD manifests and their Helm values contract."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GITOPS_DIR = ROOT / "gitops" / "argocd"
CHART_DIR = ROOT / "charts" / "hello-api"
REPO_URL = "https://github.com/mohamadjaafri/kaviont-platform.git"


def load_yaml(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot parse {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a YAML mapping.")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    try:
        project = load_yaml(GITOPS_DIR / "app-project.yaml")
        application = load_yaml(GITOPS_DIR / "hello-api-application.yaml")
        kustomization = load_yaml(GITOPS_DIR / "kustomization.yaml")
        values = load_yaml(CHART_DIR / "values-gitops.yaml.example")

        require(project.get("apiVersion") == "argoproj.io/v1alpha1", "AppProject apiVersion is incorrect.")
        require(project.get("kind") == "AppProject", "Expected an AppProject manifest.")
        project_spec = project.get("spec", {})
        require(project_spec.get("sourceRepos") == [REPO_URL], "AppProject must allow only the Kaviont repository.")
        require(
            project_spec.get("destinations") == [
                {"server": "https://kubernetes.default.svc", "namespace": "demo"}
            ],
            "AppProject must target only the in-cluster demo namespace.",
        )
        require(project_spec.get("clusterResourceWhitelist") == [], "AppProject must not allow cluster-scoped resources.")

        allowed_resources = {
            ("apps", "Deployment"),
            ("", "Service"),
            ("", "ServiceAccount"),
            ("autoscaling", "HorizontalPodAutoscaler"),
            ("policy", "PodDisruptionBudget"),
            ("networking.k8s.io", "NetworkPolicy"),
        }
        configured_resources = {
            (item.get("group", ""), item.get("kind", ""))
            for item in project_spec.get("namespaceResourceWhitelist", [])
        }
        require(configured_resources == allowed_resources, "AppProject resource allowlist does not match the hello-api chart.")

        require(application.get("apiVersion") == "argoproj.io/v1alpha1", "Application apiVersion is incorrect.")
        require(application.get("kind") == "Application", "Expected an Application manifest.")
        app_meta = application.get("metadata", {})
        app_spec = application.get("spec", {})
        require(app_meta.get("namespace") == "argocd", "Application must be created in the argocd namespace.")
        require(app_spec.get("project") == "kaviont-dev", "Application must use the restricted Kaviont project.")

        source = app_spec.get("source", {})
        require(source.get("repoURL") == REPO_URL, "Application repository URL is incorrect.")
        require(source.get("targetRevision") == "main", "Application must track the main branch.")
        require(source.get("path") == "charts/hello-api", "Application must use the hello-api Helm chart.")
        require(
            source.get("helm", {}).get("valueFiles") == ["values-gitops.yaml"],
            "Application must load the generated GitOps values file.",
        )

        destination = app_spec.get("destination", {})
        require(destination.get("server") == "https://kubernetes.default.svc", "Application destination must be the in-cluster API.")
        require(destination.get("namespace") == "demo", "Application destination must be the demo namespace.")

        sync_policy = app_spec.get("syncPolicy", {})
        automated = sync_policy.get("automated", {})
        require(automated.get("enabled") is True, "Automated sync must be enabled.")
        require(automated.get("prune") is True, "Automated pruning must be enabled.")
        require(automated.get("selfHeal") is True, "Automated self-healing must be enabled.")
        require(automated.get("allowEmpty") is False, "Automated sync must not allow an empty target.")
        require("CreateNamespace=true" in sync_policy.get("syncOptions", []), "Argo CD must create the demo namespace.")

        require(kustomization.get("kind") == "Kustomization", "Kustomize manifest kind is incorrect.")
        require(
            set(kustomization.get("resources", [])) == {"app-project.yaml", "hello-api-application.yaml"},
            "Kustomize resources must include only the project and hello-api application.",
        )
        require(kustomization.get("namespace") == "argocd", "Kustomize must target the argocd namespace.")

        require(values.get("workloadIdentity", {}).get("enabled") is True, "GitOps values must enable Workload Identity.")
        require(values.get("image", {}).get("tag") == "0.2.0", "GitOps values must pin the sample image tag.")
        require(
            str(values.get("image", {}).get("repository", "")).startswith("REPLACE_WITH_ACR_LOGIN_SERVER/"),
            "GitOps values template must use the ACR output marker.",
        )
        for marker in (
            "REPLACE_WITH_HELLO_API_CLIENT_ID",
            "REPLACE_WITH_KEY_VAULT_URI",
        ):
            require(marker in (CHART_DIR / "values-gitops.yaml.example").read_text(encoding="utf-8"), f"Missing template marker: {marker}")

    except (ValueError, TypeError, AttributeError) as exc:
        print(f"GitOps validation failed: {exc}", file=sys.stderr)
        return 1

    print("Argo CD project, application, Kustomize entry point, and Helm values contract are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
