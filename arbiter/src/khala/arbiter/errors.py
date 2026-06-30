class SpecledgerError(Exception):
    """Base for all specledger errors."""


class IdCollisionError(SpecledgerError):
    """Raised when an id would be reused."""


class ImmutableArtifactError(SpecledgerError):
    """Raised when mutating an accepted ADR."""


class ArtifactNotFoundError(SpecledgerError):
    """Raised when an id does not resolve to a file."""


class ReviewError(SpecledgerError):
    """Raised when approve() validation fails."""


class CritiqueError(SpecledgerError):
    """Raised when critique cannot run (fail-closed)."""


class GateDeniedError(SpecledgerError):
    """Raised by the hook path when an edit is blocked."""
