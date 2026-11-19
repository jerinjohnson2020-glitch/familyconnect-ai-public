import React, { useState } from 'react';
import {
  Clock,
  MapPin,
  UserCheck,
  CheckCircle2,
  PhoneCall,
  Bot,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ShieldAlert,
  Navigation,
  Bell,
  Check,
  FileText,
  Truck,
  MapPinned,
  AlertTriangle,
  Info
} from 'lucide-react';
import { updateEmergencyStatus, acknowledgeAlert, retryIncidentAlert, updateAssignmentStatus } from '../services/api';
import IncidentProximityMap from './IncidentProximityMap';
import { isDemoEntity, maskPhoneNumber, maskEmail } from '../utils/privacyMask';
import { getIncidentDisplayMessage } from '../utils/incidentMessage';

export { getIncidentDisplayMessage };

export default function EmergencyMonitor({
  emergencies,
  onRefresh,
  loading,
  onOpenSos,
  allResponders = [],
  user = null
}) {
  const [filter, setFilter] = useState('ALL');
  // Disclosures collapsed by default for glanceable compact layout
  const [expandedTriage, setExpandedTriage] = useState({});
  const [expandedResponders, setExpandedResponders] = useState({});
  const [expandedMap, setExpandedMap] = useState({});
  const [expandedTimeline, setExpandedTimeline] = useState({});
  const [expandedAlerts, setExpandedAlerts] = useState({});

  const [updatingId, setUpdatingId] = useState(null);
  const [updatingAssignmentId, setUpdatingAssignmentId] = useState(null);
  const [acknowledgingId, setAcknowledgingId] = useState(null);
  const [retryingAlertId, setRetryingAlertId] = useState(null);

  // Resolution Notes Modal State
  const [resolvingIncident, setResolvingIncident] = useState(null);
  const [resolutionNotesInput, setResolutionNotesInput] = useState('');
  const [resolutionError, setResolutionError] = useState('');

  const handleAssignmentTransition = async (assignmentId, newStatus) => {
    setUpdatingAssignmentId(assignmentId);
    try {
      await updateAssignmentStatus(assignmentId, newStatus);
      await onRefresh();
    } catch (err) {
      alert(`Error updating assignment: ${err.message}`);
    } finally {
      setUpdatingAssignmentId(null);
    }
  };

  const toggleTriage = (id) => setExpandedTriage(prev => ({ ...prev, [id]: !prev[id] }));
  const toggleResponders = (id) => setExpandedResponders(prev => ({ ...prev, [id]: !prev[id] }));
  const toggleMap = (id) => setExpandedMap(prev => ({ ...prev, [id]: !prev[id] }));
  const toggleTimeline = (id) => setExpandedTimeline(prev => ({ ...prev, [id]: !prev[id] }));
  const toggleAlerts = (id) => setExpandedAlerts(prev => ({ ...prev, [id]: !prev[id] }));

  const handleStatusChange = async (incidentId, newStatus) => {
    if (newStatus === 'RESOLVED') {
      const inc = emergencies.find(e => e.id === incidentId);
      setResolvingIncident(inc);
      setResolutionNotesInput('');
      setResolutionError('');
      return;
    }

    setUpdatingId(incidentId);
    try {
      await updateEmergencyStatus(incidentId, newStatus);
      await onRefresh();
    } catch (err) {
      alert(`Error updating status: ${err.message}`);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleConfirmResolve = async (e) => {
    e.preventDefault();
    if (!resolvingIncident) return;

    setUpdatingId(resolvingIncident.id);
    setResolutionError('');
    try {
      await updateEmergencyStatus(
        resolvingIncident.id,
        'RESOLVED',
        resolutionNotesInput.trim() || 'Emergency incident resolved and confirmed safe.'
      );
      setResolvingIncident(null);
      await onRefresh();
    } catch (err) {
      setResolutionError(err.message || 'Failed to resolve incident');
    } finally {
      setUpdatingId(null);
    }
  };

  const handleAcknowledgeAlert = async (incidentId, alertId) => {
    setAcknowledgingId(alertId);
    try {
      await acknowledgeAlert(incidentId, alertId);
      await onRefresh();
    } catch (err) {
      alert(`Error acknowledging alert: ${err.message}`);
    } finally {
      setAcknowledgingId(null);
    }
  };

  const handleRetryAlert = async (incidentId, alertId) => {
    setRetryingAlertId(alertId);
    try {
      await retryIncidentAlert(incidentId, alertId);
      await onRefresh();
    } catch (err) {
      alert(`Error retrying alert delivery: ${err.message}`);
    } finally {
      setRetryingAlertId(null);
    }
  };

  const getSeverityBadge = (level) => {
    switch (level?.toUpperCase()) {
      case 'CRITICAL':
        return <span className="badge badge-critical">Critical</span>;
      case 'HIGH':
        return <span className="badge badge-high">High</span>;
      case 'MEDIUM':
        return <span className="badge badge-medium">Medium</span>;
      case 'LOW':
        return <span className="badge badge-low">Low</span>;
      default:
        return <span className="badge badge-medium">{level}</span>;
    }
  };

  const getStatusBadge = (status) => {
    switch (status?.toUpperCase()) {
      case 'ACTIVE':
        return <span className="badge badge-active">Active</span>;
      case 'RESPONDING':
        return <span className="badge badge-responding">Responding</span>;
      case 'RESOLVED':
        return <span className="badge badge-resolved">Resolved</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  const getResponderStatusBadge = (status) => {
    switch (status?.toUpperCase()) {
      case 'ASSIGNED':
      case 'RECOMMENDED':
        return (
          <span style={{
            fontSize: '0.68rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            background: 'var(--color-primary-soft)',
            color: 'var(--color-primary)',
            border: '1px solid var(--color-primary)',
            fontWeight: 700
          }}>
            ASSIGNED
          </span>
        );
      case 'ACCEPTED':
        return (
          <span style={{
            fontSize: '0.68rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            background: 'var(--color-info-soft)',
            color: 'var(--color-info)',
            border: '1px solid var(--color-info)',
            fontWeight: 700
          }}>
            ACCEPTED
          </span>
        );
      case 'EN_ROUTE':
      case 'DISPATCHED':
        return (
          <span style={{
            fontSize: '0.68rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            background: 'var(--color-warning-soft)',
            color: 'var(--color-warning)',
            border: '1px solid var(--color-warning)',
            fontWeight: 700
          }}>
            EN ROUTE
          </span>
        );
      case 'ARRIVED':
      case 'ON_SCENE':
        return (
          <span style={{
            fontSize: '0.68rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            background: 'var(--color-success-soft)',
            color: 'var(--color-success)',
            border: '1px solid var(--color-success)',
            fontWeight: 700
          }}>
            ARRIVED ON SCENE
          </span>
        );
      case 'BUSY':
        return (
          <span style={{
            fontSize: '0.68rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            background: 'var(--color-surface-elevated)',
            color: 'var(--color-text-muted)',
            border: '1px solid var(--color-border)',
            fontWeight: 700
          }}>
            BUSY
          </span>
        );
      default:
        return (
          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
            {status}
          </span>
        );
    }
  };

  const getSeverityClass = (level) => {
    switch (level?.toUpperCase()) {
      case 'CRITICAL': return 'sev-critical';
      case 'HIGH': return 'sev-high';
      case 'MEDIUM': return 'sev-medium';
      case 'LOW': return 'sev-low';
      default: return 'sev-medium';
    }
  };

  // Filter calculations from real API data
  const filteredEmergencies = emergencies.filter(incident => {
    if (filter === 'ALL') return true;
    return incident.status?.toUpperCase() === filter;
  });

  return (
    <div>
      {/* Feed Toolbar with Filters */}
      <div className="toolbar-strip">
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Live Emergency Incident Feed
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.15rem' }}>
            Incident telemetry, AI severity classification, and Haversine proximity unit matching
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div className="filter-pills" role="tablist" aria-label="Incident status filters">
            <button
              type="button"
              className={`filter-pill ${filter === 'ALL' ? 'active' : ''}`}
              onClick={() => setFilter('ALL')}
            >
              All ({emergencies.length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'ACTIVE' ? 'active' : ''}`}
              onClick={() => setFilter('ACTIVE')}
            >
              Active ({emergencies.filter(e => e.status === 'ACTIVE').length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'RESPONDING' ? 'active' : ''}`}
              onClick={() => setFilter('RESPONDING')}
            >
              Responding ({emergencies.filter(e => e.status === 'RESPONDING').length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'RESOLVED' ? 'active' : ''}`}
              onClick={() => setFilter('RESOLVED')}
            >
              Resolved ({emergencies.filter(e => e.status === 'RESOLVED').length})
            </button>
          </div>

          <button
            type="button"
            className="btn-secondary touch-target"
            onClick={onRefresh}
            title="Refresh incident list"
            aria-label="Refresh feed"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Empty State */}
      {filteredEmergencies.length === 0 ? (
        <div className="fc-panel" style={{ textAlign: 'center', padding: '2.5rem 1.5rem' }}>
          <CheckCircle2 size={36} color="#10b981" style={{ margin: '0 auto 0.75rem' }} />
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {filter === 'ALL' ? 'No Emergencies Logged' : `No Incidents with status "${filter}"`}
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.825rem', maxWidth: '440px', margin: '0.35rem auto 1.25rem' }}>
            All family members are currently marked safe. {user?.role !== 'responder' ? 'Use the demonstration SOS button to simulate an emergency incident.' : 'No active dispatches assigned to your unit.'}
          </p>
          {user?.role !== 'responder' && (
            <button type="button" className="btn-primary touch-target" onClick={onOpenSos}>
              <ShieldAlert size={15} /> Trigger Demo Emergency SOS
            </button>
          )}
        </div>
      ) : (
        <div>
          {filteredEmergencies.map((incident) => {
            const isTriageOpen = Boolean(expandedTriage[incident.id]);
            const isRespondersOpen = Boolean(expandedResponders[incident.id]);
            const isMapOpen = Boolean(expandedMap[incident.id]);
            const isTimelineOpen = Boolean(expandedTimeline[incident.id]);
            const isAlertsOpen = Boolean(expandedAlerts[incident.id]);

            return (
              <article
                key={incident.id}
                className={`incident-card ${getSeverityClass(incident.severity_level)}`}
                aria-labelledby={`incident-title-${incident.id}`}
                style={{ padding: '0.95rem 1.1rem', marginBottom: '0.75rem' }}
              >
                {/* Header row: Title, Badges, Timestamps, Action buttons */}
                <div className="incident-header" style={{ marginBottom: '0.45rem' }}>
                  <div>
                    <div className="incident-title-area">
                      <h3 id={`incident-title-${incident.id}`} className="incident-title" style={{ fontSize: '1rem' }}>
                        {incident.incident_type}
                      </h3>
                      {getSeverityBadge(incident.severity_level)}
                      {getStatusBadge(incident.status)}
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                        ID #{incident.id}
                      </span>
                    </div>

                    <div className="incident-meta" style={{ marginTop: '0.25rem', marginBottom: '0.25rem' }}>
                      <span className="meta-chip">
                        Person: <strong style={{ color: 'var(--text-primary)' }}>{incident.reporter_name}</strong>
                      </span>
                      <span>•</span>
                      <span className="meta-chip">
                        <Clock size={11} color="#94a3b8" />
                        {new Date(incident.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      <span>•</span>
                      <span className="meta-chip">
                        <MapPin size={11} color="#ef4444" />
                        {incident.location_label}
                      </span>
                    </div>
                  </div>

                  {/* Incident Lifecycle Action Buttons */}
                  <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    {incident.status === 'ACTIVE' && (
                      <button
                        type="button"
                        className="btn-secondary incident-action-btn"
                        disabled={updatingId === incident.id}
                        onClick={() => handleStatusChange(incident.id, 'RESPONDING')}
                        style={{ color: '#38bdf8', borderColor: 'rgba(56, 189, 248, 0.4)', fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                      >
                        {updatingId === incident.id ? 'Updating...' : 'Mark Responding'}
                      </button>
                    )}

                    {user?.role !== 'responder' && incident.status !== 'RESOLVED' && (
                      <button
                        type="button"
                        className="btn-secondary incident-action-btn"
                        disabled={updatingId === incident.id}
                        onClick={() => handleStatusChange(incident.id, 'RESOLVED')}
                        style={{ color: '#34d399', borderColor: 'rgba(16, 185, 129, 0.4)', fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                      >
                        {updatingId === incident.id ? 'Updating...' : 'Resolve Incident'}
                      </button>
                    )}
                  </div>
                </div>

                {/* Incident Description / Message */}
                {(() => {
                  const message = getIncidentDisplayMessage(incident);
                  return message ? (
                    <p style={{
                      fontSize: '0.825rem',
                      color: 'var(--text-secondary)',
                      marginBottom: '0.55rem',
                      lineHeight: '1.45',
                      fontWeight: 500
                    }}>
                      {message}
                    </p>
                  ) : null;
                })()}

                {/* Display Saved Resolution Summary for Resolved Incidents */}
                {incident.status === 'RESOLVED' && (
                  <div style={{
                    background: 'rgba(16, 185, 129, 0.08)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    borderRadius: '6px',
                    padding: '0.5rem 0.75rem',
                    marginBottom: '0.5rem',
                    fontSize: '0.8rem'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                      <strong style={{ color: '#34d399', display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem' }}>
                        <CheckCircle2 size={13} color="#10b981" /> Incident Resolution Summary
                      </strong>
                      {incident.resolved_at && (
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          Resolved at: {new Date(incident.resolved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                    <p style={{ color: 'var(--text-primary)', margin: 0, fontSize: '0.78rem' }}>
                      {incident.resolution_notes || 'Incident marked resolved and confirmed safe.'}
                    </p>
                  </div>
                )}

                {/* Progression Timeline Indicator */}
                <div className="incident-timeline" style={{ margin: '0.45rem 0' }} aria-label="Incident Progression Stages">
                  <div className="timeline-step completed">
                    <CheckCircle2 size={12} />
                    <span>Reported</span>
                  </div>
                  <div className="timeline-divider" />
                  <div className="timeline-step completed">
                    <CheckCircle2 size={12} />
                    <span>AI Triaged ({incident.severity_level})</span>
                  </div>
                  <div className="timeline-divider" />
                  <div className="timeline-step completed">
                    <CheckCircle2 size={12} />
                    <span>Responders Ranked</span>
                  </div>
                  <div className="timeline-divider" />
                  <div className={`timeline-step ${incident.status === 'RESPONDING' || incident.status === 'RESOLVED' ? 'completed' : 'active'}`}>
                    <span>
                      {incident.status === 'ACTIVE' && '● Active Alert'}
                      {incident.status === 'RESPONDING' && '● Units En Route'}
                      {incident.status === 'RESOLVED' && '✓ Incident Resolved'}
                    </span>
                  </div>
                </div>

                {/* Expandable Disclosure Controls */}
                <div style={{ display: 'flex', gap: '0.45rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="disclosure-btn"
                    onClick={() => toggleTriage(incident.id)}
                    aria-expanded={isTriageOpen}
                  >
                    <Bot size={12} color="#c084fc" />
                    <span>AI Triage</span>
                    {isTriageOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>

                  <button
                    type="button"
                    className="disclosure-btn"
                    onClick={() => toggleResponders(incident.id)}
                    aria-expanded={isRespondersOpen}
                  >
                    <UserCheck size={12} color="#38bdf8" />
                    <span>Responders ({incident.matched_responders?.length || 0})</span>
                    {isRespondersOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>

                  <button
                    type="button"
                    className="disclosure-btn"
                    onClick={() => toggleAlerts(incident.id)}
                    aria-expanded={isAlertsOpen}
                  >
                    <Bell size={12} color="#f59e0b" />
                    <span>Family Alerts ({incident.alerts?.length || 0})</span>
                    {isAlertsOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>

                  <button
                    type="button"
                    className="disclosure-btn"
                    onClick={() => toggleTimeline(incident.id)}
                    aria-expanded={isTimelineOpen}
                  >
                    <Clock size={12} color="#94a3b8" />
                    <span>Timeline Log ({incident.timeline_events?.length || 0})</span>
                    {isTimelineOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>

                  <button
                    type="button"
                    className="disclosure-btn"
                    onClick={() => toggleMap(incident.id)}
                    aria-expanded={isMapOpen}
                  >
                    <Navigation size={12} color="#10b981" />
                    <span>Proximity Radar</span>
                    {isMapOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                </div>

                {/* Collapsible Panel 1: AI Triage Rationale */}
                {isTriageOpen && (
                  <div className="disclosure-body" style={{ borderLeft: '3px solid #a855f7' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                      <strong style={{ color: '#c084fc', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <Bot size={13} /> Scikit-Learn Multimodal Triage Rationale (v2)
                      </strong>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        Statistical Model Output Certainty: {(incident.severity_score * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* Conflict Banner if Rationale indicates discrepancy */}
                    {incident.ai_rationale && incident.ai_rationale.includes('CONTRADICTION') && (
                      <div style={{
                        background: 'rgba(245, 158, 11, 0.12)',
                        border: '1px solid rgba(245, 158, 11, 0.4)',
                        borderRadius: '4px',
                        padding: '0.4rem 0.6rem',
                        marginBottom: '0.45rem',
                        fontSize: '0.75rem',
                        color: '#fbbf24',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.35rem'
                      }}>
                        <AlertTriangle size={13} /> Vital Sign Discrepancy Flagged: Clinical structured flags prioritize patient safety over bystander text notes.
                      </div>
                    )}

                    <div style={{
                      background: 'var(--bg-primary)',
                      padding: '0.6rem 0.75rem',
                      borderRadius: '5px',
                      border: '1px solid var(--border-subtle)',
                      marginBottom: '0.4rem'
                    }}>
                      <p style={{ color: 'var(--text-primary)', fontSize: '0.8rem', lineHeight: 1.5, margin: 0 }}>
                        {incident.ai_rationale || 'Assessment details logged.'}
                      </p>
                    </div>

                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Info size={11} color="#94a3b8" /> Decision-support tool only. Synthetic Random Forest model output does not replace professional clinical evaluation or emergency medical dispatch judgment.
                    </div>
                  </div>
                )}

                {/* Collapsible Panel 2: Matched Responders */}
                {isRespondersOpen && (
                  <div className="disclosure-body" style={{ borderLeft: '3px solid #38bdf8' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#38bdf8', marginBottom: '0.45rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <UserCheck size={13} /> Nearest Verified Units (Haversine Distance Sorting — Verified Coordinates Only):
                    </div>

                    {incident.matched_responders && incident.matched_responders.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                        {incident.matched_responders.map((resp, i) => (
                          <div key={i} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '0.35rem 0.55rem',
                            background: 'var(--bg-secondary)',
                            borderRadius: '6px',
                            border: '1px solid var(--border-subtle)'
                          }}>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                <strong style={{ color: 'var(--text-primary)', fontSize: '0.825rem' }}>{resp.name}</strong>
                                <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                                  ({resp.role}{resp.organization ? ` • ${resp.organization}` : ''})
                                </span>
                                {getResponderStatusBadge(resp.status)}
                              </div>
                              <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.1rem' }}>
                                Capabilities: {resp.skills} • Distance: <span style={{ color: '#38bdf8', fontWeight: 700 }}>{resp.distance_km} km</span>
                                {resp.location_source ? ` • Source: ${resp.location_source === 'browser_gps' ? 'Browser GPS' : resp.location_source}` : ''}
                                {resp.location_accuracy_m != null ? ` (±${Math.round(resp.location_accuracy_m)}m)` : ''}
                                {resp.location_updated_at ? ` (${new Date(resp.location_updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})` : ''}
                              </div>
                              {/* Progress Timestamps */}
                              {(resp.accepted_at || resp.en_route_at || resp.arrived_at) && (
                                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                                  {resp.accepted_at && `Accepted: ${new Date(resp.accepted_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} `}
                                  {resp.en_route_at && `• En Route: ${new Date(resp.en_route_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} `}
                                  {resp.arrived_at && `• On Scene: ${new Date(resp.arrived_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
                                </div>
                              )}
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                              {/* Responder Action Buttons (for logged-in responder's own assignment) */}
                              {user?.role === 'responder' && user?.responder_id === resp.responder_id && resp.assignment_id && (
                                <div style={{ display: 'flex', gap: '0.35rem' }}>
                                  {(resp.status === 'ASSIGNED' || resp.status === 'RECOMMENDED') && (
                                    <button
                                      type="button"
                                      className="btn-primary"
                                      style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem' }}
                                      disabled={updatingAssignmentId === resp.assignment_id}
                                      onClick={() => handleAssignmentTransition(resp.assignment_id, 'ACCEPTED')}
                                    >
                                      {updatingAssignmentId === resp.assignment_id ? 'Accepting...' : 'Accept Assignment'}
                                    </button>
                                  )}
                                  {resp.status === 'ACCEPTED' && (
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem', color: '#fbbf24', borderColor: 'rgba(251, 191, 36, 0.4)' }}
                                      disabled={updatingAssignmentId === resp.assignment_id}
                                      onClick={() => handleAssignmentTransition(resp.assignment_id, 'EN_ROUTE')}
                                    >
                                      <Truck size={12} /> {updatingAssignmentId === resp.assignment_id ? 'Updating...' : 'Mark En Route'}
                                    </button>
                                  )}
                                  {resp.status === 'EN_ROUTE' && (
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem', color: '#34d399', borderColor: 'rgba(52, 211, 153, 0.4)' }}
                                      disabled={updatingAssignmentId === resp.assignment_id}
                                      onClick={() => handleAssignmentTransition(resp.assignment_id, 'ARRIVED')}
                                    >
                                      <MapPinned size={12} /> {updatingAssignmentId === resp.assignment_id ? 'Recording...' : 'Mark Arrived on Scene'}
                                    </button>
                                  )}
                                  {resp.status === 'ARRIVED' && (
                                    <span style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                      <CheckCircle2 size={13} /> On Scene Confirmed
                                    </span>
                                  )}
                                </div>
                              )}

                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                  <PhoneCall size={9} style={{ display: 'inline', verticalAlign: '-1px' }} /> {resp.phone}
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.75rem', color: '#fbbf24', padding: '0.35rem 0.5rem', background: 'rgba(245, 158, 11, 0.08)', borderRadius: '5px' }}>
                        No active responders had verified coordinates at dispatch time. Configure responder coordinates in the Responders &amp; Alerts tab.
                      </div>
                    )}
                  </div>
                )}

                {/* Collapsible Panel 3: Family Contact Alerts (Phase 5B Real Provider Delivery Tracking) */}
                {isAlertsOpen && (
                  <div className="disclosure-body" style={{ borderLeft: '3px solid #f59e0b' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#fbbf24', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <Bell size={13} /> Trusted Family Contact Alerts:
                      </div>
                      <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                        Live Provider Delivery &amp; Acknowledgment Audit
                      </span>
                    </div>

                    {incident.alerts && incident.alerts.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                        {incident.alerts.map((alert) => {
                          const st = (alert.status || 'QUEUED').toUpperCase();
                          const isAck = st === 'ACKNOWLEDGED';
                          const isDelivered = st === 'DELIVERED' || st === 'SENT';
                          const isSimulated = st === 'SIMULATED';
                          const isFailed = st === 'FAILED';

                          const badgeBg = isAck
                            ? 'rgba(16, 185, 129, 0.15)'
                            : isDelivered
                            ? 'rgba(56, 189, 248, 0.15)'
                            : isSimulated
                            ? 'rgba(168, 85, 247, 0.18)'
                            : isFailed
                            ? 'rgba(239, 68, 68, 0.18)'
                            : 'rgba(245, 158, 11, 0.15)';
                          const badgeColor = isAck
                            ? '#34d399'
                            : isDelivered
                            ? '#38bdf8'
                            : isSimulated
                            ? '#c084fc'
                            : isFailed
                            ? '#f87171'
                            : '#fbbf24';
                          const badgeBorder = isAck
                            ? 'rgba(16, 185, 129, 0.35)'
                            : isDelivered
                            ? 'rgba(56, 189, 248, 0.35)'
                            : isSimulated
                            ? 'rgba(168, 85, 247, 0.4)'
                            : isFailed
                            ? 'rgba(239, 68, 68, 0.4)'
                            : 'rgba(245, 158, 11, 0.35)';

                          const badgeLabel = isAck
                            ? '✓ ACKNOWLEDGED'
                            : isDelivered
                            ? `● ${st} (${alert.provider || 'live'})`
                            : isSimulated
                            ? `◈ SIMULATED (${alert.provider || 'mock'})`
                            : isFailed
                            ? `✕ DELIVERY FAILED (${alert.provider || 'unconfigured'})`
                            : `● ${st}`;

                          return (
                            <div
                              key={alert.id}
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '0.45rem 0.65rem',
                                background: 'var(--bg-secondary)',
                                borderRadius: '6px',
                                border: isFailed ? '1px solid rgba(239, 68, 68, 0.35)' : '1px solid var(--border-subtle)',
                                flexWrap: 'wrap',
                                gap: '0.5rem'
                              }}
                            >
                              <div style={{ flex: 1, minWidth: '240px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
                                  <strong style={{ color: 'var(--text-primary)', fontSize: '0.825rem' }}>{alert.contact_name}</strong>
                                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                                    ({alert.contact_email
                                      ? maskEmail(alert.contact_email, { isDemo: isDemoEntity(alert), demoSeed: alert.contact_name })
                                      : maskPhoneNumber(alert.contact_phone, { isDemo: isDemoEntity(alert), demoSeed: alert.id })})
                                  </span>
                                  <span style={{
                                    fontSize: '0.65rem',
                                    padding: '0.1rem 0.45rem',
                                    borderRadius: '4px',
                                    background: badgeBg,
                                    color: badgeColor,
                                    border: `1px solid ${badgeBorder}`,
                                    fontWeight: 700
                                  }}>
                                    {badgeLabel}
                                  </span>
                                </div>
                                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.18rem' }}>
                                  Channel: <strong>{alert.channel}</strong>
                                  {alert.provider ? ` • Provider: ${alert.provider}` : ''}
                                  {alert.delivery_attempts != null ? ` • Attempts: ${alert.delivery_attempts}` : ''}
                                  {alert.provider_message_id ? ` • MsgID: ${alert.provider_message_id}` : ''}
                                  {' • Logged: '}
                                  {new Date(alert.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                  {alert.delivered_at && ` • Delivered: ${new Date(alert.delivered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`}
                                  {alert.acknowledged_at && ` • Ack: ${new Date(alert.acknowledged_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`}
                                </div>
                                {alert.error_message && (
                                  <div style={{ fontSize: '0.68rem', color: '#fca5a5', marginTop: '0.2rem' }}>
                                    Provider Diagnostic: {alert.error_message}
                                  </div>
                                )}
                              </div>

                              {/* Retry & Acknowledge Controls */}
                              {user?.role !== 'responder' && incident.status !== 'RESOLVED' && (
                                <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                                  {(st === 'FAILED' || st === 'QUEUED' || st === 'SIMULATED') && (
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      style={{ fontSize: '0.7rem', padding: '0.25rem 0.55rem', color: '#fbbf24', borderColor: 'rgba(245, 158, 11, 0.4)' }}
                                      disabled={retryingAlertId === alert.id}
                                      onClick={() => handleRetryAlert(incident.id, alert.id)}
                                    >
                                      <RefreshCw size={11} /> {retryingAlertId === alert.id ? 'Retrying...' : 'Retry Delivery'}
                                    </button>
                                  )}
                                  {st !== 'ACKNOWLEDGED' && (
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      style={{ fontSize: '0.7rem', padding: '0.25rem 0.55rem', color: '#38bdf8' }}
                                      disabled={acknowledgingId === alert.id}
                                      onClick={() => handleAcknowledgeAlert(incident.id, alert.id)}
                                    >
                                      {acknowledgingId === alert.id ? 'Confirming...' : 'Acknowledge as Contact'}
                                    </button>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        No family contact alert generated for this incident.
                      </div>
                    )}
                  </div>
                )}

                {/* Collapsible Panel 4: Chronological Persistent Timeline */}
                {isTimelineOpen && (
                  <div className="disclosure-body" style={{ borderLeft: '3px solid #64748b' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.45rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Clock size={13} color="#94a3b8" /> Persistent Incident Timeline Log:
                    </div>

                    {incident.timeline_events && incident.timeline_events.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        {incident.timeline_events.map((event) => (
                          <div
                            key={event.id}
                            style={{
                              display: 'flex',
                              alignItems: 'flex-start',
                              gap: '0.55rem',
                              padding: '0.35rem 0.5rem',
                              background: 'var(--bg-secondary)',
                              borderRadius: '6px',
                              border: '1px solid var(--border-subtle)',
                              fontSize: '0.78rem'
                            }}
                          >
                            <span style={{
                              color: 'var(--text-muted)',
                              fontFamily: 'monospace',
                              fontSize: '0.7rem',
                              flexShrink: 0,
                              marginTop: '1px'
                            }}>
                              {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                            <div style={{ flex: 1 }}>
                              <strong style={{ color: 'var(--text-primary)' }}>{event.title}</strong>
                              {event.description && (
                                <div style={{ color: 'var(--text-secondary)', fontSize: '0.73rem', marginTop: '0.1rem' }}>
                                  {event.description}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        No timeline events recorded yet.
                      </div>
                    )}
                  </div>
                )}

                {/* Collapsible Panel 5: Responsive Proximity Map & Live GPS Refresh */}
                {isMapOpen && (
                  <IncidentProximityMap
                    incident={incident}
                    allResponders={allResponders}
                    canRefreshLocation={user?.role !== 'responder'}
                    onLocationUpdated={() => onRefresh()}
                  />
                )}
              </article>
            );
          })}
        </div>
      )}

      {/* Resolution Notes Modal */}
      {resolvingIncident && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="resolve-modal-title">
          <div className="modal-content" style={{ maxWidth: '500px', border: '1px solid rgba(16, 185, 129, 0.4)' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={20} color="#10b981" />
                <h3 id="resolve-modal-title" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Resolve Incident #{resolvingIncident.id}
                </h3>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setResolvingIncident(null)}
              >
                ✕
              </button>
            </div>

            {resolutionError && (
              <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', padding: '0.65rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.8rem' }}>
                {resolutionError}
              </div>
            )}

            <form onSubmit={handleConfirmResolve}>
              <div style={{ marginBottom: '0.85rem', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                You are marking the emergency for <strong>{resolvingIncident.reporter_name}</strong> ({resolvingIncident.incident_type}) as resolved.
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="resolution-notes-input">
                  Resolution Summary / Clinical Disposition Notes:
                </label>
                <textarea
                  id="resolution-notes-input"
                  rows={3}
                  className="form-textarea"
                  placeholder="e.g. Paramedic unit attended on scene, vitals stabilized, patient safely accompanied to medical center."
                  value={resolutionNotesInput}
                  onChange={(e) => setResolutionNotesInput(e.target.value)}
                />
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'block' }}>
                  These notes will be permanently logged in the incident audit trail.
                </span>
              </div>

              <div style={{ display: 'flex', gap: '0.65rem', marginTop: '1.25rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => setResolvingIncident(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updatingId === resolvingIncident.id}
                  className="btn-primary"
                  style={{ flex: 2, background: '#10b981', borderColor: '#34d399', justifyContent: 'center' }}
                >
                  <Check size={15} />
                  <span>{updatingId === resolvingIncident.id ? 'Resolving...' : 'Confirm & Close Incident'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
