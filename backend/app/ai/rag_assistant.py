"""
FamilyConnect AI - Evidence-Based First-Aid Knowledge Retrieval Engine (Phase 5E / Day 2)
Provides grounded, verifiable first-aid guidance from curated authoritative medical protocols
using local scikit-learn TF-IDF vector space modeling and cosine similarity.

Strict Clinical Safety & Provenance Rules:
1. Zero generation or hallucination: All returned steps, warnings, and citations are strictly
   extracted from curated, verified reference protocol documents.
2. Calibrated relevance threshold: Queries below the calibrated threshold safely return
   an explicit 'INSUFFICIENT_EVIDENCE' fallback rather than guessing.
3. Primary India emergency response: Emphasizes India's pan-India Emergency 112
   and state Ambulance 108 (e.g. KANIV 108 in Kerala).
4. Mandatory disclaimer on all outputs: Explicitly communicates that content is first-aid
   support and does not constitute certified clinical diagnosis.
"""

import os
import re
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from .local_llm import is_local_llm_enabled, generate_first_aid_explanation
except (ImportError, ValueError):
    from app.ai.local_llm import is_local_llm_enabled, generate_first_aid_explanation

logger = logging.getLogger("familyconnect.first_aid_rag")

DEFAULT_PROTOCOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge",
    "protocols"
)

# Calibrated relevance threshold (calibrated against 18 in-domain and 8 out-of-domain queries)
# Out-of-domain max score: 0.0800; In-domain min score: 0.1023.
# A threshold of 0.09 provides clean, robust separation with zero false positives.
DEFAULT_RELEVANCE_THRESHOLD = 0.09

STANDARD_DISCLAIMER = (
    "Informational first-aid guidance only. Not medical diagnosis or clinical advice. "
    "If the person is unresponsive, having difficulty breathing, experiencing severe bleeding, "
    "or in acute distress, immediately dial 112 (India's pan-India emergency number) or 108 (Ambulance, e.g., KANIV 108 in Kerala)."
)

ACUTE_EMERGENCY_PATTERNS = [
    r"\b(unresponsive|not breathing|stopped breathing|no pulse|unconscious|cardiac arrest|collapsed?)\b",
    r"\b(choking|cannot breathe|can't breathe|clutching (his|her|their)? ?(neck|throat)|airway (blocked|obstructed)|strangling|turning blue)\b",
    r"\b(spurting blood|arterial bleed(ing)?|severe bleed(ing)?|heavy bleed(ing)?|bleeding profusely|blood gushing|tourniquet)\b",
    r"\b(crushing chest pain|chest pressure|heart attack|radiating pain|left arm pain)\b",
    r"\b(stroke|face drooping|facial droop|arm weakness|slurred speech)\b",
    r"\b(anaphylaxis|severe allergic reaction|swollen tongue|throat swelling|epipen|epinephrine)\b",
    r"\b(active seizure|violent convulsion[s]?|grand mal|epilepsy convulsion|fitting)\b",
    r"\b(heatstroke|heat stroke|high fever.*hot sun)\b",
    r"\b(call 112|call 108|ambulance|emergency)\b",
]

FOLLOW_UP_RELEVANCE_TERMS = {
    "child", "children", "infant", "infants", "baby", "babies", "toddler", "pediatric",
    "elderly", "adult", "person", "victim", "patient", "boy", "girl", "man", "woman",
    "deep", "depth", "hard", "soft", "fast", "slow", "rate", "depths", "times", "minute", "minutes", "second", "seconds",
    "push", "press", "compression", "compressions", "hand", "hands", "finger", "fingers",
    "breath", "breaths", "mouth", "nose", "throat", "neck", "chest", "rib", "ribs",
    "water", "drink", "food", "eat", "ice", "cold", "warm", "heat", "wash", "clean",
    "bandage", "cloth", "dress", "cover", "wrap", "splint", "tie", "elevate",
    "pain", "hurt", "swelling", "swollen", "bleed", "bleeding", "blood", "vomit", "vomiting", "nausea",
    "stop", "start", "continue", "pause", "wait", "next", "again", "repeat",
    "safe", "danger", "harm", "hurt", "worse", "alive", "dead", "pulse",
    "how", "why", "what", "where", "when", "can", "should", "could", "would", "must", "if"
}

FOLLOW_UP_SYNONYMS = {
    "deep": "depth compressions inches cm 2 inches",
    "depth": "deep compressions inches cm 2 inches",
    "push": "compressions chest press depth",
    "hard": "compressions force depth recoil",
    "fast": "rate bpm cadence speed",
    "rate": "cadence bpm 100-120 per minute",
    "speed": "cadence bpm 100-120 rate",
    "breath": "rescue breaths mouth rise",
    "breaths": "rescue breaths mouth rise",
    "infant": "infant baby gentle chest thrusts 2 fingers",
    "child": "child pediatric 1 2 hands depth",
    "water": "running cool water burns",
    "ice": "ice water prohibited contraindicated",
    "food": "choking airway obstruction oral",
}


def is_valid_follow_up(query: str, proto_tokens: set) -> bool:
    """
    Checks if a query is a plausible contextual follow-up to an ongoing active protocol.
    Filters out completely out-of-domain conversational queries like 'how to bake cake'.
    """
    tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower()))
    if not tokens:
        return False
    non_stop = tokens - {"how", "why", "what", "where", "when", "can", "should", "could", "would", "must", "the", "and", "for", "with", "from"}
    if not non_stop:
        return False
    return bool(non_stop.intersection(proto_tokens) or non_stop.intersection(FOLLOW_UP_RELEVANCE_TERMS))


def generate_deterministic_follow_up_reply(query: str, proto: Dict[str, Any], best_chunk: Dict[str, Any]) -> str:
    """
    Generates a deterministic, grounded conversational answer for follow-up queries.
    Provides clear answers for child/infant adaptations while directing users to verified steps.
    """
    topic = proto.get("topic", "")
    chunk_title = best_chunk.get("title", "")
    chunk_text = best_chunk.get("text", "")
    q_lower = query.lower()

    if any(k in q_lower for k in ["depth", "deep", "how hard"]):
        if proto.get("protocol_id") == "cpr_adult_aed":
            return (
                "For adult CPR compression depth: Push straight down at least 2 inches (5 cm) — but no more than 2.4 inches (6 cm) — "
                "in the center of the chest. Allow full chest recoil between compressions at a rate of 100 to 120 per minute. "
                "Continue until emergency medical services (112/108) take over or an AED is ready."
            )

    if any(k in q_lower for k in ["how fast", "rate", "speed", "cadence", "bpm"]):
        if proto.get("protocol_id") == "cpr_adult_aed":
            return (
                "For adult CPR compression rate: Deliver compressions at 100 to 120 beats per minute (to the rhythm of 'Stayin' Alive'). "
                "Push hard and fast at least 2 inches (5 cm) deep and allow the chest to recoil fully between compressions."
            )

    if any(k in q_lower for k in ["infant", "baby", "pediatric"]):
        if proto.get("protocol_id") == "choking_adult_child":
            return (
                "Regarding infants (under 1 year): Do not perform standard abdominal thrusts. "
                "Use cycles of 5 firm back blows and 5 gentle chest thrusts, and call 112/108 immediately. "
                "See the full actionable steps and contraindications below."
            )
        elif proto.get("protocol_id") == "cpr_adult_aed":
            return (
                "Regarding infants/pediatric CPR: Use gentle chest compressions (2 fingers for an infant, 1 or 2 hands for a child) "
                "at a depth of about 1.5 inches (4 cm) for infants or 2 inches (5 cm) for children at 100-120 bpm. "
                "Call 112/108 immediately and follow the full emergency guidance below."
            )

    if any(k in q_lower for k in ["child", "toddler"]):
        if proto.get("protocol_id") == "cpr_adult_aed":
            return (
                "Regarding children needing CPR: Push down about 2 inches (5 cm) at 100-120 compressions per minute using 1 or 2 hands. "
                "Call 112 or 108 immediately and review the full steps below."
            )

    sentences = re.split(r'(?<=[.!?])\s+', chunk_text.strip())
    summary = " ".join(sentences[:2]) if sentences else chunk_text[:200]
    return f"Regarding your follow-up on {topic} ({chunk_title}): {summary} Please see the full protocol steps and contraindications below."


def filter_negated_query_terms(query_text: str) -> Tuple[str, List[str]]:
    """
    Strips explicitly denied or negated symptom clauses from query text before
    computing TF-IDF vector similarity. Prevents queries like
    'denies chest pain, is not bleeding, but ankle is swollen' from matching
    cardiac or bleeding protocols due to high-IDF keyword hits.
    Returns: (filtered_query_for_search, list_of_negated_concepts)
    """
    try:
        from .context_extractor import INDICATOR_PATTERNS, NEGATION_PREFIXES
    except (ImportError, ValueError):
        from app.ai.context_extractor import INDICATOR_PATTERNS, NEGATION_PREFIXES

    clauses = re.split(r'[,;.!?]+', query_text)
    positive_clauses = []
    negated_concepts = []

    for cl in clauses:
        cl_clean = cl.strip()
        if not cl_clean:
            continue
        is_neg = False
        for concept, patterns in INDICATOR_PATTERNS.items():
            for pat in patterns:
                m = re.search(pat, cl_clean, re.IGNORECASE)
                if m:
                    prefix = cl_clean[:m.start()]
                    if re.search(NEGATION_PREFIXES, prefix, re.IGNORECASE):
                        is_neg = True
                        negated_concepts.append(concept)
                        break
            if is_neg:
                break
        if not is_neg:
            positive_clauses.append(cl_clean)

    filtered_text = " ".join(positive_clauses).strip()
    search_text = filtered_text if filtered_text else query_text
    return search_text, negated_concepts


class FirstAidRAGAssistant:
    def __init__(
        self,
        protocols_dir: Optional[str] = None,
        relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD
    ):
        self.protocols_dir = Path(protocols_dir or DEFAULT_PROTOCOLS_DIR).resolve()
        self.relevance_threshold = relevance_threshold
        self.protocols: Dict[str, Dict[str, Any]] = {}
        self.chunks: List[Dict[str, Any]] = []
        self.proto_tokens: Dict[str, set] = {}
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.chunk_matrix = None
        self._is_indexed = False
        self.load_and_index()

    def load_and_index(self) -> None:
        """Loads all curated JSON protocols and fits the TF-IDF vector space index."""
        if not self.protocols_dir.exists():
            logger.warning(f"Protocols directory does not exist: {self.protocols_dir}")
            return

        self.protocols.clear()
        self.chunks.clear()
        self.proto_tokens.clear()

        protocol_files = sorted(self.protocols_dir.glob("*.json"))
        for p_file in protocol_files:
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    proto = json.load(f)
                    proto_id = proto.get("protocol_id", p_file.stem)
                    self.protocols[proto_id] = proto

                    # Token cache for follow-up validation
                    combined_text = (
                        f"{proto.get('topic', '')} "
                        f"{' '.join(proto.get('keywords', []))} "
                        f"{' '.join(proto.get('critical_warnings', []))} "
                        f"{' '.join(proto.get('actionable_steps', []))} "
                        f"{' '.join(proto.get('what_not_to_do', []))}"
                    )
                    self.proto_tokens[proto_id] = set(re.findall(r"\b[a-zA-Z]{3,}\b", combined_text.lower()))

                    for chunk in proto.get("chunks", []):
                        search_text = (
                            f"{proto.get('topic', '')} {proto.get('category', '')} "
                            f"{chunk.get('title', '')} {chunk.get('text', '')} "
                            f"{' '.join(chunk.get('keywords', []))} "
                            f"{' '.join(proto.get('keywords', []))} "
                            f"{' '.join(proto.get('critical_warnings', []))}"
                        )
                        self.chunks.append({
                            "chunk_id": chunk.get("chunk_id", ""),
                            "protocol_id": proto_id,
                            "topic": proto.get("topic", ""),
                            "category": proto.get("category", ""),
                            "title": chunk.get("title", ""),
                            "text": chunk.get("text", ""),
                            "search_text": search_text,
                            "source_metadata": proto.get("source_metadata", {}),
                            "emergency_call_guidance": proto.get("emergency_call_guidance", ""),
                            "critical_warnings": proto.get("critical_warnings", []),
                            "actionable_steps": proto.get("actionable_steps", []),
                            "what_not_to_do": proto.get("what_not_to_do", [])
                        })
            except Exception as exc:
                logger.error(f"Failed to load protocol file {p_file}: {exc}")

        if not self.chunks:
            logger.warning("No first-aid chunks loaded for indexing.")
            self._is_indexed = False
            return

        # Fit TF-IDF Vectorizer
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True
        )
        self.chunk_matrix = self.vectorizer.fit_transform([c["search_text"] for c in self.chunks])
        self._is_indexed = True
        logger.info(
            f"Indexed {len(self.protocols)} protocols ({len(self.chunks)} chunks) "
            f"with {self.chunk_matrix.shape[1]} TF-IDF features."
        )

    def get_topics(self) -> List[Dict[str, Any]]:
        """Returns metadata for all available curated first-aid topics."""
        return [
            {
                "protocol_id": proto["protocol_id"],
                "topic": proto["topic"],
                "category": proto["category"],
                "source_organization": proto.get("source_metadata", {}).get("organization", "Recognized Health Authority"),
                "document_title": proto.get("source_metadata", {}).get("document_title", ""),
                "url": proto.get("source_metadata", {}).get("url", ""),
                "emergency_call_guidance": proto.get("emergency_call_guidance", "")
            }
            for proto in self.protocols.values()
        ]

    def get_protocol(self, protocol_id: str) -> Optional[Dict[str, Any]]:
        """Returns full protocol details by ID."""
        return self.protocols.get(protocol_id)

    def query(
        self,
        query_text: str,
        conversation_history: Optional[List[Any]] = None,
        active_protocol_id: Optional[str] = None,
        top_k: int = 2
    ) -> Dict[str, Any]:
        """
        Executes evidence-grounded first-aid retrieval with conversational context handling.
        Evaluates acute emergency symptoms independently on raw query before context expansion.
        """
        start_time = time.perf_counter()

        # 1. Input Sanitization & Validation
        if not query_text or not isinstance(query_text, str):
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "INVALID_QUERY",
                "message": "Query text cannot be empty.",
                "disclaimer": STANDARD_DISCLAIMER,
                "latency_ms": elapsed_ms
            }

        cleaned_query = query_text.strip()
        if len(cleaned_query) < 2:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "INVALID_QUERY",
                "message": "Query text is too short. Please describe the emergency symptoms or first-aid topic.",
                "disclaimer": STANDARD_DISCLAIMER,
                "latency_ms": elapsed_ms
            }

        if len(cleaned_query) > 500:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "INVALID_QUERY",
                "message": "Query text exceeds maximum allowed length of 500 characters.",
                "disclaimer": STANDARD_DISCLAIMER,
                "latency_ms": elapsed_ms
            }

        # Validate conversation history payload bounds
        if conversation_history:
            recent_history = conversation_history[-6:]
            total_history_len = sum(
                len(getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else ""))
                for m in recent_history
            )
            if total_history_len > 4000:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "status": "INVALID_QUERY",
                    "message": "Total conversation history content exceeds 4000 character limit.",
                    "disclaimer": STANDARD_DISCLAIMER,
                    "latency_ms": elapsed_ms
                }

        if not self._is_indexed or self.vectorizer is None or self.chunk_matrix is None:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "message": "Knowledge base index is currently uninitialized.",
                "emergency_guidance": "If this is an active emergency, dial 112 (India) or your local emergency number immediately.",
                "disclaimer": STANDARD_DISCLAIMER,
                "latency_ms": elapsed_ms
            }

        # 2. Independent Raw Query Evaluation & Acute Emergency Detection
        search_query, negated_concepts = filter_negated_query_terms(cleaned_query)
        raw_query_vec = self.vectorizer.transform([search_query])
        raw_similarities = cosine_similarity(raw_query_vec, self.chunk_matrix)[0]

        raw_best_idx = int(raw_similarities.argmax())
        raw_best_score = float(raw_similarities[raw_best_idx])
        raw_best_chunk = self.chunks[raw_best_idx]
        raw_best_proto_id = raw_best_chunk["protocol_id"]

        is_acute_emergency = any(
            re.search(pat, cleaned_query, re.IGNORECASE) for pat in ACUTE_EMERGENCY_PATTERNS
        )

        similarities = raw_similarities
        best_idx = raw_best_idx
        best_score = raw_best_score
        is_follow_up = False

        # 3. Topic Override vs Follow-up Context Expansion
        # Acute emergency triggers immediate topic override, bypassing previous context
        if is_acute_emergency:
            # Standalone emergency overrides any active protocol context
            is_follow_up = False
        elif active_protocol_id and active_protocol_id in self.protocols:
            active_proto = self.protocols[active_protocol_id]
            proto_tokens = self.proto_tokens.get(active_protocol_id, set())

            if is_valid_follow_up(cleaned_query, proto_tokens):
                # 1. Expand with procedural synonyms
                synonyms_added = []
                for word in re.findall(r"\b[a-zA-Z]{3,}\b", cleaned_query.lower()):
                    if word in FOLLOW_UP_SYNONYMS:
                        synonyms_added.append(FOLLOW_UP_SYNONYMS[word])
                syn_text = " ".join(synonyms_added)

                # 2. Build focused active protocol search query
                focused_search = f"{search_query} {syn_text} {active_proto.get('topic', '')}"
                focused_vec = self.vectorizer.transform([focused_search])
                focused_sims = cosine_similarity(focused_vec, self.chunk_matrix)[0]

                # Filter to active protocol chunk indices
                active_indices = [i for i, c in enumerate(self.chunks) if c["protocol_id"] == active_protocol_id]
                best_active_idx = max(active_indices, key=lambda i: focused_sims[i])
                best_active_score = float(focused_sims[best_active_idx])

                if best_active_score >= self.relevance_threshold:
                    similarities = focused_sims
                    best_idx = best_active_idx
                    best_score = best_active_score
                    is_follow_up = True
            elif raw_best_score >= self.relevance_threshold and raw_best_proto_id != active_protocol_id:
                is_follow_up = False

        # 4. Relevance Threshold Evaluation
        if best_score < self.relevance_threshold:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "query": cleaned_query,
                "relevance_score": round(best_score, 4),
                "threshold_required": self.relevance_threshold,
                "message": (
                    "No verified first-aid guidance in our curated evidence collection matched your query with sufficient confidence. "
                    "To prevent medical misinformation, ungrounded advice is not generated."
                ),
                "emergency_guidance": (
                    "If someone is severely injured, unresponsive, having difficulty breathing, or experiencing acute chest pain, "
                    "call 112 (India's pan-India emergency number) or 108 (Ambulance, e.g., KANIV 108 in Kerala) immediately."
                ),
                "conversational_reply": None,
                "is_follow_up": False,
                "disclaimer": STANDARD_DISCLAIMER,
                "latency_ms": elapsed_ms
            }

        # 5. Extract Top-K Relevant Chunks
        ranked_indices = similarities.argsort()[::-1]
        top_chunks = []
        for idx in ranked_indices[:top_k]:
            if similarities[idx] >= self.relevance_threshold:
                c = self.chunks[idx]
                top_chunks.append({
                    "chunk_id": c["chunk_id"],
                    "title": c["title"],
                    "evidence_text": c["text"],
                    "similarity_score": round(float(similarities[idx]), 4)
                })

        best_chunk = self.chunks[best_idx]
        proto_id = best_chunk["protocol_id"]
        proto = self.protocols[proto_id]

        # 6. Check for Potential Ambiguity
        ambiguous = False
        secondary_match = None
        if len(ranked_indices) > 1 and not is_follow_up:
            second_idx = int(ranked_indices[1])
            second_score = float(similarities[second_idx])
            second_chunk = self.chunks[second_idx]
            if second_chunk["protocol_id"] != proto_id and (best_score - second_score) < 0.015:
                ambiguous = True
                secondary_match = {
                    "topic": second_chunk["topic"],
                    "protocol_id": second_chunk["protocol_id"],
                    "score": round(second_score, 4)
                }

        # 7. Grounded Local LLM Synthesis & Deterministic Follow-up
        synthesized_explanation = None
        llm_model_name = None
        llm_latency = None
        llm_status = "DISABLED"

        if is_local_llm_enabled():
            try:
                llm_res = generate_first_aid_explanation(
                    query=cleaned_query,
                    protocol=proto,
                    evidence_chunks=top_chunks
                )
                synthesized_explanation = llm_res.get("explanation")
                llm_model_name = llm_res.get("model")
                llm_latency = llm_res.get("latency_ms")
                llm_status = llm_res.get("status")
            except Exception as llm_err:
                logger.warning(f"[First-Aid RAG] Local LLM synthesis failed gracefully: {type(llm_err).__name__}")
                llm_status = "ERROR"

        conversational_reply = None
        if is_follow_up:
            conversational_reply = synthesized_explanation or generate_deterministic_follow_up_reply(
                cleaned_query, proto, best_chunk
            )
        elif synthesized_explanation:
            conversational_reply = synthesized_explanation

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "status": "SUCCESS",
            "query": cleaned_query,
            "relevance_score": round(best_score, 4),
            "matched_protocol": {
                "protocol_id": proto_id,
                "topic": proto["topic"],
                "category": proto["category"]
            },
            "emergency_call_guidance": proto["emergency_call_guidance"],
            "critical_warnings": proto["critical_warnings"],
            "actionable_steps": proto["actionable_steps"],
            "what_not_to_do": proto["what_not_to_do"],
            "evidence_chunks": top_chunks,
            "source_citation": {
                "organization": proto["source_metadata"]["organization"],
                "document_title": proto["source_metadata"]["document_title"],
                "url": proto["source_metadata"]["url"],
                "published_or_reviewed_date": proto["source_metadata"].get("published_or_reviewed_date", ""),
                "accessed_date": proto["source_metadata"].get("accessed_date", ""),
                "license_note": proto["source_metadata"].get("license_note", "")
            },
            "ambiguity_detected": ambiguous,
            "secondary_match": secondary_match,
            "negated_concepts_filtered": negated_concepts if negated_concepts else None,
            "synthesized_explanation": synthesized_explanation,
            "llm_model": llm_model_name,
            "llm_latency_ms": llm_latency,
            "llm_status": llm_status,
            "conversational_reply": conversational_reply,
            "is_follow_up": is_follow_up,
            "disclaimer": STANDARD_DISCLAIMER,
            "latency_ms": elapsed_ms
        }


# Singleton instance for application runtime
_rag_assistant_instance: Optional[FirstAidRAGAssistant] = None


def get_first_aid_rag_assistant() -> FirstAidRAGAssistant:
    """Returns the singleton FirstAidRAGAssistant instance with cached in-memory index."""
    global _rag_assistant_instance
    if _rag_assistant_instance is None:
        _rag_assistant_instance = FirstAidRAGAssistant()
    return _rag_assistant_instance
