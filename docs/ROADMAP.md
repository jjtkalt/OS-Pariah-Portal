# OS-Pariah roadmap (naming & merge context)

## Today

This repository delivers the **OS-Pariah** web application: CMS, helpdesk, calendar,
region tooling, and grid-admin RBAC for OpenSimulator. It is packaged for openSUSE
as RPM `os-pariah`, unit `os-pariah.service`, paths under `/opt/os-pariah` and
`/etc/os-pariah`. See [NAMING.md](NAMING.md).

A sibling effort, **OS-Pariah Installation**, installs and initially configures a
hypergridded OpenSimulator stack on openSUSE. Operators today run Installation first
(or bring their own Robust/region hosts), then deploy this web component against the
grid databases and services.

## Near term

- Keep Platform Standards alignment (CI, Ruff, migrations, Cloudflare Full strict,
  packaged timers on the master unit).
- Treat this tree as the reference implementation for CVG-style Flask apps on Leap.
- Prefer documentation and packaging that already assume the eventual product name
  **OS-Pariah**, not a separate “Portal” product.

## Long term

The intended end state is a **merged OS-Pariah system**:

1. An install wizard decides which steps are needed (base openSUSE hardening, OpenSim
   Robust/regions, this web UI, Cloudflare/nginx, backups).
2. A single branded experience for grids starting from scratch that want an
   enterprise-oriented, mostly self-caring installation with modest admin skill.
3. Shared `os-pariah` slug, user, and config directory across installer and web app
   so operators never learn two naming schemes.

Until that merge lands, keep Installation and this web component in separate repos,
but do not invent divergent slugs or “portal-only” path conventions.
