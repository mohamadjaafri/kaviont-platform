"""Deterministic starter blueprints for the engineering self-service catalog."""

from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "python-fastapi-service": {
        "name": "python-fastapi-service",
        "description": "FastAPI service with a health endpoint, tests, Dockerfile and CI security scan workflow.",
        "files": {
            "app/main.py": """from fastapi import FastAPI

app = FastAPI(title="Engineering Service", version="0.1.0")


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}
""",
            "tests/test_health.py": """from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
""",
            "requirements.txt": "fastapi>=0.115,<1.0\\nuvicorn[standard]>=0.34,<1.0\\n",
            "requirements-dev.txt": "-r requirements.txt\\nhttpx>=0.27,<1.0\\npytest>=8,<9\\n",
            "Dockerfile": """FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --uid 10001 --no-create-home app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
""",
            ".github/workflows/ci.yml": """name: Service CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt
      - run: pytest -q
  security:
    uses: mohamadjaafri/kaviont-platform/.github/workflows/reusable-security.yml@main
    permissions:
      actions: read
      contents: read
      security-events: write
    with:
      run_dependency_check: false
""",
            ".gitignore": ".venv/\\n__pycache__/\\n.pytest_cache/\\n.env\\n",
            "README.md": """# Python FastAPI Service

## Local development

    python -m venv .venv
    . .venv/bin/activate
    pip install -r requirements-dev.txt
    uvicorn app.main:app --reload

## Tests

    pytest -q

## Security

The CI workflow calls the reusable Kaviont security workflow for CodeQL, Trivy, Gitleaks and an SBOM. Enable GitHub Code Scanning and grant the workflow security-events write permission.
""",
        },
    },
    "node-service": {
        "name": "node-service",
        "description": "Node.js HTTP service with built-in tests, non-root container and CI.",
        "files": {
            "src/server.js": """const http = require("node:http");

const server = http.createServer((request, response) => {
  if (request.url === "/healthz") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: "ok" }));
    return;
  }
  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ error: "not_found" }));
});

if (require.main === module) {
  const port = Number(process.env.PORT || 8080);
  server.listen(port, "0.0.0.0");
}

module.exports = { server };
""",
            "test/server.test.js": """const test = require("node:test");
const assert = require("node:assert/strict");
const { server } = require("../src/server");

test("health endpoint returns ok", async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  try {
    const response = await fetch("http://127.0.0.1:" + address.port + "/healthz");
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok" });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
""",
            "package.json": """{
  "name": "engineering-node-service",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "start": "node src/server.js",
    "test": "node --test"
  },
  "engines": {
    "node": ">=22"
  }
}
""",
            "Dockerfile": """FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /app
COPY --chown=node:node package.json .
COPY --chown=node:node src ./src
USER node
EXPOSE 8080
CMD ["node", "src/server.js"]
""",
            ".github/workflows/ci.yml": """name: Service CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm test
  security:
    uses: mohamadjaafri/kaviont-platform/.github/workflows/reusable-security.yml@main
    permissions:
      actions: read
      contents: read
      security-events: write
    with:
      run_dependency_check: false
""",
            ".gitignore": "node_modules/\\n.env\\ncoverage/\\n",
            "README.md": """# Node.js Service

Run the service with npm start. Run tests with npm test. The workflow includes the reusable Kaviont code and dependency security checks.
""",
        },
    },
    "terraform-module": {
        "name": "terraform-module",
        "description": "Reusable Terraform module with typed inputs, outputs and validation workflow.",
        "files": {
            "versions.tf": """terraform {
  required_version = ">= 1.8.0"
}
""",
            "main.tf": """locals {
  resource_name = var.name
}

resource "terraform_data" "example" {
  input = {
    name        = local.resource_name
    environment = var.environment
    tags        = var.tags
  }
}
""",
            "variables.tf": """variable "name" {
  description = "Resource identifier."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.name))
    error_message = "name must contain 3-40 lowercase letters, numbers or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod."
  }
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
""",
            "outputs.tf": """output "resource_name" {
  description = "Configured resource name."
  value       = terraform_data.example.output.name
}
""",
            "examples/basic/main.tf": """module "example" {
  source      = "../.."
  name        = "example-service"
  environment = "dev"
  tags = {
    managed-by = "terraform"
  }
}
""",
            ".github/workflows/ci.yml": """name: Terraform CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.11.4"
      - run: terraform fmt -check -recursive
      - run: terraform init -backend=false
      - run: terraform validate
  security:
    uses: mohamadjaafri/kaviont-platform/.github/workflows/reusable-security.yml@main
    permissions:
      actions: read
      contents: read
      security-events: write
    with:
      run_dependency_check: false
""",
            ".gitignore": ".terraform/\\n*.tfstate\\n*.tfstate.*\\n*.tfvars\\n",
            "README.md": """# Terraform Module

This is a reusable module skeleton. Review the example, run terraform fmt -recursive, then initialize and validate from the module root. Add provider-specific resources and tests before use.
""",
        },
    },
    "helm-workload": {
        "name": "helm-workload",
        "description": "Kubernetes Helm chart with non-root security context, probes, resource limits and Service.",
        "files": {
            "Chart.yaml": """apiVersion: v2
name: engineering-workload
description: Hardened Kubernetes workload starter
type: application
version: 0.1.0
appVersion: "0.1.0"
""",
            "values.yaml": """replicaCount: 1
image:
  repository: ghcr.io/example/service
  tag: "0.1.0"
  pullPolicy: IfNotPresent
service:
  port: 80
  targetPort: 8080
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi
""",
            "templates/deployment.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "engineering-workload.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ include "engineering-workload.fullname" . }}
  template:
    metadata:
      labels:
        app: {{ include "engineering-workload.fullname" . }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.service.targetPort }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
""",
            "templates/service.yaml": """apiVersion: v1
kind: Service
metadata:
  name: {{ include "engineering-workload.fullname" . }}
spec:
  selector:
    app: {{ include "engineering-workload.fullname" . }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: http
""",
            "templates/_helpers.tpl": """{{- define "engineering-workload.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
""",
            "README.md": """# Helm Workload

Update the image and values, then validate with helm lint . and helm template demo .. The default container security context assumes the application supports a read-only filesystem and non-root UID.
""",
        },
    },
}


def list_templates() -> list[dict[str, Any]]:
    catalog = [
        ("python-fastapi-service", "application", ["Python", "FastAPI", "Docker", "GitHub Actions"]),
        ("node-service", "application", ["Node.js", "HTTP", "Docker", "GitHub Actions"]),
        ("terraform-module", "infrastructure", ["Terraform", "HCL", "GitHub Actions"]),
        ("helm-workload", "platform", ["Kubernetes", "Helm", "Security Context"]),
    ]
    return [
        {
            "id": template_id,
            "name": TEMPLATES[template_id]["name"],
            "category": category,
            "description": TEMPLATES[template_id]["description"],
            "status": "downloadable",
            "stack": stack,
        }
        for template_id, category, stack in catalog
    ]


def get_template(template_id: str) -> dict[str, Any] | None:
    return TEMPLATES.get(template_id)
