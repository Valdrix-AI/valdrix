# Contributing to Valdrix

Thank you for your interest in contributing to Valdrix! This guide will help you get started.

## Development Setup

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Docker (for running tests with PostgreSQL)
- Node.js 20+ (for dashboard development)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/Valdrix-AI/valdrix.git
cd valdrix

# Install dependencies
uv sync --dev

# Copy environment template
cp .env.example .env

# Run tests
uv run pytest
```

## Code Quality

### Linting
We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
uv run ruff check .
uv run ruff format .
```

### Type Checking
Ensure type hints are present for all public functions.

### Testing
All new code should include tests. We use pytest with async support:

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_zombie_detector.py -v

# Run with coverage
uv run pytest --cov=app
```

## Pull Request Process

1. **Fork** the repository
2. **Create a branch** from `main` with a descriptive name
3. **Make your changes** following our coding standards
4. **Add tests** for any new functionality
5. **Run the test suite** and ensure all tests pass
6. **Submit a PR** with a clear description of changes

### Commit Messages
We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new zombie detection plugin
fix: resolve missing await in scheduler
docs: update API documentation
test: add ZombieDetector characterization tests
refactor: extract notification service
```

## Architecture Overview

```
app/
├── api/           # FastAPI routes
├── core/          # Config, auth, middleware
├── db/            # SQLAlchemy session management
├── models/        # SQLAlchemy ORM models
└── services/      # Business logic
    ├── llm/       # LLM integration (FinOpsAnalyzer)
    ├── zombies/   # Zombie detection plugins
    ├── carbon/    # GreenOps/carbon calculator
    └── adapters/  # AWS adapter (STS-based)
```

## Security

- Never commit secrets or credentials
- Use `.env.example` as template
- All AWS access uses STS AssumeRole (no long-lived credentials)
- Report security vulnerabilities privately to security@valdrix.ai

## License

By contributing, you agree that your contributions will be licensed under the [BSL 1.1](LICENSE).

## Contributor License Agreement (CLA)

All contributors must accept the repository CLA:

- See [CLA.md](CLA.md)
- Pull request submission constitutes CLA acceptance for that contribution
- The CLA bot may ask you to comment:
  `I have read the CLA Document and I hereby sign the CLA`

## Developer Certificate of Origin (DCO)

We require DCO sign-off for all commits.

- Add sign-off using `git commit -s`
- This appends `Signed-off-by: Your Name <email>` to the commit message
- By signing off, you confirm you have the right to submit the contribution under this repository's license terms

## Trademark and Commercial Use

Please review:

- [TRADEMARK_POLICY.md](TRADEMARK_POLICY.md)
- [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md)
