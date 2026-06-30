class ArbiterError(Exception):
    """Base for all Arbiter errors."""


class IdCollisionError(ArbiterError):
    """Raised when an id would be reused."""


class ImmutableArtifactError(ArbiterError):
    """Raised when mutating an accepted ADR."""


class ArtifactNotFoundError(ArbiterError):
    """Raised when an id does not resolve to a file."""


class ReviewError(ArbiterError):
    """Raised when approve() validation fails."""


class CritiqueError(ArbiterError):
    """Raised when critique cannot run (fail-closed)."""


class GateDeniedError(ArbiterError):
    """Raised by the hook path when an edit is blocked."""
