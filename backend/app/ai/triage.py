import os
import math
import joblib
from typing import Dict, List, Tuple, Optional, Any
from .context_extractor import extract_context_from_text, compare_structured_and_text
from .train_model_v2 import build_feature_dict, train_and_evaluate_v2

# Support model version selection via environment variable with safe fallback
MODEL_V2_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "triage_model_v2.joblib")
MODEL_V1_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "triage_model.joblib")

# Default to v2 if available, fallback to v1
_model = None
_model_version = "v2"


def get_model(force_reload: bool = False):
    global _model, _model_version
    chosen_version = os.environ.get("TRIAGE_MODEL_VERSION", "v2").lower()
    
    # Reload if uninitialized, version changed, or force_reload requested
    if _model is None or _model_version != chosen_version or force_reload:
        try:
            if chosen_version == "v1" and os.path.exists(MODEL_V1_PATH):
                _model = joblib.load(MODEL_V1_PATH)
                _model_version = "v1"
                print("[AI Engine] Loaded baseline Model v1 (triage_model.joblib).")
            else:
                if not os.path.exists(MODEL_V2_PATH):
                    if os.path.exists(MODEL_V1_PATH):
                        print("[AI Engine] Model v2 artifact missing, falling back to v1 baseline...")
                        _model = joblib.load(MODEL_V1_PATH)
                        _model_version = "v1"
                    else:
                        print("[AI Engine] Model artifacts missing. Training v2...")
                        train_and_evaluate_v2()
                        _model = joblib.load(MODEL_V2_PATH)
                        _model_version = "v2"
                else:
                    _model = joblib.load(MODEL_V2_PATH)
                    _model_version = "v2"
                    print("[AI Engine] Loaded enhanced Model v2 (triage_model_v2.joblib).")
        except Exception as err:
            print(f"[AI Engine Warning] Failed to load model artifact: {err}. Setting _model to None for rule-based fallback.")
            _model = None
            _model_version = chosen_version
    return _model



def assess_emergency(
    incident_type: str,
    age: int = 40,
    is_conscious: bool = True,
    has_breathing_diff: bool = False,
    is_bleeding_severely: bool = False,
    is_alone: bool = True,
    description: Optional[str] = ""
) -> Dict[str, Any]:
    """
    Evaluates emergency triage severity using the Scikit-learn Random Forest model
    incorporating structured vital flags AND validated free-text context features.
    Produces evidence-based risk explanations with conflict detection.
    """
    model = get_model()

    # 1. NLP Context Extraction
    text_result = extract_context_from_text(description or "")
    extracted_concepts = text_result.get("extracted_concepts", [])
    negated_concepts = text_result.get("negated_concepts", [])

    # 2. Check for discrepancies between structured checkboxes and user description
    structured_flags = {
        "is_conscious": is_conscious,
        "is_bleeding_severely": is_bleeding_severely,
        "has_breathing_difficulty": has_breathing_diff,
        "is_alone": is_alone
    }
    has_conflicts, conflict_warnings = compare_structured_and_text(structured_flags, text_result)

    # 3. Build unified feature dictionary
    # CRITICAL SAFETY RULE: Extracted text never silently overrides positive critical structured flags
    eff_conscious = 0.0 if not is_conscious or "unconscious" in extracted_concepts else 1.0
    eff_bleeding = 1.0 if is_bleeding_severely or "severe_bleeding" in extracted_concepts else 0.0
    eff_breathing = 1.0 if has_breathing_diff or "breathing_difficulty" in extracted_concepts else 0.0
    eff_alone = 1.0 if is_alone or "alone" in extracted_concepts else 0.0

    # If model is v1, build legacy features; if v2, include text features
    if _model_version == "v1":
        feature_dict = {
            "incident_type": incident_type,
            "age": float(age if age is not None else 40),
            "is_conscious": eff_conscious,
            "has_breathing_diff": eff_breathing,
            "is_bleeding_severely": eff_bleeding,
            "is_alone": eff_alone,
        }
    else:
        feature_dict = build_feature_dict(
            incident_type=incident_type,
            age=float(age if age is not None else 40),
            is_conscious=eff_conscious,
            has_breathing_diff=eff_breathing,
            is_bleeding_severely=eff_bleeding,
            is_alone=eff_alone,
            description=description or ""
        )

    raw_model_prediction = None
    raw_model_confidence = None
    safety_override_applied = False
    safety_override_reason = None
    prediction_source = f"ML_MODEL_{_model_version.upper()}"

    try:
        if model is None:
            raise RuntimeError("Model artifact is uninitialized or unavailable")
        raw_pred = str(model.predict([feature_dict])[0])
        probabilities = model.predict_proba([feature_dict])[0]
        classes = list(model.classes_)
        pred_idx = classes.index(raw_pred)
        raw_conf = float(probabilities[pred_idx])

        raw_model_prediction = raw_pred
        raw_model_confidence = round(raw_conf, 3)

        prediction = raw_pred
        confidence = raw_conf

        # Deterministic Clinical Safety Override Floor (distinct from learned model output):
        # If active unresponsiveness is confirmed via structured flag or text, severity floor is CRITICAL.
        # If severe hemorrhage or airway compromise is confirmed, severity floor is at least HIGH.
        if eff_conscious < 0.5 and prediction != "CRITICAL":
            safety_override_applied = True
            safety_override_reason = (
                f"Deterministic safety rule elevated severity from raw model prediction ({raw_pred}) "
                f"to CRITICAL due to confirmed unresponsiveness."
            )
            prediction = "CRITICAL"
            confidence = max(raw_conf, 0.90)
            prediction_source = "DETERMINISTIC_SAFETY_OVERRIDE"
        elif (eff_bleeding > 0.5 or eff_breathing > 0.5) and prediction in ["LOW", "MEDIUM"]:
            safety_override_applied = True
            safety_override_reason = (
                f"Deterministic safety rule elevated severity from raw model prediction ({raw_pred}) "
                f"to HIGH due to active severe hemorrhage or respiratory distress."
            )
            prediction = "HIGH"
            confidence = max(raw_conf, 0.85)
            prediction_source = "DETERMINISTIC_SAFETY_OVERRIDE"

    except Exception as e:
        # Safe deterministic rule-based fallback if model is missing or inference encounters unexpected error
        safety_override_applied = True
        prediction_source = "DETERMINISTIC_RULE_FALLBACK"
        if not is_conscious or eff_conscious < 0.5:
            prediction = "CRITICAL"
            confidence = 0.90
        elif is_bleeding_severely or eff_bleeding > 0.5 or has_breathing_diff or eff_breathing > 0.5:
            prediction = "HIGH"
            confidence = 0.85
        elif "Cardiac" in incident_type or "Chest" in incident_type:
            prediction = "HIGH"
            confidence = 0.80
        elif is_alone:
            prediction = "MEDIUM"
            confidence = 0.75
        else:
            prediction = "LOW"
            confidence = 0.70
        safety_override_reason = f"Deterministic fallback rules executed because ML model was unavailable ({type(e).__name__})."
        print(f"[AI Engine Fallback] Deterministic rule-based assessment active ({prediction}): {e}")

    # 4. Evidence-based explanation generation
    structured_factors = []
    if not is_conscious:
        structured_factors.append("Loss of consciousness / unresponsiveness confirmed")
    if has_breathing_diff:
        structured_factors.append("Respiratory distress or compromised airway confirmed")
    if is_bleeding_severely:
        structured_factors.append("Active severe hemorrhage confirmed")
    if age and age >= 65:
        structured_factors.append(f"Geriatric vulnerability tier (Age: {age})")
    if is_alone:
        structured_factors.append("Patient isolated with no immediate on-scene support")
    if "Cardiac" in incident_type or "Chest" in incident_type:
        structured_factors.append("Cardiovascular crisis indication")

    text_factors = []
    concept_labels = {
        "chest_pain": "Mention of chest pain / cardiac pressure",
        "breathing_difficulty": "Mention of respiratory difficulty or shortness of breath",
        "unconscious": "Mention of unresponsiveness or blackout",
        "severe_bleeding": "Mention of heavy or profuse bleeding",
        "fall_or_trauma": "Mention of fall, collision, or traumatic impact",
        "dizziness": "Mention of dizziness or vertigo",
        "alone": "Mention of patient being alone / isolated",
        "minor_injury": "Mention of superficial injury or mild scrape"
    }
    for c in extracted_concepts:
        if c in concept_labels:
            text_factors.append(concept_labels[c])

    # Recommended next actions map
    action_map = {
        "CRITICAL": "Immediate emergency dispatch required. Prepare AED / Advanced Life Support.",
        "HIGH": "Priority dispatch. Notify nearest paramedic and primary emergency contact immediately.",
        "MEDIUM": "Alert nearby family and neighborhood first responder. Monitor closely.",
        "LOW": "Notify family contacts. Administer basic first aid if needed."
    }

    # Formulate clear rationale summary distinguishing ML prediction vs deterministic safety rules
    if safety_override_applied and raw_model_prediction:
        lead_sentence = (
            f"Classified as {prediction} via Deterministic Safety Override "
            f"(Raw ML Model v2 predicted {raw_model_prediction} at {int((raw_model_confidence or 0) * 100)}% certainty; "
            f"{safety_override_reason})"
        )
    elif prediction_source == "DETERMINISTIC_RULE_FALLBACK":
        lead_sentence = f"Classified as {prediction} via Deterministic Fallback Rules (ML model unavailable)."
    else:
        lead_sentence = (
            f"Classified as {prediction} ({int(confidence * 100)}% model certainty based on synthetic clinical scenarios; "
            f"experimental decision support only)."
        )

    rationale_parts = [lead_sentence]
    if structured_factors:
        rationale_parts.append("Structured Flags: " + "; ".join(structured_factors))
    if text_factors:
        rationale_parts.append("Text Evidence Extracted: " + "; ".join(text_factors))
    if negated_concepts:
        rationale_parts.append("Explicitly Negated: " + ", ".join(negated_concepts))
    if conflict_warnings:
        rationale_parts.append("⚠️ Input Discrepancies: " + " ".join(conflict_warnings))

    full_rationale = " • ".join(rationale_parts)

    return {
        "severity_level": prediction,
        "severity_score": round(confidence, 3),
        "confidence_percentage": round(confidence * 100, 1),
        "ai_rationale": full_rationale,
        "risk_factors": structured_factors,
        "extracted_concepts": extracted_concepts,
        "negated_concepts": negated_concepts,
        "has_conflicts": has_conflicts,
        "conflict_warnings": conflict_warnings,
        "model_version": _model_version,
        "raw_model_prediction": raw_model_prediction,
        "raw_model_confidence": raw_model_confidence,
        "safety_override_applied": safety_override_applied,
        "safety_override_reason": safety_override_reason,
        "prediction_source": prediction_source,
        "recommended_action": action_map.get(prediction, "Monitor patient condition closely.")
    }



def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points in kilometers.
    """
    R = 6371.0  # Earth's radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def rank_responders(
    incident_lat: float,
    incident_lon: float,
    responders: List[Dict],
    top_k: int = 4
) -> List[Dict]:
    """
    Ranks active responders that possess valid geographic coordinates
    by availability and Haversine proximity. Never invents coordinates.
    """
    if incident_lat is None or incident_lon is None:
        return []

    try:
        f_lat = float(incident_lat)
        f_lon = float(incident_lon)
        if f_lat == 0.0 and f_lon == 0.0:
            return []
    except (ValueError, TypeError):
        return []

    scored = []
    for r in responders:
        if not r.get("is_active", True) or r.get("is_demo", False):
            continue
        r_lat = r.get("latitude")
        r_lon = r.get("longitude")
        if r_lat is None or r_lon is None:
            continue
        dist = calculate_haversine_distance(float(incident_lat), float(incident_lon), float(r_lat), float(r_lon))
        scored.append({
            **r,
            "distance_km": dist
        })

    scored.sort(key=lambda x: (not x.get("is_available", True), x["distance_km"]))
    return scored[:top_k]
