# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CI pipeline via GitHub Actions: lint (ruff), type-check (mypy), tests with coverage across Python 3.10 and 3.12
- TypedDict definitions for all tool return shapes (`rcm_agent.tools._types`)
- `py.typed` marker for PEP 561 compliance
- Pre-commit configuration with ruff and mypy hooks
- Makefile with common development commands (`make lint`, `make test`, `make typecheck`, etc.)
- This changelog

### Changed
- Tool functions now return typed dicts instead of `dict[str, Any]`
- Added ruff, mypy, and pre-commit to dev dependencies

## [0.1.0] - 2026-02-24

### Added
- Initial release: Hospital RCM Agent POC
- 4 specialized crews: eligibility verification, prior authorization, coding/charge capture, denial/appeal
- Heuristic encounter router with escalation logic
- SQLite persistence with audit trail
- Protocol-based integration layer with mock and HTTP backends
- RAG infrastructure (mock and ChromaDB via insurance_rag)
- CLI interface: `process`, `status`, `history`, `metrics`, `denial-stats`, `serve-mock`
- FastAPI mock server for eligibility and prior-auth HTTP testing
- 6 synthetic encounter examples
- 20 test modules

[Unreleased]: https://github.com/csmangum/rcm_agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/csmangum/rcm_agent/releases/tag/v0.1.0
