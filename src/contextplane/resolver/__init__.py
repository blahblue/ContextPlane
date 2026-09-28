"""Context candidate resolution."""

from contextplane.resolver.domain import (
    CandidateExplanation,
    ContextCandidate,
    ContextResolutionRequest,
    ContextResolutionResult,
)
from contextplane.resolver.service import resolve_context_candidates

__all__ = [
    "CandidateExplanation",
    "ContextCandidate",
    "ContextResolutionRequest",
    "ContextResolutionResult",
    "resolve_context_candidates",
]
