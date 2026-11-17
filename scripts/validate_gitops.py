#!/usr/bin/env python3
"""Validate Kaviont's Azure and local Argo CD configurations."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GITOPS_DIR = ROOT / "gitops" / "argocd"
LOCAL_DIR = GITOPS_DIR / "local"
CHART_DIR = ROOT / "charts" / "hello-api"
REPO_URL = "https://github.com/mohamadjaafri/kaviont-platform.git"

ALLOWED_RESOURCES = {
    ("apps", "Deployment"),
    ("", "Service"),
    ("", "ServiceAccount"),
    ("", "ConfigMap"),
    ("autoscaling", "HorizontalPodAutoscaler"),
    ("policy", "PodDisruptionBudget"),
    ("networking.k8s.io", "NetworkPolicy"),
}


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


def validate_project(project: dict, name: str, namespace: str) -> None:
    require(project.get("apiVersion") == "argoproj.io/v1alpha1", f"{name} AppProject apiVersion is incorrect.")
    require(project.get("kind") == "AppProject", f"{name} must be an AppProject.")
    spec = project.get("spec", {})
    require(spec.get("sourceRepos") == [REPO_URL], f"{name} AppProject must allow only the Kaviont repository.")
    require(
        spec.get("destinations") == [{"server": "https://kubernetes.default.svc", "namespace": namespace}],
        f"{name} AppProject must target only namespace {namespace}.",
    )
    require(spec.get("clusterResourceWhitelist") == [], f"{name} AppProject must deny cluster-scoped resources.")
    configured = {
        (item.get("group", ""), item.get("kind", ""))
        for item in spec.get("namespaceResourceWhitelist", [])
    }
    require(configured == ALLOWED_RESOURCES, f"{name} AppProject resource allowlist does not match the workload chart.")


def validate_application(application: dict, project_name: str, namespace: str, values_file: str) -> None:
    require(application.get("apiVersion") == "argoproj.io/v1alpha1", "Application apiVersion is incorrect.")
    require(application.get("kind") == "Application", "Expected an Application manifest.")
    metadata = application.get("metadata", {})
    spec = application.get("spec", {})
    require(metadata.get("namespace") == "argocd", "Application must be created in the argocd namespace.")
    require(spec.get("project") == project_name, f"Application must use project {project_name}.")

    source = spec.get("source", {})
    require(source.get("repoURL") == REPO_URL, "Application repository URL is incorrect.")
    require(source.get("targetRevision") == "main", "Application must track the main branch.")
    require(source.get("path") == "charts/hello-api", "Application must use the hello-api Helm chart.")
    require(source.get("helm", {}).get("valueFiles") == [values_file], f"Application must load {values_file}.")

    destination = spec.get("destination", {})
    require(destination.get("server") == "https://kubernetes.default.svc", "Application destination must be the in-cluster API.")
    require(destination.get("namespace") == namespace, f"Application destination must be namespace {namespace}.")

    sync = spec.get("syncPolicy", {})
    automated = sync.get("automated", {})
    require(automated.get("enabled") is True, "Automated sync must be enabled.")
    require(automated.get("prune") is True, "Automated pruning must be enabled.")
    require(automated.get("selfHeal") is True, "Automated self-healing must be enabled.")
    require(automated.get("allowEmpty") is False, "Automated sync must not allow an empty target.")
    require("CreateNamespace=true" not in sync.get("syncOptions", []), "The namespace must be created outside the restricted AppProject.")


def validate_kustomization(path: Path, expected_resources: set[str]) -> None:
    config = load_yaml(path)
    require(config.get("kind") == "Kustomization", f"{path.relative_to(ROOT)} kind is incorrect.")
    require(set(config.get("resources", [])) == expected_resources, f"{path.relative_to(ROOT)} resources are unexpected.")
    require(config.get("namespace") == "argocd", f"{path.relative_to(ROOT)} must target argocd.")


def main() -> int:
    try:
        # Azure/AKS profile.
        azure_project = load_yaml(GITOPS_DIR / "app-project.yaml")
        azure_application = load_yaml(GITOPS_DIR / "hello-api-application.yaml")
        azure_values = load_yaml(CHART_DIR / "values-gitops.yaml.example")
        validate_project(azure_project, "Azure", "demo")
        validate_application(azure_application, "kaviont-dev", "demo", "values-gitops.yaml")
        validate_kustomization(
            GITOPS_DIR / "kustomization.yaml",
            {"app-project.yaml", "hello-api-application.yaml"},
        )

        require(azure_values.get("workloadIdentity", {}).get("enabled") is True, "Azure GitOps values must enable Workload Identity.")
        require(azure_values.get("marketData", {}).get("enabled") is False, "Azure GitOps market data must remain disabled until an AKS database is configured.")
        require(azure_values.get("marketData", {}).get("worker", {}).get("enabled") is False, "Azure GitOps worker must remain disabled until an AKS database is configured.")
        require(azure_values.get("marketData", {}).get("pollIntervalSeconds") == 60, "Azure GitOps market-data polling must default to 60 seconds.")
        require(azure_values.get("marketData", {}).get("pair") == "XBTUSD", "Azure GitOps market-data pair must default to XBTUSD.")
        require(azure_values.get("image", {}).get("tag") == "0.9.0", "Azure GitOps values must pin the sample image tag.")
        require(
            str(azure_values.get("image", {}).get("repository", "")).startswith("REPLACE_WITH_ACR_LOGIN_SERVER/"),
            "Azure GitOps values template must use the ACR output marker.",
        )
        template_text = (CHART_DIR / "values-gitops.yaml.example").read_text(encoding="utf-8")
        for marker in ("REPLACE_WITH_HELLO_API_CLIENT_ID", "REPLACE_WITH_KEY_VAULT_URI"):
            require(marker in template_text, f"Missing Azure values template marker: {marker}")

        # Local profile. Its project, namespace, and values are intentionally distinct.
        local_project = load_yaml(LOCAL_DIR / "app-project.yaml")
        local_application = load_yaml(LOCAL_DIR / "hello-api-application.yaml")
        local_values = load_yaml(CHART_DIR / "values-local.yaml")
        validate_project(local_project, "Local", "kaviont-local")
        validate_application(local_application, "kaviont-local", "kaviont-local", "values-local.yaml")
        validate_kustomization(
            LOCAL_DIR / "kustomization.yaml",
            {"app-project.yaml", "hello-api-application.yaml", "otel-collector-application.yaml"},
        )

        # The local telemetry Collector is a separate, namespaced Argo CD application.
        collector_application = load_yaml(LOCAL_DIR / "otel-collector-application.yaml")
        collector_spec = collector_application.get("spec", {})
        require(collector_application.get("kind") == "Application", "Local Collector must be an Argo CD Application.")
        require(collector_application.get("metadata", {}).get("namespace") == "argocd", "Local Collector Application must live in argocd.")
        require(collector_spec.get("project") == "kaviont-local", "Local Collector must use the restricted local AppProject.")
        require(collector_spec.get("source", {}).get("repoURL") == REPO_URL, "Local Collector source repository is incorrect.")
        require(collector_spec.get("source", {}).get("targetRevision") == "main", "Local Collector must track main.")
        require(collector_spec.get("source", {}).get("path") == "gitops/argocd/local/otel-collector", "Local Collector path is incorrect.")
        require(collector_spec.get("destination", {}).get("namespace") == "kaviont-local", "Local Collector must deploy to kaviont-local.")
        collector_kustomization = load_yaml(LOCAL_DIR / "otel-collector" / "kustomization.yaml")
        require(
            collector_kustomization.get("kind") == "Kustomization"
            and set(collector_kustomization.get("resources", [])) == {
                "collector-config.yaml", "collector-deployment.yaml", "collector-services.yaml"
            },
            "Local Collector Kustomize resources are incomplete.",
        )
        collector_config_resource = load_yaml(LOCAL_DIR / "otel-collector" / "collector-config.yaml")
        collector_config = yaml.safe_load(collector_config_resource.get("data", {}).get("collector-config.yaml", ""))
        require(collector_config.get("service", {}).get("pipelines", {}).get("metrics", {}).get("exporters") == ["prometheus"], "Local Collector must export Kubernetes metrics to Prometheus.")
        collector_services = list(yaml.safe_load_all((LOCAL_DIR / "otel-collector" / "collector-services.yaml").read_text(encoding="utf-8")))
        require(any(service.get("metadata", {}).get("name") == "otel-collector" and service.get("spec", {}).get("type") == "ClusterIP" for service in collector_services), "Local Collector OTLP endpoint must be a ClusterIP service.")
        require(any(
            service.get("metadata", {}).get("name") == "otel-collector-metrics"
            and service.get("spec", {}).get("type") == "NodePort"
            and service.get("spec", {}).get("ports", [{}])[0].get("nodePort") == 30089
            for service in collector_services
        ), "Local Collector Prometheus endpoint must use NodePort 30089.")

        require(local_values.get("image", {}).get("repository") == "kaviont/hello-api", "Local values must use the local image.")
        require(local_values.get("image", {}).get("tag") == "local", "Local values must use the local image tag.")
        require(local_values.get("image", {}).get("pullPolicy") == "Never", "Local values must never pull the image from a registry.")
        require(local_values.get("telemetry", {}).get("enabled") is True, "Local Kubernetes API must export telemetry.")
        require(local_values.get("telemetry", {}).get("serviceName") == "hello-api-kubernetes", "Local Kubernetes API must have a distinct telemetry service name.")
        require(local_values.get("telemetry", {}).get("otlpEndpoint") == "http://otel-collector.kaviont-local.svc.cluster.local:4317", "Local Kubernetes API OTLP endpoint is incorrect.")
        require(local_values.get("service", {}).get("type") == "NodePort", "Local Kubernetes API must be reachable through its internal NodePort.")
        require(local_values.get("service", {}).get("nodePort") == 30081, "Local Kubernetes API NodePort must be 30081.")
        require(local_values.get("workloadIdentity", {}).get("enabled") is False, "Local values must disable Azure Workload Identity.")
        require(local_values.get("localSecret", {}).get("enabled") is True, "Local values must use the local-only test secret.")
        require(local_values.get("marketData", {}).get("enabled") is False, "Local kind profile must not start market-data without a shared database.")
        require(local_values.get("marketData", {}).get("worker", {}).get("enabled") is False, "Local kind profile must not deploy a worker without a shared database.")
        require(local_values.get("marketData", {}).get("pollIntervalSeconds") == 60, "Local market-data polling must default to 60 seconds.")
        require(local_values.get("marketData", {}).get("pair") == "XBTUSD", "Local market-data pair must default to XBTUSD.")
        require(local_values.get("autoscaling", {}).get("enabled") is False, "Local profile must not require metrics-server.")
        require(local_values.get("networkPolicy", {}).get("enabled") is False, "Local profile must not claim default kindnet enforces NetworkPolicy.")

    except (ValueError, TypeError, AttributeError) as exc:
        print(f"GitOps validation failed: {exc}", file=sys.stderr)
        return 1

    print("Azure and local Argo CD projects, applications, Kustomize entry points, and Helm values contracts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
