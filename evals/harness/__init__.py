"""Contracts for installed-plugin evaluation runs."""

from .catalog import CatalogError, load_all, load_catalog, select_suite
from .models import (
    Adjudication,
    CaseSpec,
    CaseTurn,
    ClientProbe,
    CommandResult,
    MechanicalScore,
    RunRequest,
    RunResult,
    RunStatus,
)

__all__ = (
    "Adjudication",
    "CaseSpec",
    "CaseTurn",
    "CatalogError",
    "ClientProbe",
    "CommandResult",
    "MechanicalScore",
    "RunRequest",
    "RunResult",
    "RunStatus",
    "load_all",
    "load_catalog",
    "select_suite",
)
