"""
FamilyConnect AI - Deterministic First-Aid Safety Validator (Phase 3 Hardening)
Treats curated first-aid protocol JSON documents as the authoritative ground truth.

CLINICAL & REGULATORY NOTICE:
This validator is a limited, deterministic rule-based safeguard designed to intercept
blatant contradictions, clinical omissions, and dangerous instructions in LLM outputs.
It DOES NOT constitute a clinical guarantee of medical safety or complete semantic comprehension.
Whenever a summary cannot be validated with deterministic certainty, the system strictly
FAILS CLOSED: the generated summary is suppressed (synthesized_explanation = None) and
the application falls back entirely to the verified, authoritative protocol instructions.

Strict Safeguard Principles:
1. Grounded in Curated Protocols: Rules are derived strictly from curated protocols in
   backend/app/knowledge/protocols/*.json. No unverified clinical rules are invented.
2. Polarity-Aware Contradiction Detection: Differentiates safe protective warnings
   (e.g., "Do not apply ice") from dangerous affirmative recommendations ("Apply ice").
3. Contextual Essential-Action Verification: Requires the core physical intervention to be
   affirmatively instructed (e.g. chest compressions for CPR; cool water for burns).
   Generic tokens like "CPR", "FAST", or "emergency" alone do NOT satisfy the check.
4. Population-Specific Awareness: Distinguishes infant vs. adult choking interventions
   per the protocol's explicit warnings (e.g., no abdominal thrusts on infants).
5. Protocol-Scoped Substance Evaluation: Substances like aspirin or ice are evaluated
   strictly within the protocol context (aspirin is forbidden in stroke, but recommended in heart attack).
6. Fail-Closed Fallback: On any validation failure, returns is_valid=False with a specific
   reason code, allowing the caller to suppress the summary cleanly.
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger("familyconnect.safety_validator")

# Negation prefixes indicating a protective warning rather than a dangerous affirmative directive.
# Must appear within the clause preceding the prohibited action verb/target.
NEGATION_TRIGGER_PATTERN = re.compile(
    r"\b(do\s*not|don'?t|never|avoid|refrain\s*from|should\s*not|must\s*not|do\s*not\s*attempt|without|not)\b",
    re.IGNORECASE
)

# Permissible bridge words between a negation trigger and the action verb in safe warnings:
# e.g., "to", "from", "ever", "attempt to", "try to", "seek to", "even", "under any circumstances", "at any time"
SAFE_NEGATION_BRIDGE_PATTERN = re.compile(
    r"^(?:to|from|ever|attempt\s*to|try\s*to|seek\s*to|even|under\s*any\s*circumstances|at\s*any\s*time)?$",
    re.IGNORECASE
)

# Clause boundary delimiter pattern:
# Splits on sentence punctuation, colons, em-dashes (\u2014), en-dashes (\u2013), double hyphens (--),
# and subordinating/adversative clause conjunctions to prevent negation bleeding across clauses.
CLAUSE_DELIMITER_PATTERN = re.compile(
    r'[,;.!?:\n\u2014\u2013]+|--+|\s+\b(?:because|however|although|whereas|since|but)\b\s+',
    re.IGNORECASE
)

# Population detection pattern for infants (< 1 year).
# Matches explicit terms ('infant', 'baby', 'newborn', 'neonate') and age expressions
# ('6-month-old', '8 months old', 'under 12 months', 'under 1 year').
# Broad pediatric terms ('child', 'toddler', 'pediatric') do NOT classify as infant,
# preserving abdominal thrusts for older children per the curated protocol.
INFANT_POPULATION_PATTERN = re.compile(
    r"\b("
    r"infant|infants|baby|babies|newborn|newborns|neonate|neonates|"
    r"(?:under|less\s*than|below)\s*(?:1|one)\s*year(?:[- ]old)?|"
    r"(?:under|less\s*than|below)\s*(?:12|twelve)\s*months?(?:[- ]old)?|"
    r"(?:1[0-1]|[0-9]|one|two|three|four|five|six|seven|eight|nine|ten|eleven)\s*[- ]?months?(?:[- ]old)?"
    r")\b",
    re.IGNORECASE
)

# Global dangerous unauthorized folk remedies prohibited across all emergency protocols
GLOBAL_PROHIBITED_REMEDIES = [
    (re.compile(r"\b(kerosene|cow\s*dung|bleach|turmeric\s*paste|mud|ash|tobacco)\b", re.IGNORECASE), "dangerous folk remedy"),
    (re.compile(r"\b(cut|incise|slice)\s*.*(venom|poison|wound)\b", re.IGNORECASE), "dangerous incision"),
    (re.compile(r"\b(suck\s*(out)?\s*(the)?\s*(venom|poison))\b", re.IGNORECASE), "dangerous venom suction")
]

# Emergency call dissuasion pattern (actively discouraging emergency services)
EMERGENCY_DISSUASION_PATTERN = re.compile(
    r"\b(do\s*not|don'?t|never|no\s*need\s*to|avoid)\s*(call|dial|contact|alert)\s*(112|108|emergency|ambulance|hospital)\b",
    re.IGNORECASE
)


def split_into_clauses(text: str) -> List[str]:
    """
    Splits text into discrete sentences and major clauses to bound negation scope.
    Handles punctuation, em/en-dashes, double hyphens, and major clausal transitions.
    """
    raw_parts = CLAUSE_DELIMITER_PATTERN.split(text)
    clauses = [p.strip() for p in raw_parts if p.strip()]
    return clauses


def is_action_affirmed(clause: str, target_pattern: re.Pattern) -> Tuple[bool, bool]:
    """
    Checks if a target pattern appears in the clause and whether it is affirmatively
    directed or safely negated.

    Negation must be tightly scoped to the prohibited action verb.
    If intervening words indicate independent clauses or non-auxiliary words,
    the validator fails closed (treating the action as affirmative / contradiction).

    Returns:
        (pattern_found: bool, is_affirmative: bool)
        - If pattern_found is False: (False, False)
        - If pattern_found is True and safely negated: (True, False) -> Safe Negation
        - If pattern_found is True and NOT safely negated: (True, True) -> Dangerous Affirmative Directive
    """
    match = target_pattern.search(clause)
    if not match:
        return False, False

    prefix = clause[:match.start()]
    neg_matches = list(NEGATION_TRIGGER_PATTERN.finditer(prefix))
    if not neg_matches:
        return True, True  # No negation -> Dangerous affirmative

    closest_neg = neg_matches[-1]
    intervening = prefix[closest_neg.end():].strip()

    if SAFE_NEGATION_BRIDGE_PATTERN.match(intervening):
        return True, False  # Safe protective warning

    # Ambiguous or distantly separated negation fails closed as affirmative
    return True, True


# ==============================================================================
# Protocol-Specific Validation Rules
# Derived strictly from curated JSON files in backend/app/knowledge/protocols/
# ==============================================================================

# Protocol: severe_bleeding_hemorrhage.json
# Derived from: "Do not remove embedded objects", "Do not loosen or remove a tourniquet",
# "Do not remove soaked dressings", "Apply Direct, Firm Pressure"
BLEEDING_CONTRADICTIONS = [
    (re.compile(r"\b(remove|pull\s*(out)?|take\s*out|extract)\s*(the\s*)?(embedded|knife|glass|object|stake|weapon|it(\s*out)?)\b", re.IGNORECASE),
     "Removing embedded objects from a wound is strictly contraindicated."),
    (re.compile(r"\b(loosen|release|remove|take\s*off)\s*(the)?\s*tourniquet\b", re.IGNORECASE),
     "Loosening or removing a tourniquet in the field is strictly contraindicated."),
    (re.compile(r"\b(remove|pull\s*off|take\s*off)\s*(the)?\s*(soaked|blood-soaked)\s*(gauze|dressing|cloth)\b", re.IGNORECASE),
     "Removing blood-soaked dressings is contraindicated; fresh layers must be added on top.")
]
BLEEDING_ESSENTIAL_ACTION = re.compile(
    r"\b(direct\s*pressure|firm\s*pressure|continuous\s*pressure|press\s*firmly|push\s*down|apply\s*(a\s*)?tourniquet|pack\s*(the\s*)?wound)\b",
    re.IGNORECASE
)

# Protocol: choking_adult_child.json
# Derived from: "Do not perform blind finger sweeps", "Do not perform abdominal thrusts on infants"
CHOKING_CONTRADICTIONS = [
    (re.compile(r"\b(blind\s*(finger)?\s*sweep|sweep\s*blindly|insert\s*finger\s*blindly)\b", re.IGNORECASE),
     "Blind finger sweeps are contraindicated as they can push objects deeper into the airway."),
    (re.compile(r"\b(abdominal\s*thrusts?|heimlich)\s*(on|for|to)\s*(an?\s*)?(infant|baby|newborn|pregnant)\b", re.IGNORECASE),
     "Abdominal thrusts (Heimlich) are contraindicated on infants and pregnant women (chest thrusts required).")
]
CHOKING_ADULT_ESSENTIAL_ACTION = re.compile(
    r"\b(back\s*blows?|abdominal\s*thrusts?|heimlich|chest\s*thrusts?|chest\s*compressions?)\b",
    re.IGNORECASE
)
CHOKING_INFANT_ESSENTIAL_ACTION = re.compile(
    r"\b(back\s*(blows?|slaps?)|chest\s*thrusts?)\b",
    re.IGNORECASE
)

# Protocol: cpr_adult_aed.json
# Derived from: "Deliver Hard & Fast Compressions", "Ensure NO ONE touches victim during rhythm analysis or shock",
# "Do not stop CPR for more than 10 seconds"
CPR_CONTRADICTIONS = [
    (re.compile(r"\b(touch|hold|stay\s*in\s*contact)\s*.*(during|while)\s*.*(analyz|shock|defibrillat)", re.IGNORECASE),
     "Touching the victim during AED analysis or shock delivery is dangerous and contraindicated."),
    (re.compile(r"\b(stop|pause|delay)\s*compressions\s*(for\s*)?(more\s*than\s*10|extended|long)\b", re.IGNORECASE),
     "Pausing chest compressions for more than 10 seconds is contraindicated.")
]
# Generic token "CPR" or "AED" alone is NOT sufficient: the physical compressions must be articulated.
CPR_ESSENTIAL_ACTION = re.compile(
    r"\b(chest\s*compressions?|compress\s*the\s*chest|push\s*(down\s*)?(hard\s*and\s*fast|2\s*inches|in\s*the\s*center\s*of\s*the\s*chest)|100\s*(to|-)\s*120\s*(bpm|compressions?))\b",
    re.IGNORECASE
)

# Protocol: burns_thermal_chemical.json
# Derived from: "NEVER use ice, ice-cold water, butter, toothpaste, oil, or greasy ointments",
# "Do NOT pop, puncture, or peel burn blisters", "Cool Under Running Water for 20 Minutes"
BURNS_CONTRADICTIONS = [
    (re.compile(
        r"\b(apply|use|put|spread|rub|smear|submerge|immerse|douse|pack|soak)\s*.*"
        r"(ice|ice-cold|iced\s*water|ice\s*water|freezing\s*water|butter|toothpaste|oil|grease|ointment|turmeric|egg\s*white|creams?|lotions?)\b",
        re.IGNORECASE
    ),
     "Applying ice, butter, oil, toothpaste, or greasy ointments to burns is strictly contraindicated."),
    (re.compile(r"\b(pop|burst|puncture|peel|debride)\s*.*(blister)\b", re.IGNORECASE),
     "Popping or puncturing burn blisters is strictly contraindicated."),
    (re.compile(r"\b(peel|rip|pull\s*off)\s*.*(stuck|melted|adhered)\s*clothing\b", re.IGNORECASE),
     "Peeling adhered or melted fabric from burn tissue is contraindicated.")
]
BURNS_ESSENTIAL_ACTION = re.compile(
    r"\b(cool\s*(running\s*)?water|running\s*(tap\s*)?water|irrigate\s*with\s*water|cool\s*(the\s*)?burn\s*for\s*(20|ten|fifteen|several)\s*minutes?|tap\s*water)\b",
    re.IGNORECASE
)

# Protocol: stroke_fast_protocol.json
# Derived from: "NEVER give aspirin to a suspected stroke victim before hospital CT imaging",
# "Do NOT give anything by mouth (food, water, or medications)", "Perform the F.A.S.T. Test"
STROKE_CONTRADICTIONS = [
    (re.compile(r"\b(give|administer|take|chew|offer)\s*.*(aspirin|blood\s*thinner|anticoagulant)\b", re.IGNORECASE),
     "Administering aspirin before hospital CT imaging in suspected stroke is strictly contraindicated (hemorrhagic risk)."),
    (re.compile(r"\b(give|offer|drink|feed|administer)\s*.*(water|food|drink|liquid|oral\s*medication)\b", re.IGNORECASE),
     "Giving food or liquids to a suspected stroke patient is contraindicated due to swallowing paralysis and fatal aspiration risk."),
    (re.compile(r"\b(wait\s*to\s*see|sleep\s*it\s*off|wait\s*at\s*home)\b", re.IGNORECASE),
     "Delaying medical transport or waiting to see if stroke symptoms pass is contraindicated.")
]
# Generic token "FAST" alone is NOT enough: neurological check or immediate emergency escalation must be stated.
STROKE_ESSENTIAL_ACTION = re.compile(
    r"\b((check|look\s*for|test\s*for)\s*(face|arm|speech)|face\s*(droop|smile)|arm\s*(weakness|drift)|speech\s*(slur|difficult)|call\s*(112|108|emergency|ambulance))\b",
    re.IGNORECASE
)

# Protocol: heart_attack_acute_coronary.json
# Derived from: "Do not substitute acetaminophen (paracetamol) or ibuprofen for aspirin",
# "Sit the Person Down & Rest", "Call 112 / 108 Immediately"
HEART_ATTACK_CONTRADICTIONS = [
    (re.compile(r"\b(substitute|take|give|use)\s*.*(paracetamol|acetaminophen|ibuprofen|tylenol)\s*(for|instead\s*of)\s*aspirin\b", re.IGNORECASE),
     "Substituting paracetamol or ibuprofen for aspirin in acute coronary syndrome is contraindicated."),
    (re.compile(r"\b(drive\s*(yourself|themselves|the\s*patient)|walk\s*to\s*the\s*hospital|engage\s*in\s*physical\s*exertion)\b", re.IGNORECASE),
     "Walking or driving oneself to the hospital during a suspected heart attack is contraindicated.")
]
HEART_ATTACK_ESSENTIAL_ACTION = re.compile(
    r"\b(call\s*(112|108|emergency|ambulance)|sit\s*(down)?|semi-seated|rest\s*(the\s*patient)?|reduce\s*strain|chew\s*(an?\s*)?aspirin)\b",
    re.IGNORECASE
)

# Protocol: seizure_first_aid.json
# Derived from: "NEVER hold the person down or attempt to restrain", "NEVER put anything into the person's mouth"
SEIZURE_CONTRADICTIONS = [
    (re.compile(r"\b(restrain|hold\s*down|pin\s*down|force\s*limbs?\s*still)\b", re.IGNORECASE),
     "Restraining a seizing person is strictly contraindicated (risk of fractures and joint dislocations)."),
    (re.compile(r"\b(put|insert|place|force)\s*.*(in|into|between)\s*.*(mouth|teeth|jaw|tongue)\b", re.IGNORECASE),
     "Placing objects (spoons, fingers, cloth) into the mouth of a seizing person is strictly contraindicated."),
    (re.compile(r"\b(give|offer|pour)\s*.*(water|food|drink|liquid|medicine)\s*.*(during|while)\s*(seiz|fit|convuls)\b", re.IGNORECASE),
     "Giving liquids or medicine during active convulsions is contraindicated.")
]
SEIZURE_ESSENTIAL_ACTION = re.compile(
    r"\b(cushion\s*(the\s*)?head|clear\s*(away\s*)?(hazards?|objects?|furniture)|protect\s*(the\s*)?head|recovery\s*position|turn\s*(on(to)?\s*)?(their\s*)?side|time\s*the\s*seizure)\b",
    re.IGNORECASE
)

# Protocol: anaphylaxis_epinephrine.json
# Derived from: "DO NOT allow the person to stand or walk", "Do not delay epinephrine"
ANAPHYLAXIS_CONTRADICTIONS = [
    (re.compile(r"\b(allow|tell|help|let)\s*.*(stand|walk|exercise|move\s*around)\b", re.IGNORECASE),
     "Allowing an anaphylaxis patient to stand or walk is contraindicated (risk of fatal circulatory collapse)."),
    (re.compile(r"\b(delay|wait\s*before|give)\s*.*(antihistamines?|inhalers?)\s*instead\s*of\s*epinephrine\b", re.IGNORECASE),
     "Delaying epinephrine to administer oral antihistamines or inhalers in anaphylaxis is contraindicated.")
]
ANAPHYLAXIS_ESSENTIAL_ACTION = re.compile(
    r"\b(epinephrine|epipen|auto-injector|outer\s*mid-thigh|inject|lay\s*flat)\b",
    re.IGNORECASE
)

# Protocol: fractures_sprains_trauma.json
# Derived from: "Do NOT attempt to push an exposed bone back", "Do NOT attempt to straighten or realign"
FRACTURES_CONTRADICTIONS = [
    (re.compile(r"\b(push|force)\s*.*(bone|bone\s*fragment)\s*(back|beneath|in)\b", re.IGNORECASE),
     "Attempting to push an exposed bone back beneath the skin is strictly contraindicated."),
    (re.compile(r"\b(straighten|realign|manipulate|force)\s*.*(deformed|fracture|broken\s*bone|dislocated)\b", re.IGNORECASE),
     "Attempting to realign or straighten a deformed bone or dislocated joint is contraindicated.")
]
FRACTURES_ESSENTIAL_ACTION = re.compile(
    r"\b(immobiliz|support\s*(the\s*)?limb|splint|keep\s*still|rest\s*(the\s*)?limb)\b",
    re.IGNORECASE
)

# Protocol: heatstroke_exhaustion.json
# Derived from: "Do not give aspirin, paracetamol", "Cool first, transport second"
HEATSTROKE_CONTRADICTIONS = [
    (re.compile(r"\b(give|take|administer)\s*.*(aspirin|paracetamol|acetaminophen|tylenol|fever\s*reducer)\b", re.IGNORECASE),
     "Giving fever reducers (aspirin/paracetamol) for heatstroke is contraindicated (ineffective and stresses liver/kidneys)."),
    (re.compile(r"\b(force|pour)\s*.*(water|fluid|drink)\s*.*(unconscious|confused|vomiting)\b", re.IGNORECASE),
     "Giving fluids to a confused or unconscious heatstroke patient is contraindicated due to aspiration risk.")
]
HEATSTROKE_ESSENTIAL_ACTION = re.compile(
    r"\b(rapid\s*cooling|cool\s*(water|shade)|sponge|spray|fan|ice\s*packs?\s*(on|to)?\s*(neck|armpit|groin))\b",
    re.IGNORECASE
)


def validate_first_aid_summary(
    summary: str,
    protocol: Dict[str, Any],
    query: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Executes multi-stage deterministic safety validation on an LLM-generated summary.

    Args:
        summary: The raw cleaned explanation generated by the model.
        protocol: The curated protocol dictionary retrieved by RAG.
        query: The user's original query text (optional, used for population context like infants).

    Returns:
        (is_valid: bool, status_code: str, reason: Optional[str])
        - If valid: (True, "SUCCESS", None)
        - If invalid: (False, "VALIDATION_<CATEGORY>", descriptive_log_reason)
    """
    if not summary or not isinstance(summary, str):
        return False, "EMPTY_RESPONSE", "Summary is empty or invalid type."

    cleaned_summary = summary.strip()
    if len(cleaned_summary) < 20:
        return False, "EMPTY_RESPONSE", f"Summary is too short ({len(cleaned_summary)} chars)."

    protocol_id = protocol.get("protocol_id", "")
    clauses = split_into_clauses(cleaned_summary)

    # --------------------------------------------------------------------------
    # Stage 1: Global Unauthorized Remedies & Dangerous Phrasing
    # --------------------------------------------------------------------------
    for pat, label in GLOBAL_PROHIBITED_REMEDIES:
        for cl in clauses:
            found, affirmative = is_action_affirmed(cl, pat)
            if found and affirmative:
                logger.warning(f"[Safety Validator] Contradiction: Prohibited remedy '{label}' affirmatively detected in summary.")
                return False, "VALIDATION_UNGROUNDED", f"Affirmatively recommended dangerous remedy: {label}"

    # --------------------------------------------------------------------------
    # Stage 2: Emergency Escalation Integrity (Dissuasion Detection)
    # --------------------------------------------------------------------------
    if EMERGENCY_DISSUASION_PATTERN.search(cleaned_summary):
        logger.warning("[Safety Validator] Emergency dissuasion detected: Summary advises against calling emergency services.")
        return False, "VALIDATION_CONTRADICTION", "Summary discourages or advises against calling emergency services."

    # --------------------------------------------------------------------------
    # Stage 3: Protocol-Specific Polarity-Aware Contradiction Checks
    # Derived directly from what_not_to_do & critical_warnings in protocol JSON
    # --------------------------------------------------------------------------
    contradiction_rules: List[Tuple[re.Pattern, str]] = []

    if protocol_id == "severe_bleeding_hemorrhage":
        contradiction_rules = BLEEDING_CONTRADICTIONS
    elif protocol_id == "choking_adult_child":
        contradiction_rules = list(CHOKING_CONTRADICTIONS)
        is_infant = bool(INFANT_POPULATION_PATTERN.search(f"{query or ''} {cleaned_summary}"))
        if is_infant:
            contradiction_rules.append(
                (re.compile(r"\b(abdominal\s*thrusts?|heimlich)\b", re.IGNORECASE),
                 "Abdominal thrusts (Heimlich) are strictly contraindicated on infants (back slaps and chest thrusts required).")
            )
    elif protocol_id == "cpr_adult_aed":
        contradiction_rules = CPR_CONTRADICTIONS
    elif protocol_id == "burns_thermal_chemical":
        contradiction_rules = BURNS_CONTRADICTIONS
    elif protocol_id == "stroke_fast_protocol":
        contradiction_rules = STROKE_CONTRADICTIONS
    elif protocol_id == "heart_attack_acute_coronary":
        contradiction_rules = HEART_ATTACK_CONTRADICTIONS
    elif protocol_id == "seizure_first_aid":
        contradiction_rules = SEIZURE_CONTRADICTIONS
    elif protocol_id == "anaphylaxis_epinephrine":
        contradiction_rules = ANAPHYLAXIS_CONTRADICTIONS
    elif protocol_id == "fractures_sprains_trauma":
        contradiction_rules = FRACTURES_CONTRADICTIONS
    elif protocol_id == "heatstroke_exhaustion":
        contradiction_rules = HEATSTROKE_CONTRADICTIONS

    for pat, rule_desc in contradiction_rules:
        for cl in clauses:
            found, affirmative = is_action_affirmed(cl, pat)
            # Only trigger contradiction if pattern is affirmatively asserted without negation
            if found and affirmative:
                logger.warning(f"[Safety Validator] Contradiction triggered for {protocol_id}: '{rule_desc}' (Clause: '{cl}')")
                return False, "VALIDATION_CONTRADICTION", rule_desc

    # --------------------------------------------------------------------------
    # Stage 4: Contextual, Population-Specific Essential Action Verification
    # --------------------------------------------------------------------------
    # Fail closed: must affirm the protocol's primary physical intervention
    essential_action_pattern: Optional[re.Pattern] = None

    if protocol_id == "severe_bleeding_hemorrhage":
        essential_action_pattern = BLEEDING_ESSENTIAL_ACTION
    elif protocol_id == "choking_adult_child":
        # Check if query/summary context specifies an infant (<1 year)
        is_infant = bool(INFANT_POPULATION_PATTERN.search(f"{query or ''} {cleaned_summary}"))
        essential_action_pattern = CHOKING_INFANT_ESSENTIAL_ACTION if is_infant else CHOKING_ADULT_ESSENTIAL_ACTION
    elif protocol_id == "cpr_adult_aed":
        essential_action_pattern = CPR_ESSENTIAL_ACTION
    elif protocol_id == "burns_thermal_chemical":
        essential_action_pattern = BURNS_ESSENTIAL_ACTION
    elif protocol_id == "stroke_fast_protocol":
        essential_action_pattern = STROKE_ESSENTIAL_ACTION
    elif protocol_id == "heart_attack_acute_coronary":
        essential_action_pattern = HEART_ATTACK_ESSENTIAL_ACTION
    elif protocol_id == "seizure_first_aid":
        essential_action_pattern = SEIZURE_ESSENTIAL_ACTION
    elif protocol_id == "anaphylaxis_epinephrine":
        essential_action_pattern = ANAPHYLAXIS_ESSENTIAL_ACTION
    elif protocol_id == "fractures_sprains_trauma":
        essential_action_pattern = FRACTURES_ESSENTIAL_ACTION
    elif protocol_id == "heatstroke_exhaustion":
        essential_action_pattern = HEATSTROKE_ESSENTIAL_ACTION

    if essential_action_pattern is not None:
        # Check if the essential action is present anywhere in an affirmative, non-negated clause
        action_affirmed = False
        for cl in clauses:
            found, affirmative = is_action_affirmed(cl, essential_action_pattern)
            if found and affirmative:
                action_affirmed = True
                break

        if not action_affirmed:
            logger.warning(f"[Safety Validator] Omission triggered for {protocol_id}: Mandatory core clinical action not affirmatively articulated.")
            return False, "VALIDATION_OMISSION", f"Summary omitted mandatory core physical action for {protocol_id}."

    # If all stages pass deterministically:
    return True, "SUCCESS", None
