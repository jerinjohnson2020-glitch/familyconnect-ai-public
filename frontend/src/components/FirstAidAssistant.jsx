import React, { useState, useRef, useEffect } from 'react';
import {
  BookOpen,
  Send,
  AlertTriangle,
  ExternalLink,
  PhoneCall,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RefreshCw,
  Info,
  Clock,
  Sparkles,
  ChevronRight,
  MessageSquare,
  User,
  Bot,
  HeartPulse,
  Flame,
  Droplets,
  Activity
} from 'lucide-react';
import { queryFirstAid } from '../services/api';

const ALL_EMERGENCY_TOPICS = [
  { label: 'Adult CPR & AED', query: 'how to perform adult CPR and use an AED', icon: <HeartPulse size={15} color="#ef4444" />, desc: 'Chest compressions, airway & AED protocol' },
  { label: 'Choking (Heimlich)', query: 'what to do if someone is choking on food', icon: <Activity size={15} color="#f59e0b" />, desc: 'Back blows & abdominal thrusts' },
  { label: 'Severe Bleeding', query: 'how to stop severe arterial bleeding with a tourniquet', icon: <Droplets size={15} color="#dc2626" />, desc: 'Pressure, packing & tourniquet' },
  { label: 'Burns & Scalds', query: 'first aid for boiling water scald burn on skin', icon: <Flame size={15} color="#f97316" />, desc: 'Cool running water protocol' },
  { label: 'Stroke (F.A.S.T.)', query: 'face drooping arm weakness stroke signs FAST', icon: <AlertTriangle size={15} color="#8b5cf6" />, desc: 'Facial droop, arm weakness & speech check' },
  { label: 'Active Seizure', query: 'first aid for person having violent convulsions and seizure', icon: <Activity size={15} color="#06b6d4" />, desc: 'Protect head, recovery position & safety' },
  { label: 'Anaphylaxis (EpiPen)', query: 'severe allergic reaction swollen tongue epinephrine epipen', icon: <AlertTriangle size={15} color="#ec4899" />, desc: 'Epinephrine auto-injector & airway check' },
  { label: 'Heart Attack Signs', query: 'crushing chest pain radiating to left arm heart attack warning signs', icon: <HeartPulse size={15} color="#e11d48" />, desc: 'Chest pain, emergency positioning & aspirin rule' },
  { label: 'Fractures & Splints', query: 'first aid for broken bone compound fracture with bone exposed', icon: <AlertTriangle size={15} color="#64748b" />, desc: 'Immobilization & open fracture support' },
  { label: 'Heatstroke vs Exhaustion', query: 'heatstroke high fever confusion in hot sun cooling protocol', icon: <Flame size={15} color="#d97706" />, desc: 'Rapid active cooling & hydration guard' }
];

const FOLLOW_UP_SUGGESTIONS = {
  cpr_adult_aed: [
    { label: 'How deep to push?', query: 'How deep should I push?' },
    { label: 'Compression rate?', query: 'How fast should I compress?' },
    { label: 'For an infant or child?', query: 'What about an infant or child?' },
    { label: 'When to use AED?', query: 'When should I use the AED?' }
  ],
  choking_adult_child: [
    { label: 'For an infant under 1 year?', query: 'What about an infant under 1 year?' },
    { label: 'If they pass out?', query: 'What if the choking person becomes unconscious?' },
    { label: 'Back blows vs thrusts?', query: 'How to alternate back blows and abdominal thrusts?' }
  ],
  severe_bleeding_hemorrhage: [
    { label: 'How to apply tourniquet?', query: 'How to apply a tourniquet properly?' },
    { label: 'Should I remove knife?', query: 'Should I remove an embedded object from the wound?' },
    { label: 'If blood soaks through?', query: 'What if blood soaks through the bandage?' }
  ],
  burns_thermal_chemical: [
    { label: 'Can I use ice or butter?', query: 'Can I apply ice or butter to the burn?' },
    { label: 'How long to cool with water?', query: 'How long should I keep the burn under water?' },
    { label: 'Chemical burn steps?', query: 'How to treat a chemical burn on skin?' }
  ]
};

const NATURAL_TOPIC_INTRODUCTIONS = {
  cpr_adult_aed: "Here is the emergency adult CPR and AED procedure. If the person is unresponsive and not breathing normally, begin chest compressions immediately.",
  choking_adult_child: "Here is the emergency procedure for a choking adult or child. Act quickly to clear the airway using back blows and abdominal thrusts.",
  severe_bleeding_hemorrhage: "Here is the critical emergency protocol for severe bleeding. Apply firm, continuous direct pressure to the wound immediately.",
  burns_thermal_chemical: "Here is the clinical first-aid protocol for thermal and chemical burns. Cool the burn immediately under cool, gentle running water for at least 20 minutes.",
  stroke_fast_protocol: "Here is the F.A.S.T. stroke assessment protocol. Stroke is a time-critical emergency — every minute counts.",
  seizure_first_aid: "Here is the emergency guidance for an active seizure. Focus on protecting the person from injury and keeping their airway clear.",
  anaphylaxis_epinephrine: "Here is the emergency protocol for severe allergic reaction and anaphylaxis. Administer an epinephrine auto-injector immediately if available.",
  cardiac_chest_pain_heart_attack: "Here is the emergency protocol for suspected heart attack or acute chest pain. Keep the patient calm, seated, and call emergency services immediately.",
  fractures_sprains_trauma: "Here is the first-aid guidance for suspected fractures, dislocations, or sprains. Support and immobilize the injured area in the position found.",
  heatstroke_exhaustion: "Here is the emergency cooling protocol for heat exhaustion and heatstroke. Move the person to a cool area and initiate active cooling immediately."
};

export default function FirstAidAssistant() {
  const [queryText, setQueryText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [activeProtocolId, setActiveProtocolId] = useState(null);
  const [showAllTopics, setShowAllTopics] = useState(false);

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  };

  useEffect(() => {
    if (messages.length > 0 || loading) {
      scrollToBottom();
      const timer = setTimeout(scrollToBottom, 60);
      return () => clearTimeout(timer);
    }
  }, [messages, loading]);

  const handleSendMessage = async (customPrompt = null) => {
    const textToSend = (customPrompt !== null ? customPrompt : queryText).trim();
    if (!textToSend || loading) return;

    setLoading(true);
    setError(null);

    const userMessage = {
      role: 'user',
      content: textToSend,
      timestamp: Date.now()
    };

    const nextHistory = [...messages, userMessage];
    setMessages(nextHistory);
    setQueryText('');

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const data = await queryFirstAid(textToSend, {
        conversationHistory: nextHistory,
        activeProtocolId: activeProtocolId
      });

      if (data.status === 'SUCCESS') {
        const protoId = data.matched_protocol?.protocol_id || null;
        setActiveProtocolId(protoId);

        let assistantText = data.conversational_reply;
        if (!assistantText) {
          if (data.is_follow_up) {
            assistantText = `Regarding your follow-up on ${data.matched_protocol?.topic || 'this condition'}: Here is the specific verified guidance:`;
          } else if (protoId && NATURAL_TOPIC_INTRODUCTIONS[protoId]) {
            assistantText = NATURAL_TOPIC_INTRODUCTIONS[protoId];
          } else {
            assistantText = `Here is the verified emergency first-aid procedure for ${data.matched_protocol?.topic || 'this condition'}:`;
          }
        }

        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: assistantText,
            conversationalReply: assistantText,
            isFollowUp: data.is_follow_up || false,
            data: data,
            timestamp: Date.now()
          }
        ]);
      } else if (data.status === 'INSUFFICIENT_EVIDENCE') {
        const fallbackText = data.message || 'No verified first-aid guidance in our curated medical protocols matched your query with sufficient confidence.';
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: fallbackText,
            conversationalReply: fallbackText,
            isInsufficient: true,
            data: data,
            timestamp: Date.now()
          }
        ]);
      }
    } catch (err) {
      setError(err.message || 'Failed to retrieve first-aid guidance. Please check your connection and try again.');
    } finally {
      setLoading(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleTextareaInput = (e) => {
    setQueryText(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  const handleNewConversation = () => {
    setQueryText('');
    setMessages([]);
    setActiveProtocolId(null);
    setError(null);
    setShowAllTopics(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  };

  const displayedWelcomePrompts = showAllTopics ? ALL_EMERGENCY_TOPICS : ALL_EMERGENCY_TOPICS.slice(0, 4);
  const currentSuggestions = activeProtocolId && FOLLOW_UP_SUGGESTIONS[activeProtocolId]
    ? FOLLOW_UP_SUGGESTIONS[activeProtocolId]
    : [];

  return (
    <div className="first-aid-container chat-mode" data-testid="first-aid-container">
      {/* Compact Chat Header */}
      <header className="chat-header" data-testid="chat-header">
        <div className="chat-header-brand">
          <div className="chat-header-icon" aria-hidden="true">
            <Bot size={22} color="var(--color-primary)" />
          </div>
          <div className="chat-header-titles">
            <div className="chat-header-title-row">
              <h2>AI First Aid Guide</h2>
              <span className="chat-status-pill online" title="Verified against MoHFW, ICMR, Indian Red Cross, WHO & AHA">
                <span className="status-dot"></span>
                <span>Evidence-Grounded RAG</span>
              </span>
            </div>
            <p className="chat-header-subtitle">
              Instant clinical protocols &bull; India 112/108 Integrated
            </p>
          </div>
        </div>

        <div className="chat-header-actions">
          {/* Compact India Emergency Access */}
          <div className="compact-emergency-access" aria-label="Emergency Response Numbers">
            <a href="tel:112" className="compact-call-btn danger" title="Call 112 Pan-India Emergency (National Emergency Number)">
              <PhoneCall size={12} />
              <span>Call 112</span>
            </a>
            <a href="tel:108" className="compact-call-btn ambulance" title="Call 108 Ambulance (e.g. KANIV 108 in Kerala; availability depends on locality)">
              <PhoneCall size={12} />
              <span>Call 108</span>
            </a>
          </div>

          <button
            type="button"
            onClick={handleNewConversation}
            className="first-aid-new-chat-btn"
            data-testid="first-aid-new-chat-btn"
            title="Start a new conversation"
          >
            <RefreshCw size={13} />
            <span>New Chat</span>
          </button>
        </div>
      </header>

      {/* Scrollable Conversation Viewport */}
      <main className="chat-messages-viewport first-aid-chat-thread" data-testid="first-aid-chat-thread">
        <div className="chat-thread-inner">
        {/* Welcome Empty State (Centered when no messages) */}
        {messages.length === 0 && !loading && (
          <div className="chat-welcome-state first-aid-empty-state" data-testid="first-aid-welcome-state">
            <div className="welcome-avatar">
              <Sparkles size={28} color="var(--color-primary)" />
            </div>
            <h3 className="welcome-title">How can I help you?</h3>
            <p className="welcome-subtitle">
              Ask any emergency medical symptom or first-aid question. Guidance is retrieved from verified Indian and international emergency health authorities (MoHFW, ICMR, Indian Red Cross, NDMA, WHO, AHA) with full source citations.
            </p>

            {/* Compact Clickable Suggestion Prompts */}
            <div className="welcome-prompts-grid" aria-label="Common Emergency Situations">
              {displayedWelcomePrompts.map((topic) => (
                <button
                  key={topic.label}
                  type="button"
                  className="welcome-prompt-card"
                  onClick={() => handleSendMessage(topic.query)}
                  data-testid={`topic-pill-${topic.label.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
                >
                  <div className="prompt-header">
                    <span className="prompt-icon">{topic.icon}</span>
                    <strong className="prompt-label">{topic.label}</strong>
                  </div>
                  <p className="prompt-desc">{topic.desc}</p>
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <button
                type="button"
                className="welcome-toggle-topics-btn"
                onClick={() => setShowAllTopics(!showAllTopics)}
              >
                {showAllTopics ? 'Show fewer emergency topics' : 'Show all 10 curated emergency topics'}
              </button>
            </div>

            <div className="welcome-emergency-reminder india-emergency-banner">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <PhoneCall size={15} color="var(--color-danger)" style={{ flexShrink: 0 }} />
                <span>
                  For acute distress, call <strong style={{ color: '#ffffff', background: 'var(--color-danger)', padding: '0.05rem 0.35rem', borderRadius: '4px' }}>112</strong> or <strong style={{ color: '#ffffff', background: '#b45309', padding: '0.05rem 0.35rem', borderRadius: '4px' }}>108</strong> (Ambulance, e.g. KANIV 108 in Kerala; availability depends on locality) immediately.
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Conversation Message Exchanges */}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`chat-message-row ${msg.role}`}
            data-testid={`message-row-${idx}`}
          >
            {msg.role === 'assistant' && (
              <div className="chat-avatar assistant" aria-hidden="true">
                <Bot size={18} />
              </div>
            )}

            <div className={`chat-bubble ${msg.role}`}>
              <div className="chat-bubble-header">
                <span className="chat-author-name">
                  {msg.role === 'user' ? 'You' : 'First Aid Assistant'}
                </span>
                {msg.isFollowUp && (
                  <span className="first-aid-followup-badge">
                    Follow-up
                  </span>
                )}
              </div>

              <div className="chat-bubble-text">
                {msg.conversationalReply || msg.content}
              </div>

              {/* Embedded Structured Guidance Card */}
              {msg.data && msg.data.status === 'SUCCESS' && (
                <article className="embedded-protocol-card first-aid-result-card" data-testid="first-aid-result-card">
                  <div className="protocol-meta-bar">
                    <span className="first-aid-category-badge">{msg.data.matched_protocol?.category}</span>
                    <strong className="protocol-topic-title">{msg.data.matched_protocol?.topic}</strong>
                    {msg.data.relevance_score && (
                      <span className="first-aid-score-badge">Verified Guidance</span>
                    )}
                    {msg.data.synthesized_explanation ? (
                      <span className="first-aid-ai-status-badge success" data-testid="ai-status-badge">
                        <Sparkles size={11} style={{ marginRight: '0.2rem' }} />
                        Local AI explanation available
                      </span>
                    ) : msg.data.llm_status === 'TIMEOUT' ? (
                      <span className="first-aid-ai-status-badge warning" data-testid="ai-status-badge">
                        <Clock size={11} style={{ marginRight: '0.2rem' }} />
                        AI Timeout — Using verified guidance only
                      </span>
                    ) : (
                      <span className="first-aid-ai-status-badge neutral" data-testid="ai-status-badge">
                        <BookOpen size={11} style={{ marginRight: '0.2rem' }} />
                        Using verified guidance only
                      </span>
                    )}
                  </div>

                  {/* Immediate Emergency Call Directive */}
                  <div
                    className="first-aid-call-guidance-box"
                    role="region"
                    aria-label="Emergency Call Instructions"
                    style={{
                      background: 'var(--color-danger-soft)',
                      border: '1px solid var(--color-danger)',
                      borderRadius: '8px',
                      padding: '0.85rem 1rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.45rem'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <PhoneCall size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
                      <strong style={{ color: 'var(--color-danger)', fontSize: '0.88rem' }}>
                        Emergency Safety Directive — When to Call Emergency Services
                      </strong>
                    </div>

                    <p style={{ margin: '0.15rem 0', fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.45 }}>
                      {msg.data.emergency_call_guidance || 'If the patient is unconscious, unresponsive, experiencing acute chest pain, severe bleeding, or difficulty breathing, call emergency services immediately.'}
                    </p>

                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      flexWrap: 'wrap',
                      paddingTop: '0.45rem',
                      borderTop: '1px solid rgba(239, 68, 68, 0.25)'
                    }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                        India Emergency Dialing:
                      </span>
                      <a
                        href="tel:112"
                        className="call-emergency-btn"
                        title="Call 112 Pan-India Emergency (National Emergency Number)"
                        style={{ fontSize: '0.76rem', padding: '0.35rem 0.65rem' }}
                      >
                        <PhoneCall size={12} />
                        <span>Call 112 (National Emergency Number)</span>
                      </a>
                      <a
                        href="tel:108"
                        className="call-emergency-btn"
                        title="Call 108 Ambulance Service (e.g. KANIV 108)"
                        style={{ background: '#b45309', color: '#ffffff', fontSize: '0.76rem', padding: '0.35rem 0.65rem' }}
                      >
                        <PhoneCall size={12} />
                        <span>Call 108 (Ambulance Service)</span>
                      </a>
                    </div>
                  </div>

                  {/* Critical Safety Warnings */}
                  {msg.data.critical_warnings && msg.data.critical_warnings.length > 0 && (
                    <div className="first-aid-warnings-box" role="region" aria-label="Critical Warnings">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.35rem' }}>
                        <AlertTriangle size={15} color="#f59e0b" style={{ flexShrink: 0 }} />
                        <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#fbbf24', margin: 0 }}>
                          Critical Safety Warnings &amp; Red Flags
                        </h4>
                      </div>
                      <ul className="first-aid-warnings-list">
                        {msg.data.critical_warnings.map((warn, wIdx) => (
                          <li key={wIdx}>{warn}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Actionable Steps */}
                  {msg.data.actionable_steps && msg.data.actionable_steps.length > 0 && (
                    <div className="first-aid-steps-section" role="region" aria-label="Actionable Steps">
                      <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#f8fafc', marginBottom: '0.55rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={16} color="#34d399" />
                        <span>Actionable Step-by-Step Procedure</span>
                      </h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
                        {msg.data.actionable_steps.map((step, sIdx) => (
                          <div key={sIdx} className="first-aid-step-item">
                            <span className="first-aid-step-num">{sIdx + 1}</span>
                            <span className="first-aid-step-body">{step.replace(/^\d+\.\s*/, '')}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* What NOT to Do */}
                  {msg.data.what_not_to_do && msg.data.what_not_to_do.length > 0 && (
                    <div className="first-aid-contraindications-box" role="region" aria-label="What NOT to Do">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.35rem' }}>
                        <XCircle size={15} color="#f87171" style={{ flexShrink: 0 }} />
                        <h4 style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f87171', margin: 0 }}>
                          What NOT To Do (Dangerous Mistakes)
                        </h4>
                      </div>
                      <ul style={{ margin: '0.25rem 0 0 1.2rem', padding: 0, fontSize: '0.82rem', lineHeight: 1.45 }}>
                        {msg.data.what_not_to_do.map((item, cIdx) => (
                          <li key={cIdx}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Optional AI Grounded Summary */}
                  {msg.data.synthesized_explanation ? (() => {
                    const result = msg.data;
                    return (
                      <div className="first-aid-llm-summary-box" role="region" aria-label="AI Grounded Summary" data-testid="first-aid-llm-summary">
                        <div className="first-aid-llm-summary-header">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                            <Sparkles size={14} color="var(--color-primary)" />
                            <strong style={{ fontSize: '0.86rem', color: 'var(--color-text)' }}>
                              AI Grounded Summary (Supplementary)
                            </strong>
                            <span className="first-aid-llm-badge">
                              {result.llm_model || 'llama3.2:3b'} (Local CPU)
                            </span>
                            {result.llm_latency_ms !== undefined && result.llm_latency_ms !== null && (
                              <span className="first-aid-latency-pill">
                                <Clock size={10} style={{ marginRight: '0.2rem' }} />
                                {result.llm_latency_ms} ms
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="first-aid-llm-summary-text">
                          {result.synthesized_explanation}
                        </p>
                        <div className="first-aid-llm-summary-footer">
                          <Info size={12} style={{ flexShrink: 0 }} />
                          <span>
                            Supplementary AI summary synthesized locally from retrieved guideline evidence. Never overrides emergency instructions and is not a substitute for verified guidance. Always follow the verified clinical procedure above.
                          </span>
                        </div>
                      </div>
                    );
                  })() : msg.data.llm_status === 'TIMEOUT' ? (
                    <div className="first-aid-llm-fallback-note timeout" role="note" aria-label="Local AI Synthesis Timeout Notice" data-testid="first-aid-llm-timeout-note">
                      <Clock size={15} color="#f59e0b" style={{ flexShrink: 0 }} />
                      <div>
                        <strong style={{ color: '#f59e0b' }}>Local AI synthesis timed out.</strong>
                        <span style={{ marginLeft: '0.35rem', color: 'var(--color-text)' }}>
                          Displaying authoritative clinical instructions directly from verified health guidelines above.
                        </span>
                      </div>
                    </div>
                  ) : msg.data.llm_status === 'OFFLINE' ? (
                    <div className="first-aid-llm-fallback-note offline" role="note" aria-label="Local AI Offline Notice" data-testid="first-aid-llm-offline-note">
                      <Info size={15} color="var(--color-primary)" style={{ flexShrink: 0 }} />
                      <div>
                        <strong style={{ color: 'var(--color-primary)' }}>Local AI service offline (Ollama).</strong>
                        <span style={{ marginLeft: '0.35rem', color: 'var(--color-text)' }}>
                          Displaying authoritative clinical instructions directly from verified health guidelines above.
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="first-aid-llm-fallback-note" role="note" aria-label="Verified Protocol Direct Guidance">
                      <Info size={14} color="var(--color-primary)" style={{ flexShrink: 0 }} />
                      <span>
                        Using verified guidance only — displaying authoritative clinical instructions directly from cited health guidelines.
                      </span>
                    </div>
                  )}

                  {/* Evidence Drawer and Source Provenance */}
                  <details className="first-aid-evidence-drawer">
                    <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: '0.8rem', color: 'var(--color-primary)' }}>
                      View Retrieved Evidence Excerpts ({msg.data.evidence_chunks?.length || 0}) &amp; Source Provenance
                    </summary>
                    <div style={{ marginTop: '0.55rem', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                      {msg.data.evidence_chunks?.map((ch) => (
                        <div key={ch.chunk_id} className="first-aid-evidence-text">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                            <strong style={{ fontSize: '0.78rem', color: 'var(--color-primary)' }}>{ch.title}</strong>
                            <span style={{ fontSize: '0.68rem', color: 'var(--color-text-muted)' }}>
                              Sim: {(ch.similarity_score * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div style={{ fontSize: '0.78rem' }}>"{ch.evidence_text}"</div>
                        </div>
                      ))}

                      {msg.data.source_citation && (
                        <div className="first-aid-source-citation-card" data-testid="first-aid-source-citation">
                          <div className="first-aid-source-header">
                            <span className="first-aid-org-tag badge">{msg.data.source_citation.organization}</span>
                          </div>
                          <div className="first-aid-source-body" style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
                            <div>Document: {msg.data.source_citation.document_title}</div>
                          </div>
                          {msg.data.source_citation.url && (
                            <div style={{ marginTop: '0.25rem' }}>
                              <a
                                href={msg.data.source_citation.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="first-aid-source-link"
                              >
                                <span>{msg.data.source_citation.url}</span>
                                <ExternalLink size={11} style={{ marginLeft: '0.2rem' }} />
                              </a>
                            </div>
                          )}
                          <div className="first-aid-source-footer" style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                            Reviewed: {msg.data.source_citation.published_or_reviewed_date || 'Current'} &bull; Accessed: {msg.data.source_citation.accessed_date || '2026-10-26'}
                          </div>
                        </div>
                      )}
                    </div>
                  </details>
                </article>
              )}

              {/* Insufficient Evidence Fallback inside Message */}
              {msg.data && msg.data.status === 'INSUFFICIENT_EVIDENCE' && (
                <div className="first-aid-fallback-card" data-testid="first-aid-insufficient-evidence" style={{ marginTop: '0.65rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fbbf24', fontWeight: 700, fontSize: '0.88rem' }}>
                    <HelpCircle size={16} />
                    <span>No verified protocol found matching that exact query</span>
                  </div>
                  <p style={{ margin: '0.35rem 0', fontSize: '0.82rem', color: 'var(--color-text)', lineHeight: 1.45 }}>
                    {msg.data.message || 'The retrieval assistant could not match your query with high confidence against our curated first-aid protocol database.'}
                  </p>
                  <div className="india-emergency-banner" style={{ marginTop: '0.45rem', padding: '0.5rem 0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                      <PhoneCall size={14} color="var(--color-danger)" />
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>
                        If someone is in acute distress, call <strong>112</strong> or <strong>108</strong> immediately.
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.35rem' }}>
                      <a href="tel:112" className="call-emergency-btn" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
                        Call 112
                      </a>
                      <a href="tel:108" className="call-emergency-btn" style={{ background: '#b45309', color: '#ffffff', fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
                        Call 108
                      </a>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Loading / Searching State */}
        {loading && (
          <div className="chat-message-row assistant" data-testid="first-aid-loading">
            <div className="chat-avatar assistant">
              <Bot size={18} />
            </div>
            <div className="chat-bubble assistant loading-bubble first-aid-loading-state">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <span className="loading-text" style={{ fontWeight: 700 }}>Searching medical protocols...</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Retrieving guidelines &amp; local AI (llama3.2:3b) synthesis</span>
            </div>
          </div>
        )}

        {/* Error Banner with Retry */}
        {error && (
          <div className="first-aid-error-banner" role="alert" data-testid="first-aid-error-banner" style={{ margin: '0.5rem 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={16} color="#ef4444" style={{ flexShrink: 0 }} />
              <span style={{ fontSize: '0.825rem' }}>{error}</span>
            </div>
            <button
              type="button"
              className="first-aid-retry-btn"
              onClick={() => handleSendMessage()}
            >
              <RefreshCw size={12} /> Retry
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Sticky Bottom Chat Composer */}
      <footer className="chat-composer-footer" data-testid="chat-composer-container">
        <div className="chat-composer-inner">
          {/* Contextual Follow-up Chips */}
          {currentSuggestions.length > 0 && !loading && (
            <div className="composer-suggestions-bar" aria-label="Suggested Follow-up Questions">
              <span className="suggestions-label">Suggested follow-ups:</span>
              <div className="suggestions-chips-scroll">
                {currentSuggestions.map((s, sIdx) => (
                  <button
                    key={sIdx}
                    type="button"
                    className="composer-suggestion-chip"
                    onClick={() => handleSendMessage(s.query)}
                    disabled={loading}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Composer Form with Multiline Textarea and Send Button */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="chat-composer-form first-aid-search-form"
          >
            <div className="composer-input-wrapper first-aid-input-wrapper">
              <textarea
                ref={textareaRef}
                rows={1}
                className="composer-textarea first-aid-search-input"
                value={queryText}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder={activeProtocolId ? "Ask a follow-up (e.g. How deep to push? What about an infant?)..." : "Ask any emergency first-aid question (e.g. How do I perform CPR on an adult?)..."}
                maxLength={500}
                disabled={loading}
                aria-label="First aid query input"
                data-testid="first-aid-input"
              />
              <button
                type="submit"
                className="composer-send-btn first-aid-submit-btn"
                disabled={loading || !queryText.trim()}
                data-testid="first-aid-submit-btn"
                aria-label="Send message"
                title="Send message (Enter)"
              >
                {loading ? (
                  <RefreshCw size={16} className="spin-animation" />
                ) : (
                  <Send size={18} color={!queryText.trim() ? '#64748b' : '#ffffff'} strokeWidth={2.2} />
                )}
              </button>
            </div>
          </form>

          {/* Mandatory Clinical Disclaimer */}
          <div className="chat-composer-disclaimer first-aid-result-disclaimer" data-testid="first-aid-disclaimer">
            <Info size={12} style={{ flexShrink: 0, marginTop: '0.1rem' }} color="var(--color-text-muted)" />
            <span>
              <strong>Clinical Disclaimer:</strong> FamilyConnect AI First Aid Guide provides evidence-retrieved first-aid assistance from cited clinical guidelines. It does not constitute professional medical diagnosis or care and does not replace emergency medical services or clinical judgment. In an acute emergency, always dial 112/108 immediately.
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
