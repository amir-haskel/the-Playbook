# Developer shortcuts. Everything here is also what CI runs.
IMAGE        ?= playbook
TAG          ?= dev
RELEASE      ?= playbook
NAMESPACE    ?= playbook
CHART        := charts/playbook
ADMIN_PASSWORD ?= changeme

.PHONY: help run seed test lint image chart-lint chart-template install uninstall screenshots

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

run: ## Run the app locally on :8000 (scripts come from the chart)
	ADMIN_PASSWORD=$(ADMIN_PASSWORD) SESSION_SECRET=local-dev DATA_DIR=./data \
		python -m uvicorn app.main:app --reload --port 8000

seed: ## Load the demo catalog into a running instance (and run a few actions)
	python hack/seed_demo.py --url http://localhost:8000 --password $(ADMIN_PASSWORD) --run

test: ## Unit tests
	ADMIN_PASSWORD=test python -m pytest -q

lint: ## Python + shell lint
	ruff check app tests hack $(CHART)/scripts --select E9,F63,F7,F82,F401
	find $(CHART)/scripts -name '*.sh' -print0 | xargs -0 shellcheck

image: ## Build the container image
	docker build -t $(IMAGE):$(TAG) .

chart-lint: ## helm lint with every CI values file
	helm lint $(CHART) --strict
	for f in $(CHART)/ci/*-values.yaml; do helm lint $(CHART) --strict -f $$f; done

chart-template: ## Render the chart to stdout
	helm template $(RELEASE) $(CHART) -n $(NAMESPACE)

install: ## Install/upgrade the chart into the current kube context
	helm upgrade --install $(RELEASE) $(CHART) -n $(NAMESPACE) --create-namespace --wait \
		--set image.repository=$(IMAGE) --set image.tag=$(TAG)

uninstall: ## Remove the release (PVCs are kept on purpose)
	helm uninstall $(RELEASE) -n $(NAMESPACE)

screenshots: ## Regenerate docs/images from a running, seeded instance
	python hack/screenshots.py --url http://localhost:8000 --password $(ADMIN_PASSWORD)
