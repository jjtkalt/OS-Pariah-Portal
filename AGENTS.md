# OS-Pariah-Portal — Agent Index

This app follows **Platform Standards**. Canonical source (GitHub, not a local path):

**https://github.com/jjtkalt/PlatformStandards**

When aligning platform conventions, treat that repository as source of truth. Prefer fetching or opening these paths from GitHub:

1. [docs/STANDARDS.md](https://github.com/jjtkalt/PlatformStandards/blob/main/docs/STANDARDS.md) — mandatory checklist
2. [ARCHITECTURE-DECISIONS.md](https://github.com/jjtkalt/PlatformStandards/blob/main/ARCHITECTURE-DECISIONS.md) — rationale
3. [docs/CI.md](https://github.com/jjtkalt/PlatformStandards/blob/main/docs/CI.md) — GitHub Actions workflows
4. [docs/LINTING.md](https://github.com/jjtkalt/PlatformStandards/blob/main/docs/LINTING.md) — Ruff lint/format
5. [templates/](https://github.com/jjtkalt/PlatformStandards/tree/main/templates) — copy-paste starters

Short agent index in that repo: [AGENTS.md](https://github.com/jjtkalt/PlatformStandards/blob/main/AGENTS.md).

## Non-negotiables (summary)

| Area | Rule |
|------|------|
| Install root | `/opt/<app>/` (this app: `/opt/os_pariah/`) |
| Config | `/etc/<app>/<app>.conf` + `/etc/<app>/secrets` + project `.env` for dev |
| Migrations | `migrations/*.sql` + `scripts/migrate.py` + `ensure_secret_key()` + `ensure_bootstrap_admin()` |
| Pre-start | `sync_requirements.py`, `check_mariadb.py`, `migrate.py` |
| WSGI | `wsgi:app` on unix socket `/run/<app>/<app>.sock` |
| CSS | `app/static/css/base.css` with shared tokens |
| User manual | Tabbed `manual.html` at `/manual.html` |
| Dev docs | `README`, `CHANGELOG`, `SECURITY`, `docs/DEPLOYMENT.md` |
| Tests | Integration-first; mock email/SMTP only |
| Lint/format | **Ruff** (lint + format), config in `pyproject.toml`; pre-commit + CI `lint` job |
| CI | **Required** `.github/workflows/ci-tests.yml` (`lint` + `test` jobs); optional `release-rpm.yml` |
| TLS | HTTPS on origin; Cloudflare Full (strict); `<app>-cloudflare-ip.conf` + daily updater timer pulled in by master unit |
| Package | RPM spec for openSUSE when deploying to CVG infrastructure |
| Packaged timers | List on master `<app>.service` `Before=` / `Requires=`; do not separately enable each timer |

## Explicit exclusions

- Do **not** change business logic during platform-only tasks.
- Do **not** use Flask-Migrate in production startup paths.
- Do **not** terminate TLS only at Cloudflare with HTTP origin.

## Portal-specific

OS-Pariah-Portal is a **reference implementation** for Platform Standards (dev doc depth, CI, release RPM). Do not change those platform patterns without an explicit request. Prefer matching existing layout under `packaging/`, `scripts/`, `.github/workflows/`, and `docs/` over inventing new conventions.
