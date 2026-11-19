"""
Train an enhanced scikit-learn triage model incorporating both structured emergency indicators
and validated features extracted from free-text descriptions.
Saves model artifact to triage_model_v2.joblib while keeping triage_model.joblib available for rollback.
"""

import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score
from .context_extractor import extract_context_from_text


def build_feature_dict(
    incident_type: str,
    age: float,
    is_conscious: float,
    has_breathing_diff: float,
    is_bleeding_severely: float,
    is_alone: float,
    description: str = ""
) -> dict:
    """
    Unified feature construction function used identically during training and inference.
    Combines structured clinical indicators with NLP-extracted features.
    """
    text_result = extract_context_from_text(description)
    extracted_features = text_result["extracted_features"]

    features = {
        "incident_type": str(incident_type),
        "age": float(age if age is not None else 40),
        "is_conscious": 1.0 if is_conscious else 0.0,
        "has_breathing_diff": 1.0 if has_breathing_diff else 0.0,
        "is_bleeding_severely": 1.0 if is_bleeding_severely else 0.0,
        "is_alone": 1.0 if is_alone else 0.0,
    }
    # Add extracted text features consistently
    features.update(extracted_features)
    return features


def generate_training_data_with_text():
    """
    Augments the 660 synthetic clinical triage scenarios with realistic representative
    descriptions corresponding to patient presentation for robust DictVectorizer fitting.
    """
    np.random.seed(42)
    records = []
    labels = []

    # 1. Critical Scenarios
    for _ in range(80):
        desc = np.random.choice([
            "Patient is completely unresponsive and not waking up.",
            "Found collapsed on floor, unconscious after sudden blackout.",
            "Unconscious person, breathing sounds shallow.",
            "Unresponsive individual, family unable to wake them."
        ])
        feats = build_feature_dict(
            incident_type="Unconscious / Unresponsive",
            age=float(np.random.randint(18, 90)),
            is_conscious=0.0,
            has_breathing_diff=float(np.random.choice([0, 1])),
            is_bleeding_severely=float(np.random.choice([0, 1])),
            is_alone=float(np.random.choice([0, 1])),
            description=desc
        )
        records.append(feats)
        labels.append("CRITICAL")

    for _ in range(70):
        desc = np.random.choice([
            "Severe chest pain radiating to left arm and intense pressure.",
            "Acute cardiac distress with shortness of breath and chest tightness.",
            "Heart feels like it's being squeezed, gasping for air, alone at home.",
            "Sudden crushing chest pain, difficulty breathing."
        ])
        feats = build_feature_dict(
            incident_type="Cardiac / Chest Pain",
            age=float(np.random.randint(45, 90)),
            is_conscious=float(np.random.choice([0, 1], p=[0.2, 0.8])),
            has_breathing_diff=1.0,
            is_bleeding_severely=0.0,
            is_alone=float(np.random.choice([0, 1])),
            description=desc
        )
        records.append(feats)
        labels.append("CRITICAL")

    # 2. High Severity Scenarios
    for _ in range(80):
        desc = np.random.choice([
            "Deep cut with severe bleeding, blood loss from arm wound.",
            "Heavy bleeding from deep laceration after broken glass accident.",
            "Uncontrolled bleeding from leg injury, applying pressure.",
            "Profuse hemorrhage from traumatic puncture."
        ])
        feats = build_feature_dict(
            incident_type="Severe Bleeding",
            age=float(np.random.randint(10, 85)),
            is_conscious=1.0,
            has_breathing_diff=0.0,
            is_bleeding_severely=1.0,
            is_alone=float(np.random.choice([0, 1])),
            description=desc
        )
        records.append(feats)
        labels.append("HIGH")

    for _ in range(80):
        desc = np.random.choice([
            "Severe asthma attack, struggling to breathe and wheezing.",
            "Shortness of breath, acute respiratory difficulty.",
            "Can't breathe properly, inhaler not helping, gasping for air.",
            "Difficulty breathing with chest tightness, breathing rapidly."
        ])
        feats = build_feature_dict(
            incident_type="Breathing Difficulty",
            age=float(np.random.randint(15, 80)),
            is_conscious=1.0,
            has_breathing_diff=1.0,
            is_bleeding_severely=0.0,
            is_alone=float(np.random.choice([0, 1])),
            description=desc
        )
        records.append(feats)
        labels.append("HIGH")

    for _ in range(60):
        desc = np.random.choice([
            "Elderly grandmother fell down stairs, severe hip pain, unable to get up.",
            "Senior citizen slipped in bathroom, living alone, injured hip.",
            "Fell from bed, alone and feeling dizzy, cannot stand.",
            "Elderly person fallen, painful injury, no one else at home."
        ])
        feats = build_feature_dict(
            incident_type="Fall with Injury",
            age=float(np.random.randint(70, 95)),
            is_conscious=1.0,
            has_breathing_diff=0.0,
            is_bleeding_severely=0.0,
            is_alone=1.0,
            description=desc
        )
        records.append(feats)
        labels.append("HIGH")

    # 3. Medium Severity Scenarios
    for _ in range(80):
        desc = np.random.choice([
            "Slipped on stairs, sprained ankle and mild swelling.",
            "Tripped in garden, bruised knee, conscious and breathing normally.",
            "Fell while walking dog, moderate leg pain, accompanied by spouse.",
            "Minor fall accident, conscious with swollen wrist."
        ])
        feats = build_feature_dict(
            incident_type="Fall with Injury",
            age=float(np.random.randint(18, 65)),
            is_conscious=1.0,
            has_breathing_diff=0.0,
            is_bleeding_severely=0.0,
            is_alone=float(np.random.choice([0, 1])),
            description=desc
        )
        records.append(feats)
        labels.append("MEDIUM")

    for _ in range(70):
        desc = np.random.choice([
            "Feeling intense anxiety and panic, rapid heartbeat but conscious.",
            "Sudden panic attack, feeling dizzy and alone at home.",
            "General emergency call, high anxiety and nervousness.",
            "Distress call, panic symptoms, requests neighbor assistance."
        ])
        feats = build_feature_dict(
            incident_type="General SOS / Panic",
            age=float(np.random.randint(20, 75)),
            is_conscious=1.0,
            has_breathing_diff=0.0,
            is_bleeding_severely=0.0,
            is_alone=1.0,
            description=desc
        )
        records.append(feats)
        labels.append("MEDIUM")

    # 4. Low Severity Scenarios
    for _ in range(90):
        desc = np.random.choice([
            "Small superficial scrape on arm, no bleeding, conscious.",
            "Minor scratch on child's knee at playground, needs bandage.",
            "Mild finger cut, washed and clean, family is present.",
            "Superficial bruise, conscious, breathing fine, no chest pain."
        ])
        feats = build_feature_dict(
            incident_type="Minor Injury",
            age=float(np.random.randint(5, 75)),
            is_conscious=1.0,
            has_breathing_diff=0.0,
            is_bleeding_severely=0.0,
            is_alone=0.0,
            description=desc
        )
        records.append(feats)
        labels.append("LOW")

    for _ in range(50):
        desc = np.random.choice([
            "Accidental button press, family is fine, checking system.",
            "Testing emergency button, feeling calm, not alone.",
            "Non-urgent assistance check, no pain or bleeding.",
            "Accidental panic alert triggered while cleaning device."
        ])
        feats = build_feature_dict(
            incident_type="General SOS / Panic",
            age=float(np.random.randint(18, 50)),
            is_conscious=1.0,
            has_breathing_diff=0.0,
            is_bleeding_severely=0.0,
            is_alone=0.0,
            description=desc
        )
        records.append(feats)
        labels.append("LOW")

    return records, labels


def train_and_evaluate_v2():
    records, labels = generate_training_data_with_text()

    # Split before fitting (80% train, 20% test, stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        records, labels, test_size=0.2, random_state=42, stratify=labels
    )

    pipeline = Pipeline([
        ("vectorizer", DictVectorizer(sparse=False)),
        ("classifier", RandomForestClassifier(n_estimators=75, random_state=42, class_weight="balanced")),
    ])

    pipeline.fit(X_train, y_train)

    # Evaluate on held-out test set
    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    print(f"\n[AI Evaluation] Test Accuracy: {acc * 100:.2f}% | Macro F1: {f1_macro:.4f}")
    print("\n[AI Evaluation] Held-Out Test Classification Report:")
    print(classification_report(y_test, y_pred))

    # Refit on all 660 synthetic examples for maximum deployment robustness
    pipeline.fit(records, labels)

    save_dir = os.path.dirname(os.path.abspath(__file__))
    model_v2_path = os.path.join(save_dir, "triage_model_v2.joblib")
    joblib.dump(pipeline, model_v2_path)
    print(f"[AI Model] Model v2 saved successfully to {model_v2_path}")
    return model_v2_path


if __name__ == "__main__":
    train_and_evaluate_v2()
