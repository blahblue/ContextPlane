"""Context candidate resolution."""

from contextplane.resolver.domain import (
    CandidateExplanation,
    ContextCandidate,
    ContextResolutionRequest,
    ContextResolutionResult,
    ConflictDecision,
    ConflictStep,
    EffectiveContextResult,
)
from contextplane.resolver.precedence import (ContextPrecedenceConflictError, apply_conflict_precedence)
from contextplane.resolver.service import resolve_context_candidates

__all__ = [
    "CandidateExplanation",
    "ContextCandidate",
    "ContextResolutionRequest",
    "ContextResolutionResult",
    "ConflictDecision",
    "ConflictStep",
    "EffectiveContextResult",
    "ContextPrecedenceConflictError",
    "apply_conflict_precedence",
    "resolve_context_candidates",
]
