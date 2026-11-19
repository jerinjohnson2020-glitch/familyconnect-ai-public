"""
FamilyConnect AI - First-Aid Knowledge & Assistance Router (Phase 5E / Day 2)
Provides evidence-based first-aid protocol retrieval grounded in curated public health documents.

Strict System Boundaries:
- READ-ONLY knowledge retrieval: Never creates incidents, never writes to database,
  never dispatches responders, never modifies household or user data.
- Enforces user authentication, input length validation, and in-memory rate limiting.
- Zero PII or query content logging to protect user privacy.
"""

import time
from collections import defaultdict
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..models import User
from ..auth import get_current_user, logger
from ..schemas import (
    FirstAidQueryRequest,
    FirstAidQueryResponse,
    FirstAidTopicItem
)
from ..ai.rag_assistant import get_first_aid_rag_assistant

router = APIRouter(prefix="/api/first-aid", tags=["First-Aid Knowledge Assistant"])

# Lightweight in-memory rate limiting (max 30 requests per minute per user)
# Sliding window timestamp tracker
_user_query_timestamps: Dict[int, List[float]] = defaultdict(list)
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_REQUESTS = 30


def check_rate_limit(user_id: int) -> None:
    """Enforces in-memory rate limit without external dependencies."""
    now = time.time()
    timestamps = _user_query_timestamps[user_id]
    # Prune timestamps older than window
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    _user_query_timestamps[user_id] = [ts for ts in timestamps if ts > cutoff]

    if len(_user_query_timestamps[user_id]) >= RATE_LIMIT_MAX_REQUESTS:
        logger.warning(f"[First-Aid Rate Limit] User ID {user_id} exceeded rate limit ({RATE_LIMIT_MAX_REQUESTS} req/min).")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a moment before sending another first-aid query."
        )

    _user_query_timestamps[user_id].append(now)


@router.post("/query", response_model=FirstAidQueryResponse)
def query_first_aid_assistant(
    payload: FirstAidQueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Query the evidence-based first-aid knowledge assistant.
    Returns matched protocol guidance with verbatim evidence chunks and source citations.
    Falls back safely if evidence is insufficient.
    """
    check_rate_limit(current_user.id)

    raw_query = payload.query.strip()
    if not raw_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty or contain only whitespace."
        )

    rag = get_first_aid_rag_assistant()
    result = rag.query(
        query_text=raw_query,
        conversation_history=payload.conversation_history,
        active_protocol_id=payload.active_protocol_id,
        top_k=payload.top_k or 2
    )

    if result.get("status") == "INVALID_QUERY":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Invalid query provided.")
        )

    return result


@router.get("/topics", response_model=List[FirstAidTopicItem])
def list_first_aid_topics(
    current_user: User = Depends(get_current_user)
):
    """
    List all available curated first-aid topics, categories, and source organizations.
    """
    rag = get_first_aid_rag_assistant()
    return rag.get_topics()


@router.get("/protocols/{protocol_id}")
def get_first_aid_protocol_detail(
    protocol_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the complete, unabridged protocol for a specific first-aid topic by ID.
    """
    rag = get_first_aid_rag_assistant()
    proto = rag.get_protocol(protocol_id.strip().lower())
    if not proto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"First-aid protocol '{protocol_id}' not found."
        )
    return proto
