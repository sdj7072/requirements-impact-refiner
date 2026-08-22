"""The common client-adapter boundary."""

from typing import Protocol

from ..models import ClientProbe, RunRequest, RunResult


class ClientAdapter(Protocol):
    """A client-specific probe, preparation, and case execution adapter."""

    def probe(self) -> ClientProbe:
        """Describe the safely observable client and installed composition."""

    def prepare(self) -> ClientProbe:
        """Verify evaluation inputs without changing skill behavior."""

    def execute(self, request: RunRequest) -> RunResult:
        """Execute a request or return a structured non-behavior result."""
