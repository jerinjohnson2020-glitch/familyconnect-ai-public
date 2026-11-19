import React, { useState, useEffect } from 'react';
import { Bot, Play, Sparkles, AlertTriangle, ShieldCheck, Info, FileText, CheckCircle2, BarChart3 } from 'lucide-react';
import { testAiTriage, getAiEvaluationBenchmark } from '../services/api';

const SAMPLE_PRESETS = [
  {
    name: "Rahul Road-Accident (PPT Slide 6)",
    type: "Unconscious / Unresponsive",
    age: 26,
    conscious: false,
    breathing: true,
    bleeding: true,
    alone: true,
    description: "Rahul involved in high-speed collision at junction. Severe laceration on arm with arterial bleeding, lost consciousness for 2 minutes, visibly dizzy and disoriented."
  },
  {
    name: "Elderly Fall & Cardiac Signs",
    type: "Cardiac / Chest Pain",
    age: 78,
    conscious: true,
    breathing: true,
    bleeding: false,
    alone: true,
    description: "Grandfather collapsed in living room clutching left chest. Complains of crushing pressure and acute shortness of breath. No bleeding observed."
  },
  {
    name: "Child Playground Scratch (Minor)",
    type: "Minor Injury",
    age: 8,
    conscious: true,
    breathing: false,
    bleeding: false,
    alone: false,
    description: "Small knee scrape from playground slide. Denies dizziness, denies chest pain, breathing normally, alert and talking with mother."
  },
  {
    name: "Safety Override Demo (Minor Type + Severe Bleeding)",
    type: "Minor Injury",
    age: 35,
    conscious: true,
    breathing: false,
    bleeding: true,
    alone: false,
    description: "Deep laceration from broken glass with active arterial bleeding."
  }
];

export default function AiTriageTester() {
  const [incidentType, setIncidentType] = useState('Cardiac / Chest Pain');
  const [age, setAge] = useState(72);
  const [isConscious, setIsConscious] = useState(true);
  const [hasBreathing, setHasBreathing] = useState(true);
  const [isBleeding, setIsBleeding] = useState(false);
  const [isAlone, setIsAlone] = useState(true);
  const [description, setDescription] = useState('');

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [benchmarkReport, setBenchmarkReport] = useState(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    setBenchmarkLoading(true);
    getAiEvaluationBenchmark()
      .then((data) => {
        if (mounted) setBenchmarkReport(data);
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setBenchmarkLoading(false);
      });
    return () => { mounted = false; };
  }, []);

  const runPrediction = async (customParams = null) => {
    setLoading(true);
    setError('');
    const params = customParams || {
      incident_type: incidentType,
      age: parseInt(age, 10),
      is_conscious: isConscious,
      has_breathing_difficulty: hasBreathing,
      is_bleeding_severely: isBleeding,
      is_alone: isAlone,
      description: description.trim()
    };

    try {
      const data = await testAiTriage(params);
      setResult(data);
    } catch (err) {
      setError(err.message || 'Prediction failed');
    } finally {
      setLoading(false);
    }
  };

  const loadPreset = (preset) => {
    setIncidentType(preset.type);
    setAge(preset.age);
    setIsConscious(preset.conscious);
    setHasBreathing(preset.breathing);
    setIsBleeding(preset.bleeding);
    setIsAlone(preset.alone);
    setDescription(preset.description || '');
    runPrediction({
      incident_type: preset.type,
      age: preset.age,
      is_conscious: preset.conscious,
      has_breathing_difficulty: preset.breathing,
      is_bleeding_severely: preset.bleeding,
      is_alone: preset.alone,
      description: preset.description || ''
    });
  };

  return (
    <div>
      <div className="toolbar-strip">
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Bot size={20} color="#c084fc" /> Explainable Scikit-Learn Triage AI Testing Sandbox (v2)
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.15rem' }}>
            Simulate emergency conditions combining structured vital signs and natural language bystander notes with multi-factor evidence rationale
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Quick Presets:</span>
          {SAMPLE_PRESETS.map((p, idx) => (
            <button
              key={idx}
              type="button"
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.55rem' }}
              onClick={() => loadPreset(p)}
            >
              <Sparkles size={11} color="#fbbf24" /> {p.name}
            </button>
          ))}
        </div>
      </div>

      <div className="sandbox-grid">
        {/* Controls Card */}
        <div className="fc-panel">
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.85rem' }}>
            Emergency Signal Inputs
          </h3>

          <div className="form-group">
            <label className="form-label" htmlFor="sandbox-incident">Incident Type</label>
            <select
              id="sandbox-incident"
              className="form-select"
              value={incidentType}
              onChange={(e) => setIncidentType(e.target.value)}
            >
              <option value="Cardiac / Chest Pain">Cardiac / Chest Pain</option>
              <option value="Breathing Difficulty">Breathing Difficulty</option>
              <option value="Unconscious / Unresponsive">Unconscious / Unresponsive</option>
              <option value="Severe Bleeding">Severe Bleeding</option>
              <option value="Fall with Injury">Fall with Injury</option>
              <option value="Minor Injury">Minor Injury</option>
              <option value="General SOS / Panic">General SOS / Panic</option>
            </select>
          </div>

          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
              <label className="form-label" style={{ margin: 0 }} htmlFor="sandbox-age">Patient Age</label>
              <strong style={{ fontSize: '0.825rem', color: 'var(--color-primary)' }}>{age} years</strong>
            </div>
            <input
              id="sandbox-age"
              type="range"
              min="1"
              max="95"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              style={{ width: '100%', accentColor: 'var(--color-primary)' }}
            />
          </div>

          {/* Structured Vital Checkboxes */}
          <div style={{
            background: 'var(--bg-primary)',
            padding: '0.75rem',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
            marginTop: '0.75rem'
          }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
              Structured Vital Checkboxes
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={!isConscious}
                onChange={(e) => setIsConscious(!e.target.checked)}
              />
              <span style={{ color: !isConscious ? '#f87171' : 'inherit' }}>Patient is Unconscious / Fainting</span>
            </label>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={hasBreathing}
                onChange={(e) => setHasBreathing(e.target.checked)}
              />
              <span style={{ color: hasBreathing ? '#fb923c' : 'inherit' }}>Respiratory Distress Reported</span>
            </label>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={isBleeding}
                onChange={(e) => setIsBleeding(e.target.checked)}
              />
              <span style={{ color: isBleeding ? '#f87171' : 'inherit' }}>Active Severe Hemorrhage</span>
            </label>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={isAlone}
                onChange={(e) => setIsAlone(e.target.checked)}
              />
              <span>Patient Alone (No Immediate Assistance)</span>
            </label>
          </div>

          {/* Free-text Description / Notes Input */}
          <div className="form-group" style={{ marginTop: '0.85rem' }}>
            <label className="form-label" htmlFor="sandbox-description" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <FileText size={13} color="var(--color-primary)" /> Free-Text Description / Bystander Notes
            </label>
            <textarea
              id="sandbox-description"
              className="form-textarea"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Rahul hit by motorcycle at crossing, heavy bleeding from arm, unconscious initially but now coughing. No chest pain reported."
              style={{ fontSize: '0.8rem', resize: 'vertical' }}
            />
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
              Extracted for NLP symptoms (chest pain, breathing, bleeding, unconsciousness, alone) with clause negation handling.
            </div>
          </div>

          <div style={{ marginTop: '1.25rem' }}>
            <button
              type="button"
              className="btn-primary"
              style={{ width: '100%' }}
              disabled={loading}
              onClick={() => runPrediction()}
            >
              <Play size={14} /> {loading ? 'Running scikit-learn v2 Inference...' : 'Evaluate Emergency Severity'}
            </button>
          </div>
        </div>

        {/* Prediction Output Card */}
        <div className="fc-panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          {error && (
            <div style={{ color: '#f87171', background: 'rgba(239, 68, 68, 0.2)', padding: '0.75rem', borderRadius: '6px' }}>
              {error}
            </div>
          )}

          {!result && !error && (
            <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '2rem 1rem' }}>
              <Bot size={36} color="var(--color-text-muted)" style={{ margin: '0 auto 0.65rem' }} />
              <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--color-text)' }}>Awaiting Input Signals</h4>
              <p style={{ fontSize: '0.8rem', marginTop: '0.25rem', color: 'var(--text-muted)' }}>
                Configure parameters or pick a preset above to inspect the model's live classification.
              </p>
            </div>
          )}

          {result && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 700 }}>
                    Final Triage Severity Tier
                  </span>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    Source: <strong>{result.prediction_source || result.model_version}</strong> ({result.model_version || 'v2'})
                  </div>
                </div>
                <span className={`badge ${
                  result.severity_level === 'CRITICAL' ? 'badge-critical' :
                  result.severity_level === 'HIGH' ? 'badge-high' :
                  result.severity_level === 'MEDIUM' ? 'badge-medium' : 'badge-low'
                }`} style={{ fontSize: '0.95rem', padding: '0.3rem 0.85rem' }}>
                  {result.severity_level}
                </span>
              </div>

              {/* Phase 5D: Distinct Separation of Learned ML Model vs Deterministic Safety Rules */}
              <div style={{
                background: result.safety_override_applied ? 'rgba(239, 68, 68, 0.12)' : 'rgba(56, 189, 248, 0.08)',
                border: result.safety_override_applied ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(56, 189, 248, 0.25)',
                borderRadius: '6px',
                padding: '0.6rem 0.8rem',
                marginBottom: '0.85rem',
                fontSize: '0.75rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.4rem' }}>
                  <span style={{ color: 'var(--color-text)' }}>
                    <strong>Learned ML Prediction:</strong>{' '}
                    <span style={{ color: 'var(--color-primary)', fontWeight: 700 }}>
                      {result.raw_model_prediction || result.severity_level}
                    </span>
                    {result.raw_model_confidence != null ? ` (${Math.round(result.raw_model_confidence * 100)}% raw prob)` : ''}
                  </span>
                  <span style={{
                    fontSize: '0.68rem',
                    padding: '0.1rem 0.45rem',
                    borderRadius: '4px',
                    background: result.safety_override_applied ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.15)',
                    color: result.safety_override_applied ? '#fca5a5' : '#34d399',
                    fontWeight: 700
                  }}>
                    {result.safety_override_applied ? '⚡ SAFETY RULE OVERRIDE APPLIED' : '✓ PURE ML CLASSIFIER'}
                  </span>
                </div>
                {result.safety_override_applied && result.safety_override_reason && (
                  <div style={{ color: '#fca5a5', fontSize: '0.72rem', marginTop: '0.3rem' }}>
                    <strong>Deterministic Override Reason:</strong> {result.safety_override_reason}
                  </div>
                )}
              </div>

              {/* Conflict Warning Alert Banner */}
              {result.has_conflicts && result.conflict_warnings?.length > 0 && (
                <div style={{
                  background: 'rgba(245, 158, 11, 0.12)',
                  border: '1px solid rgba(245, 158, 11, 0.4)',
                  borderRadius: '6px',
                  padding: '0.65rem 0.85rem',
                  marginBottom: '0.85rem'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#fbbf24', fontSize: '0.78rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                    <AlertTriangle size={14} /> Vital Sign Discrepancy Detected
                  </div>
                  <ul style={{ paddingLeft: '1.2rem', color: '#fef3c7', fontSize: '0.75rem', margin: 0 }}>
                    {result.conflict_warnings.map((cw, i) => (
                      <li key={i}>{cw}</li>
                    ))}
                  </ul>
                  <div style={{ fontSize: '0.68rem', color: '#fcd34d', marginTop: '0.3rem' }}>
                    Safety Policy: Critical structured flags take precedence over conflicting free-text claims.
                  </div>
                </div>
              )}

              {/* Confidence Gauge */}
              <div style={{ marginBottom: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.35rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Model Output Certainty*</span>
                  <strong style={{ color: 'var(--color-text)' }}>{result.confidence_percentage}%</strong>
                </div>
                <div style={{ height: '7px', background: 'var(--bg-primary)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${result.confidence_percentage}%`,
                      background: result.severity_level === 'CRITICAL' ? '#ef4444' :
                                  result.severity_level === 'HIGH' ? '#f97316' :
                                  result.severity_level === 'MEDIUM' ? '#f59e0b' : '#10b981'
                    }}
                  />
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
                  *Statistical output from synthetic training scenarios. Decision support only — not clinically validated diagnostic accuracy.
                </div>
              </div>

              {/* NLP Extracted Concepts & Negations */}
              {((result.extracted_concepts && result.extracted_concepts.length > 0) || (result.negated_concepts && result.negated_concepts.length > 0)) && (
                <div style={{
                  background: 'var(--bg-primary)',
                  padding: '0.65rem 0.8rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-subtle)',
                  marginBottom: '0.85rem'
                }}>
                  <div style={{ color: '#38bdf8', fontSize: '0.75rem', fontWeight: 700, marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <FileText size={12} /> NLP Context Extraction:
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                    {result.extracted_concepts?.map((c, idx) => (
                      <span key={`c-${idx}`} style={{
                        fontSize: '0.7rem',
                        padding: '0.15rem 0.45rem',
                        borderRadius: '4px',
                        background: 'rgba(56, 189, 248, 0.15)',
                        color: '#38bdf8',
                        border: '1px solid rgba(56, 189, 248, 0.3)'
                      }}>
                        + {c.replace(/_/g, ' ')}
                      </span>
                    ))}
                    {result.negated_concepts?.map((nc, idx) => (
                      <span key={`nc-${idx}`} style={{
                        fontSize: '0.7rem',
                        padding: '0.15rem 0.45rem',
                        borderRadius: '4px',
                        background: 'rgba(148, 163, 184, 0.12)',
                        color: '#94a3b8',
                        border: '1px solid rgba(148, 163, 184, 0.25)',
                        textDecoration: 'line-through'
                      }}>
                        negated: {nc.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Identified Risk Factors */}
              <div style={{
                background: 'var(--bg-primary)',
                padding: '0.75rem 0.85rem',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)',
                marginBottom: '0.85rem'
              }}>
                <div style={{ color: '#c084fc', fontSize: '0.78rem', fontWeight: 700, marginBottom: '0.35rem' }}>
                  Multi-Factor Evidence Factors:
                </div>
                <ul style={{ paddingLeft: '1.2rem', color: 'var(--color-text)', fontSize: '0.8rem', lineHeight: 1.5, margin: 0 }}>
                  {result.risk_factors.map((rf, idx) => (
                    <li key={idx}>{rf}</li>
                  ))}
                </ul>
              </div>

              {/* Recommended Action */}
              <div style={{
                background: 'var(--bg-secondary)',
                padding: '0.75rem 0.85rem',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)'
              }}>
                <div style={{ color: 'var(--color-primary)', fontSize: '0.78rem', fontWeight: 700, marginBottom: '0.2rem' }}>
                  Recommended Action Protocol:
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--color-text)', margin: 0 }}>
                  {result.recommended_action}
                </p>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
                  Model Artifact: {result.model_name} ({result.model_version || 'v2'})
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Phase 5D: Independent 40-Scenario Holdout Evaluation Benchmark Panel */}
      {benchmarkReport && (
        <div className="fc-panel" style={{ marginTop: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.85rem' }}>
            <div>
              <h3 style={{ fontSize: '0.98rem', fontWeight: 700, color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <BarChart3 size={17} color="var(--color-primary)" /> Independent Holdout Evaluation Benchmark ({benchmarkReport.total_scenarios} Unseen Scenarios)
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                Evaluated on hand-authored clinical &amp; bystander scenarios completely excluded from model training.
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              <span style={{
                fontSize: '0.75rem',
                padding: '0.25rem 0.65rem',
                borderRadius: '6px',
                background: 'rgba(56, 189, 248, 0.12)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                fontWeight: 700
              }}>
                Raw ML v2 Accuracy: {benchmarkReport.raw_ml_model_v2?.accuracy_pct}% (Macro F1: {benchmarkReport.raw_ml_model_v2?.macro_f1})
              </span>
              <span style={{
                fontSize: '0.75rem',
                padding: '0.25rem 0.65rem',
                borderRadius: '6px',
                background: 'rgba(16, 185, 129, 0.15)',
                color: '#34d399',
                border: '1px solid rgba(16, 185, 129, 0.35)',
                fontWeight: 700
              }}>
                Hybrid System Accuracy: {benchmarkReport.hybrid_system_ml_plus_safety_rules?.accuracy_pct}% (Macro F1: {benchmarkReport.hybrid_system_ml_plus_safety_rules?.macro_f1})
              </span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            {/* Per-Class Precision / Recall / F1 Table (Raw ML v2) */}
            <div style={{ background: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--color-primary)', marginBottom: '0.5rem' }}>
                Raw ML Classifier (v2 Alone) — Per-Class Metrics
              </div>
              <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse', color: 'var(--color-text)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--color-text-muted)', textAlign: 'left' }}>
                    <th style={{ padding: '0.3rem' }}>Class</th>
                    <th style={{ padding: '0.3rem' }}>Precision</th>
                    <th style={{ padding: '0.3rem' }}>Recall</th>
                    <th style={{ padding: '0.3rem' }}>F1</th>
                    <th style={{ padding: '0.3rem' }}>Support</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmarkReport.labels?.map((lbl) => {
                    const m = benchmarkReport.raw_ml_model_v2?.per_class?.[lbl] || {};
                    return (
                      <tr key={lbl} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.3rem', fontWeight: 700 }}>{lbl}</td>
                        <td style={{ padding: '0.3rem' }}>{m.precision}</td>
                        <td style={{ padding: '0.3rem' }}>{m.recall}</td>
                        <td style={{ padding: '0.3rem' }}>{m.f1}</td>
                        <td style={{ padding: '0.3rem' }}>{m.support}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Confusion Matrix (Raw ML v2) */}
            <div style={{ background: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#c084fc', marginBottom: '0.5rem' }}>
                Confusion Matrix (Raw ML Model v2 vs Hybrid Safety Layer)
              </div>
              <table style={{ width: '100%', fontSize: '0.74rem', borderCollapse: 'collapse', color: 'var(--color-text)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--color-text-muted)', textAlign: 'center' }}>
                    <th style={{ padding: '0.3rem', textAlign: 'left' }}>True \ Pred</th>
                    {benchmarkReport.labels?.map((l) => (
                      <th key={l} style={{ padding: '0.3rem' }}>{l.slice(0, 4)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {benchmarkReport.labels?.map((rowLbl) => (
                    <tr key={rowLbl} style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                      <td style={{ padding: '0.3rem', textAlign: 'left', fontWeight: 700 }}>{rowLbl}</td>
                      {benchmarkReport.labels?.map((colLbl) => {
                        const val = benchmarkReport.raw_ml_model_v2?.confusion_matrix?.[rowLbl]?.[colLbl] || 0;
                        const isDiag = rowLbl === colLbl;
                        return (
                          <td
                            key={colLbl}
                            style={{
                              padding: '0.3rem',
                              fontWeight: val > 0 ? 700 : 400,
                              color: isDiag && val > 0 ? '#34d399' : val > 0 ? '#f87171' : '#64748b'
                            }}
                          >
                            {val}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.45rem' }}>
                Safety overrides triggered on {benchmarkReport.safety_overrides_count} holdout case(s) where structured life-safety flags overrode lower raw ML probabilities.
              </div>
            </div>
          </div>

          {benchmarkReport.limitations_disclosure && (
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Info size={12} color="#38bdf8" />
              <span><strong>Model Limitations Disclosure:</strong> {benchmarkReport.limitations_disclosure}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

