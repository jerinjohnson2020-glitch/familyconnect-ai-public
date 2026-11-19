"""
FamilyConnect AI - Local LLM Synthesis Client (Stage 3 Integration)
Integrates local Ollama (llama3.2:3b) with the First-Aid RAG assistant.

Strict Architectural & Safety Safeguards:
1. Local Inference Only: Connects exclusively to local Ollama daemon (http://127.0.0.1:11434).
   Never makes remote network calls or uses external/paid APIs.
2. Standard Library Implementation: Uses Python standard library urllib.request; zero additional packages.
3. Strict Grounding: System prompt enforces reading comprehension of retrieved verified guidelines only.
   No hallucinated medications, dosages, procedures, or uncited sources.
4. Bounded Execution: Enforces strict request timeouts (default 8.0s) and token limits.
5. Graceful Degradation: If Ollama is offline, times out, disabled, or returns refusal/error,
   fails safely by returning None for synthesized_explanation, allowing the verified
   verbatim protocol to be returned without disruption.
6. Privacy Preservation: Zero logging of personal user information or patient health narratives.
7. Isolated from Emergency Triage: Completely separate from scikit-learn emergency triage classifier.
"""

import os
import re
import time
import json
import socket
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

try:
    from .safety_validator import validate_first_aid_summary
except (ImportError, ValueError):
    from app.ai.safety_validator import validate_first_aid_summary

logger = logging.getLogger("familyconnect.local_llm")

# Configuration via environment variables with safe, bounded defaults
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_PREDICT_TOKENS = 100
TEMPERATURE = 0.1

# Streamlined system prompt framed as technical reading comprehension of verified guidelines
SYSTEM_PROMPT = (
    "You are the FamilyConnect AI First Aid Assistant. "
    "Summarize the provided emergency clinical guideline into 2 concise sentences for a bystander.\n"
    "RULES: Rely ONLY on the provided text. Clearly state the primary physical first-aid action. "
    "Never invent medications, home remedies, or procedures. Never contradict verified steps or warnings. "
    "Include emergency numbers (112/108). Output ONLY the direct summary without conversational filler or preambles."
)

# Patterns that indicate a non-substantive refusal or ungrounded meta-response
REFUSAL_PATTERNS = [
    re.compile(r"\b(i can'?t provide medical advice|i am unable to provide medical advice)\b", re.IGNORECASE),
    re.compile(r"\b(as an ai language model|as an ai)\b", re.IGNORECASE),
    re.compile(r"\b(consult with a healthcare professional|seek professional medical advice)\b", re.IGNORECASE)
]


def is_local_llm_enabled() -> bool:
    """
    Checks the ENABLE_LOCAL_LLM feature flag.
    Defaults to False so local LLM calls are disabled until explicitly enabled.
    """
    val = os.environ.get("ENABLE_LOCAL_LLM", "false").strip().lower()
    return val in ("true", "1", "yes")


def get_ollama_base_url() -> str:
    """Returns the configured Ollama base URL (local endpoint only)."""
    raw = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    # Guard against accidental remote configuration
    if not (raw.startswith("http://127.0.0.1:") or raw.startswith("http://localhost:")):
        logger.warning(f"[Local LLM Security] Non-local OLLAMA_BASE_URL rejected: '{raw}'. Falling back to {DEFAULT_OLLAMA_BASE_URL}.")
        return DEFAULT_OLLAMA_BASE_URL
    return raw


def get_ollama_model() -> str:
    """Returns the configured Ollama model name."""
    return os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()


def get_ollama_timeout() -> float:
    """Returns the bounded request timeout in seconds."""
    try:
        val = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        # Clamp timeout between 1.0 and 30.0 seconds
        return max(1.0, min(val, 30.0))
    except (ValueError, TypeError):
        return DEFAULT_TIMEOUT_SECONDS


def check_ollama_available(base_url: Optional[str] = None, timeout: float = 1.0) -> bool:
    """
    Lightweight health check against the local Ollama tags endpoint.
    Returns True if local Ollama daemon is reachable and responding.
    """
    target_url = f"{base_url or get_ollama_base_url()}/api/tags"
    try:
        req = urllib.request.Request(target_url, headers={"User-Agent": "FamilyConnect-AI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def build_grounded_prompt(
    protocol: Dict[str, Any],
    evidence_chunks: List[Dict[str, Any]],
    query: str
) -> str:
    """
    Constructs a concise, non-redundant reference passage containing only
    essential verified protocol details, core physical interventions, and contraindications.
    """
    topic = protocol.get("topic", "Emergency Protocol")
    source_meta = protocol.get("source_metadata", {})
    org = source_meta.get("organization", "Verified Health Authority")

    # Primary emergency call guidance (first sentence)
    raw_guidance = protocol.get("emergency_call_guidance", "Dial 112 or 108 immediately.")
    call_directive = raw_guidance.split(".")[0].strip() + "."

    # Core actionable steps (ensuring core physical intervention is included)
    steps = protocol.get("actionable_steps", [])
    if steps:
        if protocol.get("protocol_id") == "cpr_adult_aed":
            # For CPR, prioritize steps detailing chest compressions and AED
            selected_steps = [s for s in steps if any(k in s.lower() for k in ["compressions", "push", "responsiveness", "aed"])][:3]
            core_steps = " ".join(selected_steps if selected_steps else steps[:3])
        else:
            core_steps = " ".join(steps[:3])
    else:
        # Fallback to evidence chunks if steps absent
        core_steps = " ".join(ch.get("evidence_text", "").strip() for ch in evidence_chunks[:2])

    # Core critical warnings (top 2)
    warnings = protocol.get("critical_warnings", [])
    warnings_text = " ".join(warnings[:2]) if warnings else ""

    # Protocol-specific negative contraindications (top 2)
    what_not_to_do = protocol.get("what_not_to_do", [])
    contraindications = " ".join(what_not_to_do[:2]) if what_not_to_do else ""

    prompt_body = (
        f"DOCUMENT: {topic} ({org})\n"
        f"EMERGENCY DIRECTIVE: {call_directive}\n"
        f"ACTIONABLE STEPS: {core_steps[:450]}\n"
    )
    if warnings_text:
        prompt_body += f"CRITICAL WARNINGS: {warnings_text[:200]}\n"
    if contraindications:
        prompt_body += f"PROHIBITED ACTIONS: {contraindications[:200]}\n"

    prompt_body += "TASK: Summarize the emergency instructions for a bystander in 2 sentences based only on this document."
    return prompt_body


def clean_model_output(raw_text: str) -> Optional[str]:
    """
    Cleans model-generated text: removes conversational preambles, validates length,
    and filters non-substantive refusals.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()

    # Strip common markdown wrapper fences if present
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    # Strip introductory conversational prefixes (e.g. "Here is a summary...")
    cleaned = re.sub(
        r"^(here is (a|the) (concise |direct |grounded )?summary[^:\n]*:\s*|\*\*summary:\*\*\s*|summary:\s*)",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # Strip surrounding quotes if wrapped
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    # Reject if output is too short to be a meaningful explanation (< 20 characters)
    if len(cleaned) < 20:
        return None

    # Check for refusal patterns
    for pat in REFUSAL_PATTERNS:
        if pat.search(cleaned):
            logger.info("[Local LLM] Model generated a standard refusal; falling back to verbatim protocol.")
            return None

    return cleaned


def generate_first_aid_explanation(
    query: str,
    protocol: Dict[str, Any],
    evidence_chunks: List[Dict[str, Any]],
    timeout_seconds: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calls local Ollama chat endpoint (/api/chat) to synthesize a grounded explanation
    from retrieved protocol data.

    Returns:
        {
            "explanation": Optional[str],
            "status": str,  # 'SUCCESS', 'DISABLED', 'OFFLINE', 'TIMEOUT', 'MODEL_NOT_FOUND', 'REFUSAL_FILTERED', 'ERROR'
            "model": Optional[str],
            "latency_ms": float
        }
    """
    if not is_local_llm_enabled():
        return {
            "explanation": None,
            "status": "DISABLED",
            "model": None,
            "latency_ms": 0.0
        }

    base_url = get_ollama_base_url()
    model = get_ollama_model()
    timeout = timeout_seconds if timeout_seconds is not None else get_ollama_timeout()

    user_content = build_grounded_prompt(protocol, evidence_chunks, query)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": MAX_PREDICT_TOKENS,
            "top_p": 0.9
        }
    }

    endpoint = f"{base_url}/api/chat"
    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=req_body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FamilyConnect-AI/1.0"
        },
        method="POST"
    )

    start_time = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if resp.status != 200:
                logger.warning(f"[Local LLM] Ollama returned non-200 status: {resp.status}")
                return {
                    "explanation": None,
                    "status": f"HTTP_ERROR_{resp.status}",
                    "model": model,
                    "latency_ms": elapsed_ms
                }

            response_data = json.loads(resp.read().decode("utf-8"))
            raw_content = response_data.get("message", {}).get("content", "")
            explanation = clean_model_output(raw_content)

            if not explanation:
                return {
                    "explanation": None,
                    "status": "REFUSAL_FILTERED" if raw_content else "EMPTY_RESPONSE",
                    "model": model,
                    "latency_ms": elapsed_ms
                }

            # Phase 3 Hardening: Multi-Stage Deterministic Safety Validation Gate
            is_valid, validation_status, validation_reason = validate_first_aid_summary(
                summary=explanation,
                protocol=protocol,
                query=query
            )

            if not is_valid:
                logger.warning(
                    f"[Local LLM Safety Gate] Suppressed summary for '{protocol.get('protocol_id')}'. "
                    f"Status: {validation_status}. Reason: {validation_reason}"
                )
                return {
                    "explanation": None,
                    "status": validation_status,
                    "model": model,
                    "latency_ms": elapsed_ms
                }

            return {
                "explanation": explanation,
                "status": "SUCCESS",
                "model": model,
                "latency_ms": elapsed_ms
            }

    except urllib.error.HTTPError as http_err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if http_err.code == 404:
            logger.warning(f"[Local LLM] Model '{model}' not found in local Ollama daemon (HTTP 404).")
            return {
                "explanation": None,
                "status": "MODEL_NOT_FOUND",
                "model": model,
                "latency_ms": elapsed_ms
            }
        logger.warning(f"[Local LLM] HTTP error from local Ollama: {http_err.code}")
        return {
            "explanation": None,
            "status": f"HTTP_ERROR_{http_err.code}",
            "model": model,
            "latency_ms": elapsed_ms
        }

    except urllib.error.URLError as url_err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        reason = getattr(url_err, "reason", None)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(url_err).lower():
            logger.warning(f"[Local LLM] Request to Ollama timed out after {timeout}s.")
            return {
                "explanation": None,
                "status": "TIMEOUT",
                "model": model,
                "latency_ms": elapsed_ms
            }
        logger.warning(f"[Local LLM] Local Ollama daemon unreachable at {base_url}.")
        return {
            "explanation": None,
            "status": "OFFLINE",
            "model": model,
            "latency_ms": elapsed_ms
        }

    except (socket.timeout, TimeoutError):
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"[Local LLM] Request to Ollama socket timed out after {timeout}s.")
        return {
            "explanation": None,
            "status": "TIMEOUT",
            "model": model,
            "latency_ms": elapsed_ms
        }

    except json.JSONDecodeError:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning("[Local LLM] Failed to parse JSON response from Ollama.")
        return {
            "explanation": None,
            "status": "MALFORMED_RESPONSE",
            "model": model,
            "latency_ms": elapsed_ms
        }

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"[Local LLM] Unexpected exception during local inference: {type(exc).__name__}")
        return {
            "explanation": None,
            "status": "ERROR",
            "model": model,
            "latency_ms": elapsed_ms
        }
