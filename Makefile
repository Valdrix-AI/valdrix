# Valdrix Makefile
# Developer convenience commands using uv

.PHONY: help install dev test lint format security clean docker-build docker-up helm-install

# Default target
help:
	@echo "Valdrix Development Commands"
	@echo ""
	@echo "  make install     - Install dependencies with uv"
	@echo "  make dev         - Start development servers"
	@echo "  make test        - Run test suite"
	@echo "  make lint        - Run linters"
	@echo "  make format      - Format code"
	@echo "  make security    - Run security checks"
	@echo "  make clean       - Clean build artifacts"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-up     - Start with docker-compose"
	@echo "  make observability - Start Prometheus/Grafana stack"
	@echo ""
	@echo "Deployment:"
	@echo "  make helm-install  - Install to Kubernetes with Helm"
	@echo "  make migrate       - Run database migrations"

# Development
install:
	uv sync --dev
	cd dashboard && pnpm install

dev:
	@echo "Starting API server..."
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
	@echo "Starting dashboard..."
	cd dashboard && pnpm run dev

test:
	uv run pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

test-unit:
	uv run pytest tests/ -v --ignore=tests/integration --ignore=tests/security --ignore=tests/governance

test-fast:
	uv run pytest tests/ -x -q --tb=line

lint:
	uv run ruff check app/ tests/
	uv run ruff format --check app/ tests/

format:
	uv run ruff check --fix app/ tests/
	uv run ruff format app/ tests/

typecheck:
	uv run mypy app/ --ignore-missing-imports

security:
	uv run bandit -r app/ -ll -ii -s B101,B104
	@echo "Running Trivy scan..."
	trivy fs --severity HIGH,CRITICAL .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf __pycache__ app/__pycache__ tests/__pycache__
	rm -rf .coverage coverage.xml htmlcov
	rm -rf dist build *.egg-info

# Docker
docker-build:
	docker build -t valdrix:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

observability:
	docker-compose -f docker-compose.observability.yml up -d
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/valdrix)"
	@echo "Alertmanager: http://localhost:9093"

observability-down:
	docker-compose -f docker-compose.observability.yml down

# Database
migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"

# Kubernetes/Helm
helm-lint:
	helm lint helm/valdrix/

helm-template:
	helm template valdrix helm/valdrix/ --debug

helm-install:
	helm install valdrix helm/valdrix/ \
		--set existingSecrets.name=valdrix-secrets

helm-upgrade:
	helm upgrade valdrix helm/valdrix/

helm-uninstall:
	helm uninstall valdrix

# Pre-commit
hooks-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg

hooks-run:
	uv run pre-commit run --all-files

# OpenAPI
generate-client:
	./scripts/generate-api-client.sh

# ============================================================================
# Deployment (Koyeb)
# ============================================================================

deploy:
	@echo "🚀 Deploying to Koyeb..."
	koyeb app init valdrix --docker ghcr.io/valdrix-ai/valdrix:latest || true
	koyeb deploy -f koyeb.yaml
	@echo "✅ Koyeb deployment started"
	@echo "Dashboard: https://app.koyeb.com"

deploy-status:
	@echo "Koyeb status:"
	koyeb service list --app valdrix

