"""Grid providers: how a grid comes to exist, as far as the setup wizard is concerned.

Slice A ships exactly one provider, ``external``: the grid (OpenSim/Robust) already
exists, OS-Pariah only *reads* it. The wizard core never installs or reconfigures
OpenSim. A future provider (for example OS-Pariah Installation) may declare mutating
capabilities and contribute extra steps through the same registry; nothing else is
allowed to touch OpenSim.
"""

from __future__ import annotations

from enum import StrEnum

DEFAULT_PROVIDER_ID = "external"


class Capability(StrEnum):
    # Read-only access to an existing grid. Safe for every provider.
    READ_GRID = "read_grid"
    # Mutating capabilities: only providers that own the grid install may declare these.
    PROVISION_GRID_DB = "provision_grid_db"
    INSTALL_OPENSIM = "install_opensim"
    WRITE_OPENSIM_CONFIG = "write_opensim_config"
    CONTROL_OPENSIM_SERVICES = "control_opensim_services"


MUTATING_CAPABILITIES = frozenset(
    {
        Capability.PROVISION_GRID_DB,
        Capability.INSTALL_OPENSIM,
        Capability.WRITE_OPENSIM_CONFIG,
        Capability.CONTROL_OPENSIM_SERVICES,
    }
)


class GridProvider:
    """Base class: an id, a title, declared capabilities, and the steps that apply."""

    id: str = ""
    title: str = ""
    capabilities: frozenset[Capability] = frozenset()

    @property
    def mutating(self) -> bool:
        return bool(self.capabilities & MUTATING_CAPABILITIES)

    def steps(self):
        """Wizard steps that apply to this provider, in display order."""
        from app.setup.steps import STEPS

        return [s for s in STEPS if s.applies_to(self.id)]


class ExternalGridProvider(GridProvider):
    """An already-running grid. Read-only: no mutating capability, ever."""

    id = DEFAULT_PROVIDER_ID
    title = "Existing grid (read-only)"
    capabilities = frozenset({Capability.READ_GRID})


_PROVIDERS: dict[str, GridProvider] = {}


def register_provider(provider: GridProvider) -> GridProvider:
    if not provider.id:
        raise ValueError("A grid provider needs an id.")
    _PROVIDERS[provider.id] = provider
    return provider


def get_provider(provider_id: str | None = None) -> GridProvider:
    """Return the registered provider; unknown ids fall back to the read-only default."""
    wanted = (provider_id or DEFAULT_PROVIDER_ID).strip()
    return _PROVIDERS.get(wanted) or _PROVIDERS[DEFAULT_PROVIDER_ID]


def provider_ids() -> list[str]:
    return sorted(_PROVIDERS)


register_provider(ExternalGridProvider())
