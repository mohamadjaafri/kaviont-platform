TF_BOOTSTRAP_DIR := infrastructure/terraform/bootstrap/state
TF_DIR := infrastructure/terraform/environments/dev
APP_DIR := workloads/hello-api
CHART_DIR := charts/hello-api

.PHONY: fmt fmt-check terraform-bootstrap-validate terraform-validate app-test helm-check gitops-check image-build dev-up dev-logs dev-down container-test local-up local-build local-status local-forward local-down

fmt:
	terraform fmt -recursive infrastructure/terraform

fmt-check:
	terraform fmt -check -recursive infrastructure/terraform

terraform-bootstrap-validate:
	terraform -chdir=$(TF_BOOTSTRAP_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_BOOTSTRAP_DIR) validate

terraform-validate:
	terraform -chdir=$(TF_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_DIR) validate

app-test:
	python -m pip install -r $(APP_DIR)/requirements.txt -r $(APP_DIR)/requirements-dev.txt
	PYTHONPATH=$(APP_DIR) python -m pytest $(APP_DIR)/tests -q

helm-check:
	helm lint $(CHART_DIR)
	helm template hello-api $(CHART_DIR) >/dev/null

gitops-check:
	python -m pip install "PyYAML>=6,<7"
	python scripts/validate_gitops.py
	helm lint $(CHART_DIR) --values $(CHART_DIR)/values-gitops.yaml.example
	helm template hello-api $(CHART_DIR) --namespace demo --values $(CHART_DIR)/values-gitops.yaml.example >/dev/null

image-build:
	docker build -t kaviont/hello-api:dev $(APP_DIR)

# Container-first development. No host Python environment is required.
dev-up:
	docker compose --profile dev up --build -d

dev-logs:
	docker compose --profile dev logs -f hello-api

dev-down:
	docker compose --profile dev down --remove-orphans

container-test:
	docker compose --profile test run --build --rm hello-api-test

# Full local Kubernetes/GitOps environment. Requires Docker, kind, kubectl and OpenSSL.
local-up:
	bash scripts/local-up.sh

local-build:
	bash scripts/local-build.sh

local-status:
	kubectl --context kind-kaviont-local get applications -n argocd
	kubectl --context kind-kaviont-local get pods,svc -n kaviont-local

local-forward:
	kubectl --context kind-kaviont-local port-forward -n kaviont-local svc/hello-api-local 8081:80

local-down:
	bash scripts/local-down.sh
