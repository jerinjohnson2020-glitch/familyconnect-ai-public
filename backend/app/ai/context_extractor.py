"""
FamilyConnect AI - Context Extraction Engine (Phase 4C)
Converts unstructured emergency free-text descriptions into validated,
structured clinical indicators using transparent keyword patterns and negation analysis.
"""

import re
from typing import Dict, Any, List, Optional, Tuple

# Controlled clinical indicator patterns
# Each concept has a list of positive trigger patterns and negation detection
INDICATOR_PATTERNS = {
    "chest_pain": [
        r"\b(?:chest\s+(?:pain|tight|pressure|discomfort|ache|hurts?)|cardiac|heart\s+attack|angina)\b"
    ],
    "breathing_difficulty": [
        r"\b(?:difficult(?:y)?\s+(?:in\s+)?breath(?:ing)?|breath(?:ing)?\s+(?:diff|trouble|short|hard)|shortness\s+of\s+breath|breathless|suffocat|gasping|wheez|asthma|can'?t\s+breathe|cannot\s+breathe|dyspnea)\b"
    ],
    "unconscious": [
        r"\b(?:unconscious|unconcious|unresponsive|passed\s+out|fainted|blacked\s+out|collapsed|not\s+waking\s+up|comatose|incoherent|lost\s+consciousness)\b"
    ],
    "severe_bleeding": [
        r"\b(?:bleed(?:ing)?|hemorrhag|blood\s+(?:everywhere|loss|pool|from|gushing|spurting)|stab|deep\s+cut|arterial\s+bleed)\b"
    ],
    "fall_or_trauma": [
        r"\b(?:fell|fallen|fall(?:ing)?|fell\s+over|fell\s+down|stairs|slipped|tripped|struck|hit\s+by|accident|crash|collision|trauma|impact)\b"
    ],
    "dizziness": [
        r"\b(?:dizzy|dizziness|lightheaded|vertigo|unsteady|loss\s+of\s+balance|faint)\b"
    ],
    "alone": [
        r"\b(?:alone|by\s+(?:my|him|her)self|no\s+one\s+(?:here|around|with)|isolated|living\s+alone|solo|nobody\s+around)\b"
    ],
    "minor_injury": [
        r"\b(?:minor|scrape|scratch|bruise|small\s+cut|sprain|twisted\s+ankle|mild\s+pain|superficial)\b"
    ]
}


# Negation window regex: matches negative prefixes preceding symptoms
# e.g., "no chest pain", "not bleeding", "denies shortness of breath", "without dizziness"
NEGATION_PREFIXES = r"\b(?:no|not|denies|denied|without|negative\s+for|rules?\s+out|never|zero)\b"


def extract_context_from_text(description: Optional[str]) -> Dict[str, Any]:
    """
    Parses emergency description text safely, extracting positive indicators,
    negated indicators, and evidence snippets.
    Returns:
    {
        "extracted_features": Dict[str, float], # 1.0 or 0.0 for model DictVectorizer
        "extracted_concepts": List[str],        # Human-readable labels
        "negated_concepts": List[str],          # Symptoms explicitly denied
        "evidence_snippets": Dict[str, str],    # Extracted text matches
        "has_conflicts": bool,
        "conflicts": List[str]
    }
    """
    if not description or not isinstance(description, str) or not description.strip():
        return {
            "extracted_features": {
                f"text_{k}": 0.0 for k in INDICATOR_PATTERNS
            },
            "extracted_concepts": [],
            "negated_concepts": [],
            "evidence_snippets": {},
            "has_conflicts": False,
            "conflicts": []
        }

    clean_text = description.strip().lower()
    # Normalize punctuation and whitespace while preserving clause boundaries
    # Split text into sentence/clause segments to avoid over-extended negation scopes
    clauses = re.split(r"[.;,!?]+", clean_text)

    positive_indicators = set()
    negated_indicators = set()
    snippets = {}

    for concept, patterns in INDICATOR_PATTERNS.items():
        concept_found = False
        concept_negated = False

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            for pattern in patterns:
                match = re.search(pattern, clause)
                if match:
                    matched_phrase = match.group(0)
                    start_pos = match.start()
                    # Check text immediately before match within clause for negation words (up to 4 words before)
                    prefix_window = clause[max(0, start_pos - 35):start_pos]

                    if re.search(NEGATION_PREFIXES, prefix_window):
                        concept_negated = True
                        snippets[f"negated_{concept}"] = f"clause: '{clause}'"
                    else:
                        concept_found = True
                        snippets[concept] = matched_phrase

        # Conflict resolution within text itself:
        # If explicitly found and explicitly negated across different clauses, record as ambiguous
        if concept_found and not concept_negated:
            positive_indicators.add(concept)
        elif concept_negated and not concept_found:
            negated_indicators.add(concept)
        elif concept_found and concept_negated:
            # Ambiguous/conflicting text: default to positive for emergency safety, but flag conflict
            positive_indicators.add(concept)
            snippets[f"ambiguous_{concept}"] = "Both asserted and negated in description"

    # Build feature dictionary formatted for ML model
    extracted_features = {}
    for k in INDICATOR_PATTERNS:
        extracted_features[f"text_{k}"] = 1.0 if k in positive_indicators else 0.0

    return {
        "extracted_features": extracted_features,
        "extracted_concepts": sorted(list(positive_indicators)),
        "negated_concepts": sorted(list(negated_indicators)),
        "evidence_snippets": snippets,
        "has_conflicts": any("ambiguous_" in k for k in snippets),
        "conflicts": [k.replace("ambiguous_", "") for k in snippets if "ambiguous_" in k]
    }


def compare_structured_and_text(
    structured_flags: Dict[str, Any],
    extracted_result: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Detects discrepancies between structured checkboxes and free-text statements.
    e.g., Structured: conscious=True, but Text says: "unconscious"
    or Structured: bleeding=False, but Text says: "heavy bleeding"
    """
    conflicts = []
    text_concepts = extracted_result.get("extracted_concepts", [])
    negated_concepts = extracted_result.get("negated_concepts", [])

    # Consciousness check
    is_conscious = structured_flags.get("is_conscious")
    if is_conscious is True and "unconscious" in text_concepts:
        conflicts.append("Structured flag indicates CONSCIOUS, but description mentions UNCONSCIOUS/UNRESPONSIVE.")
    elif is_conscious is False and "unconscious" in negated_concepts:
        conflicts.append("Structured flag indicates UNCONSCIOUS, but description states NOT UNCONSCIOUS.")

    # Bleeding check
    is_bleeding = structured_flags.get("is_bleeding_severely")
    if is_bleeding is False and "severe_bleeding" in text_concepts:
        conflicts.append("Structured flag indicates NO SEVERE BLEEDING, but description mentions SEVERE/HEAVY BLEEDING.")
    elif is_bleeding is True and "severe_bleeding" in negated_concepts:
        conflicts.append("Structured flag indicates SEVERE BLEEDING, but description states NO BLEEDING.")

    # Breathing check
    has_breathing_diff = structured_flags.get("has_breathing_difficulty")
    if has_breathing_diff is False and "breathing_difficulty" in text_concepts:
        conflicts.append("Structured flag indicates NORMAL BREATHING, but description mentions BREATHING DIFFICULTY.")
    elif has_breathing_diff is True and "breathing_difficulty" in negated_concepts:
        conflicts.append("Structured flag indicates BREATHING DIFFICULTY, but description states NO BREATHING DIFFICULTY.")

    return len(conflicts) > 0, conflicts
