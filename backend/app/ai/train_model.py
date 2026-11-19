"""
Train a scikit-learn triage severity assessment model using a synthetic emergency dataset.
Note: For demonstration and hackathon safety purposes, this model is trained on a structured,
rule-aligned synthetic dataset representing standard emergency triage prioritization principles.
"""

import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

# Synthetic dataset generator for emergency triage calibration
def generate_training_data():
    np.random.seed(42)

    records = []
    labels = []

    # 1. Critical Scenarios
    for _ in range(80):
        records.append({
            "incident_type": "Unconscious / Unresponsive",
            "age": float(np.random.randint(18, 90)),
            "is_conscious": 0.0,
            "has_breathing_diff": float(np.random.choice([0, 1])),
            "is_bleeding_severely": float(np.random.choice([0, 1])),
            "is_alone": float(np.random.choice([0, 1]))
        })
        labels.append("CRITICAL")

    for _ in range(70):
        records.append({
            "incident_type": "Cardiac / Chest Pain",
            "age": float(np.random.randint(45, 90)),
            "is_conscious": float(np.random.choice([0, 1], p=[0.2, 0.8])),
            "has_breathing_diff": 1.0,
            "is_bleeding_severely": 0.0,
            "is_alone": float(np.random.choice([0, 1]))
        })
        labels.append("CRITICAL")

    # 2. High Severity Scenarios
    for _ in range(80):
        records.append({
            "incident_type": "Severe Bleeding",
            "age": float(np.random.randint(10, 85)),
            "is_conscious": 1.0,
            "has_breathing_diff": 0.0,
            "is_bleeding_severely": 1.0,
            "is_alone": float(np.random.choice([0, 1]))
        })
        labels.append("HIGH")

    for _ in range(80):
        records.append({
            "incident_type": "Breathing Difficulty",
            "age": float(np.random.randint(15, 80)),
            "is_conscious": 1.0,
            "has_breathing_diff": 1.0,
            "is_bleeding_severely": 0.0,
            "is_alone": float(np.random.choice([0, 1]))
        })
        labels.append("HIGH")

    for _ in range(60):
        records.append({
            "incident_type": "Fall with Injury",
            "age": float(np.random.randint(70, 95)),  # Elderly fall
            "is_conscious": 1.0,
            "has_breathing_diff": 0.0,
            "is_bleeding_severely": 0.0,
            "is_alone": 1.0
        })
        labels.append("HIGH")

    # 3. Medium Severity Scenarios
    for _ in range(80):
        records.append({
            "incident_type": "Fall with Injury",
            "age": float(np.random.randint(18, 65)),
            "is_conscious": 1.0,
            "has_breathing_diff": 0.0,
            "is_bleeding_severely": 0.0,
            "is_alone": float(np.random.choice([0, 1]))
        })
        labels.append("MEDIUM")

    for _ in range(70):
        records.append({
            "incident_type": "General SOS / Panic",
            "age": float(np.random.randint(20, 75)),
            "is_conscious": 1.0,
            "has_breathing_diff": 0.0,
            "is_bleeding_severely": 0.0,
            "is_alone": 1.0
        })
        labels.append("MEDIUM")

    # 4. Low Severity Scenarios
    for _ in range(90):
        records.append({
            "incident_type": "Minor Injury",
            "age": float(np.random.randint(5, 75)),
            "is_conscious": 1.0,
            "has_breathing_diff": 0.0,
            "is_bleeding_severely": 0.0,
            "is_alone": 0.0
        })
        labels.append("LOW")

    for _ in range(50):
        records.append({
            "incident_type": "General SOS / Panic",
            "age": float(np.random.randint(18, 50)),
            "is_conscious": 1.0,
            "has_breathing_diff": 0.0,
            "is_bleeding_severely": 0.0,
            "is_alone": 0.0
        })
        labels.append("LOW")

    return records, labels


def train_and_export():
    records, labels = generate_training_data()

    pipeline = Pipeline([
        ("vectorizer", DictVectorizer(sparse=False)),
        ("classifier", RandomForestClassifier(n_estimators=60, random_state=42, class_weight="balanced")),
    ])

    pipeline.fit(records, labels)

    save_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(save_dir, "triage_model.joblib")
    joblib.dump(pipeline, model_path)
    print(f"[AI Model] Model trained successfully on {len(labels)} synthetic clinical triage scenarios.")
    print(f"[AI Model] Saved to {model_path}")
    return model_path


if __name__ == "__main__":
    train_and_export()
