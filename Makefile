TF_DIR := infrastructure/terraform/environments/dev
APP_DIR := workloads/hello-api
CHART_DIR := charts/hello-api

.PHONY: fmt fmt-check terraform-validate app-test helm-check image-build

fmt:
	terraform fmt -recursive infrastructure/terraform

fmt-check:
	terraform fmt -check -recursive infrastructure/terraform

terraform-validate:
	terraform -chdir=$(TF_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_DIR) validate

app-test:
	python -m pip install -r $(APP_DIR)/requirements.txt -r $(APP_DIR)/requirements-dev.txt
	PYTHONPATH=$(APP_DIR) python -m pytest $(APP_DIR)/tests -q

helm-check:
	helm lint $(CHART_DIR)
	helm template hello-api $(CHART_DIR) >/dev/null

image-build:
	docker build -t kaviont/hello-api:dev $(APP_DIR)
