"""
FamilyConnect AI - Phase 5D Independent Holdout Evaluation Suite
Evaluates the triage ML model (v2) and the hybrid deterministic safety layer
against 40 independently authored emergency scenarios NOT used during training.
Computes confusion matrix, per-class precision/recall/F1, and macro F1.
"""

from typing import Dict, List, Any
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, accuracy_score
from .triage import assess_emergency

CLASSES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

# 40 Independently Authored Holdout Scenarios (10 per severity class)
# Written independently of train_model_v2.py templates, testing diverse phrasing,
# cross-category combinations, negations, and edge cases.
INDEPENDENT_BENCHMARK_SCENARIOS: List[Dict[str, Any]] = [
    # --- CRITICAL (10 scenarios) ---
    {
        "id": "IND-C01",
        "incident_type": "Cardiac / Chest Pain",
        "age": 69,
        "is_conscious": False,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Father collapsed in hallway after complaining of tightness in chest, not waking up and gasping.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C02",
        "incident_type": "Unconscious / Unresponsive",
        "age": 26,
        "is_conscious": False,
        "has_breathing_diff": False,
        "is_bleeding_severely": True,
        "is_alone": True,
        "description": "Rahul struck by vehicle at crosswalk. Blacked out on asphalt with blood gushing from forearm. Denies chest pain prior.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C03",
        "incident_type": "Fall with Injury",
        "age": 82,
        "is_conscious": False,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Grandmother tumbled down basement steps, found unresponsive on concrete floor, shallow breathing.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C04",
        "incident_type": "Severe Bleeding",
        "age": 34,
        "is_conscious": False,
        "has_breathing_diff": True,
        "is_bleeding_severely": True,
        "is_alone": False,
        "description": "Power saw workshop accident. Arterial bleed from thigh, patient just fainted and is unresponsive.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C05",
        "incident_type": "Breathing Difficulty",
        "age": 12,
        "is_conscious": False,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Severe peanut anaphylaxis, child cannot breathe, lips turning blue and just lost consciousness.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C06",
        "incident_type": "Cardiac / Chest Pain",
        "age": 77,
        "is_conscious": True,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Living alone, sudden crushing chest pressure radiating to jaw, breathless and sweating.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C07",
        "incident_type": "General SOS / Panic",
        "age": 55,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Bystander clicked general SOS, but victim is actually passed out cold on sidewalk and not waking up.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C08",
        "incident_type": "Unconscious / Unresponsive",
        "age": 61,
        "is_conscious": False,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Diabetic hypoglycemia episode, found comatose in kitchen by neighbor, no bleeding.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C09",
        "incident_type": "Cardiac / Chest Pain",
        "age": 58,
        "is_conscious": True,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Suspected heart attack at home alone, acute angina and shortness of breath. No trauma or fall.",
        "expected": "CRITICAL"
    },
    {
        "id": "IND-C10",
        "incident_type": "Minor Injury",
        "age": 40,
        "is_conscious": False,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Caller selected minor injury by mistake, patient fainted after head impact and is completely unconscious.",
        "expected": "CRITICAL"
    },

    # --- HIGH (10 scenarios) ---
    {
        "id": "IND-H01",
        "incident_type": "Severe Bleeding",
        "age": 29,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": True,
        "is_alone": False,
        "description": "Kitchen knife slipped, deep cut on wrist with heavy bleeding. Patient is awake and holding towel on wound.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H02",
        "incident_type": "Breathing Difficulty",
        "age": 19,
        "is_conscious": True,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Acute asthma flare-up in dorm room alone, wheezing audibly and struggling to catch breath. Conscious.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H03",
        "incident_type": "Fall with Injury",
        "age": 79,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Elderly resident slipped on wet patio, unable to stand due to hip trauma, entirely alone at home.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H04",
        "incident_type": "Severe Bleeding",
        "age": 47,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": True,
        "is_alone": True,
        "description": "Shattered window pane caused deep laceration on leg, blood loss continuing. Alert, no breathing trouble.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H05",
        "incident_type": "Breathing Difficulty",
        "age": 64,
        "is_conscious": True,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "COPD patient experiencing severe dyspnea and shortness of breath. Awake with spouse present, no bleeding.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H06",
        "incident_type": "Fall with Injury",
        "age": 84,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "84-year-old grandfather fell out of bed, feeling dizzy and isolated in apartment. Denies chest pain.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H07",
        "incident_type": "Minor Injury",
        "age": 33,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": True,
        "is_alone": False,
        "description": "Reported as minor injury, but wound has active severe hemorrhage that will not stop.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H08",
        "incident_type": "Breathing Difficulty",
        "age": 41,
        "is_conscious": True,
        "has_breathing_diff": True,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Smoke inhalation from stove fire, coughing and difficulty breathing. Alert and outside now.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H09",
        "incident_type": "Severe Bleeding",
        "age": 22,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": True,
        "is_alone": False,
        "description": "Compound ankle trauma from bicycle crash with profuse bleeding. Awake and talking.",
        "expected": "HIGH"
    },
    {
        "id": "IND-H10",
        "incident_type": "Fall with Injury",
        "age": 74,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Senior citizen tripped over rug, wrist deformity and dizziness, living alone.",
        "expected": "HIGH"
    },

    # --- MEDIUM (10 scenarios) ---
    {
        "id": "IND-M01",
        "incident_type": "Fall with Injury",
        "age": 38,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Slipped while jogging on curb, twisted ankle with moderate swelling. No bleeding, breathing fine.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M02",
        "incident_type": "General SOS / Panic",
        "age": 27,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Walking home late, feeling lightheaded and anxious, alone and requesting family check-in. No chest pain.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M03",
        "incident_type": "Fall with Injury",
        "age": 52,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Tripped on porch step carrying groceries, bruised knee and sore shoulder. Alert, no blood loss.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M04",
        "incident_type": "General SOS / Panic",
        "age": 45,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Experiencing vertigo and dizziness while home alone. Denies shortness of breath, denies chest pain.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M05",
        "incident_type": "Fall with Injury",
        "age": 24,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Skateboard tumble in park, sprained wrist, friends are present. Conscious and no bleeding.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M06",
        "incident_type": "General SOS / Panic",
        "age": 60,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Power outage at house, feeling unsteady and nervous by herself. No injury or bleeding.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M07",
        "incident_type": "Fall with Injury",
        "age": 49,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Slipped on wet grass, painful ankle sprain, spouse helping him up. Without dizziness or bleeding.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M08",
        "incident_type": "General SOS / Panic",
        "age": 31,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Acute panic episode at office after hours, trembling and dizzy, alone in building.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M09",
        "incident_type": "Fall with Injury",
        "age": 35,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Fell off stationary bike in garage, bruised elbow, alone at home. No head impact, not unconscious.",
        "expected": "MEDIUM"
    },
    {
        "id": "IND-M10",
        "incident_type": "General SOS / Panic",
        "age": 50,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": True,
        "description": "Feeling unwell and lightheaded alone in apartment, requesting neighbor visit.",
        "expected": "MEDIUM"
    },

    # --- LOW (10 scenarios) ---
    {
        "id": "IND-L01",
        "incident_type": "Minor Injury",
        "age": 9,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Child scraped elbow on backyard swing, superficial scratch, mother cleaning with antiseptic.",
        "expected": "LOW"
    },
    {
        "id": "IND-L02",
        "incident_type": "Minor Injury",
        "age": 32,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Small paper cut and minor bruise on finger, no bleeding now, completely fine.",
        "expected": "LOW"
    },
    {
        "id": "IND-L03",
        "incident_type": "General SOS / Panic",
        "age": 28,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Accidental SOS button tap while adjusting phone case. Everyone is safe, no emergency.",
        "expected": "LOW"
    },
    {
        "id": "IND-L04",
        "incident_type": "Minor Injury",
        "age": 14,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Minor knee bruise during soccer practice, coach and parents present. No dizziness, no shortness of breath.",
        "expected": "LOW"
    },
    {
        "id": "IND-L05",
        "incident_type": "Minor Injury",
        "age": 44,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Superficial rose thorn scratch on hand while gardening with partner. Needs band-aid only.",
        "expected": "LOW"
    },
    {
        "id": "IND-L06",
        "incident_type": "General SOS / Panic",
        "age": 36,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Routine test of family check-in alert with family present in living room. No pain, no bleeding.",
        "expected": "LOW"
    },
    {
        "id": "IND-L07",
        "incident_type": "Minor Injury",
        "age": 21,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Stubbed toe on coffee table, mild pain, roommate is here. Denies dizziness or bleeding.",
        "expected": "LOW"
    },
    {
        "id": "IND-L08",
        "incident_type": "Minor Injury",
        "age": 53,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Small kitchen blister on thumb from warm pan, washed with cold water, family home.",
        "expected": "LOW"
    },
    {
        "id": "IND-L09",
        "incident_type": "General SOS / Panic",
        "age": 25,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "False alarm triggered by toddler playing with tablet. No injury, everyone healthy.",
        "expected": "LOW"
    },
    {
        "id": "IND-L10",
        "incident_type": "Minor Injury",
        "age": 62,
        "is_conscious": True,
        "has_breathing_diff": False,
        "is_bleeding_severely": False,
        "is_alone": False,
        "description": "Minor fingernail snag, superficial scrape, no bleeding and no chest pain.",
        "expected": "LOW"
    }
]


def run_independent_evaluation() -> Dict[str, Any]:
    """
    Runs all 40 independent scenarios through assess_emergency() and computes:
    1) Raw ML Model v2 metrics (before deterministic safety overrides)
    2) Hybrid System metrics (ML Model v2 + Deterministic Clinical Safety Overrides)
    """
    y_true = []
    y_raw_model = []
    y_hybrid = []
    safety_overrides_triggered = []
    scenario_details = []

    for sc in INDEPENDENT_BENCHMARK_SCENARIOS:
        res = assess_emergency(
            incident_type=sc["incident_type"],
            age=sc["age"],
            is_conscious=sc["is_conscious"],
            has_breathing_diff=sc["has_breathing_diff"],
            is_bleeding_severely=sc["is_bleeding_severely"],
            is_alone=sc["is_alone"],
            description=sc["description"]
        )
        expected = sc["expected"]
        raw_pred = res.get("raw_model_prediction") or res["severity_level"]
        hybrid_pred = res["severity_level"]

        y_true.append(expected)
        y_raw_model.append(raw_pred)
        y_hybrid.append(hybrid_pred)

        if res.get("safety_override_applied"):
            safety_overrides_triggered.append({
                "id": sc["id"],
                "expected": expected,
                "raw_model_prediction": raw_pred,
                "final_prediction": hybrid_pred,
                "reason": res.get("safety_override_reason")
            })

        scenario_details.append({
            "id": sc["id"],
            "expected": expected,
            "raw_model_prediction": raw_pred,
            "hybrid_prediction": hybrid_pred,
            "safety_override_applied": res.get("safety_override_applied", False),
            "extracted_concepts": res.get("extracted_concepts", []),
            "negated_concepts": res.get("negated_concepts", []),
            "has_conflicts": res.get("has_conflicts", False)
        })

    # Compute Raw Model Metrics
    raw_cm = confusion_matrix(y_true, y_raw_model, labels=CLASSES).tolist()
    raw_p, raw_r, raw_f1, raw_sup = precision_recall_fscore_support(
        y_true, y_raw_model, labels=CLASSES, zero_division=0
    )
    raw_acc = float(accuracy_score(y_true, y_raw_model))
    raw_macro_f1 = float(raw_f1.mean())

    # Compute Hybrid (Model + Safety Layer) Metrics
    hyb_cm = confusion_matrix(y_true, y_hybrid, labels=CLASSES).tolist()
    hyb_p, hyb_r, hyb_f1, hyb_sup = precision_recall_fscore_support(
        y_true, y_hybrid, labels=CLASSES, zero_division=0
    )
    hyb_acc = float(accuracy_score(y_true, y_hybrid))
    hyb_macro_f1 = float(hyb_f1.mean())

    per_class_raw = {}
    per_class_hybrid = {}
    for idx, cls_name in enumerate(CLASSES):
        per_class_raw[cls_name] = {
            "precision": round(float(raw_p[idx]), 3),
            "recall": round(float(raw_r[idx]), 3),
            "f1": round(float(raw_f1[idx]), 3),
            "support": int(raw_sup[idx])
        }
        per_class_hybrid[cls_name] = {
            "precision": round(float(hyb_p[idx]), 3),
            "recall": round(float(hyb_r[idx]), 3),
            "f1": round(float(hyb_f1[idx]), 3),
            "support": int(hyb_sup[idx])
        }

    return {
        "benchmark_name": "Phase 5D Independent Holdout Benchmark (40 Hand-Authored Scenarios)",
        "total_scenarios": len(INDEPENDENT_BENCHMARK_SCENARIOS),
        "classes": CLASSES,
        "raw_ml_model": {
            "description": "Scikit-learn RandomForestClassifier (triage_model_v2.joblib) alone without deterministic safety rules",
            "accuracy": round(raw_acc, 4),
            "macro_f1": round(raw_macro_f1, 4),
            "confusion_matrix": raw_cm,
            "per_class_metrics": per_class_raw
        },
        "hybrid_safety_system": {
            "description": "ML Model v2 + Deterministic Clinical Safety Override Floor (production configuration)",
            "accuracy": round(hyb_acc, 4),
            "macro_f1": round(hyb_macro_f1, 4),
            "confusion_matrix": hyb_cm,
            "per_class_metrics": per_class_hybrid,
            "safety_overrides_count": len(safety_overrides_triggered),
            "safety_overrides_triggered": safety_overrides_triggered
        },
        "limitations_and_disclaimers": [
            "Trained on 660 synthetic emergency configurations; not trained on real hospital EHR or EMS dispatch records.",
            "Not clinically validated or FDA/CE certified as a medical device; intended solely for hackathon decision-support demonstration.",
            "NLP context extractor uses deterministic regular expressions and 35-character clause-bounded negation windows; complex sarcasm or rare clinical terminology may not be extracted.",
            "When structured checkboxes conflict with free-text bystander notes, deterministic safety rules enforce a floor (CRITICAL for unresponsiveness, HIGH for severe bleeding/airway distress) rather than relying solely on statistical tree voting."
        ],
        "scenario_details": scenario_details
    }


def evaluate_holdout_benchmark() -> Dict[str, Any]:
    """
    Wrapper returning both the raw evaluation report and normalized keys for API/UI consumption.
    """
    base = run_independent_evaluation()
    classes = base["classes"]
    raw_cm_list = base["raw_ml_model"]["confusion_matrix"]
    hyb_cm_list = base["hybrid_safety_system"]["confusion_matrix"]

    raw_cm_dict = {
        classes[i]: {classes[j]: int(raw_cm_list[i][j]) for j in range(len(classes))}
        for i in range(len(classes))
    }
    hyb_cm_dict = {
        classes[i]: {classes[j]: int(hyb_cm_list[i][j]) for j in range(len(classes))}
        for i in range(len(classes))
    }

    base["labels"] = classes
    base["safety_overrides_count"] = base["hybrid_safety_system"]["safety_overrides_count"]
    base["raw_ml_model_v2"] = {
        "accuracy": base["raw_ml_model"]["accuracy"],
        "accuracy_pct": round(base["raw_ml_model"]["accuracy"] * 100.0, 2),
        "macro_f1": base["raw_ml_model"]["macro_f1"],
        "per_class": base["raw_ml_model"]["per_class_metrics"],
        "confusion_matrix": raw_cm_dict
    }
    base["hybrid_system_ml_plus_safety_rules"] = {
        "accuracy": base["hybrid_safety_system"]["accuracy"],
        "accuracy_pct": round(base["hybrid_safety_system"]["accuracy"] * 100.0, 2),
        "macro_f1": base["hybrid_safety_system"]["macro_f1"],
        "per_class": base["hybrid_safety_system"]["per_class_metrics"],
        "confusion_matrix": hyb_cm_dict
    }
    return base


if __name__ == "__main__":
    import json
    report = evaluate_holdout_benchmark()
    print(json.dumps({k: v for k, v in report.items() if k != "scenario_details"}, indent=2))

