# Contributing

Thanks for considering a contribution.

## Setup

1. Install Python 3.12+ and `uv`.
2. Run `uv sync`.
3. Copy `.env.example` to `.env`.
4. Start PostgreSQL with `docker compose up -d db`.
5. Run `uv run alembic upgrade head`.

## Before opening a pull request

Run:

```bash
make contracts
make verify
```

Add or update tests for behavior changes. If a public contract changes, regenerate the
checked-in contract and explain compatibility in the pull request.

Keep commits focused and avoid including real production logs, credentials, personal data,
or model prompts copied from private systems.
