import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldAlert,
  Navigation,
  HeartHandshake,
  CheckCircle2,
  AlertTriangle,
  MapPin,
  Users,
  Clock,
  WifiOff
} from 'lucide-react';
import { triggerSos } from '../services/api';
import { syncMemberSelection } from '../utils/memberSelection.js';
import { isDemoEntity, maskPhoneNumber, maskEmail } from '../utils/privacyMask.js';

const INCIDENT_CATEGORIES = [
  "Cardiac / Chest Pain",
  "Breathing Difficulty",
  "Unconscious / Unresponsive",
  "Severe Bleeding",
  "Fall with Injury",
  "General SOS / Panic",
  "Minor Injury"
];

export default function SosTriggerModal({
  isOpen,
  onClose,
  members,
  preselectedMember,
  onEmergencyTriggered,
  isOnline = true
}) {
  const activeMembers = (members || []).filter((m) => m.is_active !== false);

  const [selectedMemberId, setSelectedMemberId] = useState('');
  const [reporterName, setReporterName] = useState('');
  const [incidentType, setIncidentType] = useState('Cardiac / Chest Pain');
  const [description, setDescription] = useState('');

  // Phase 6 Section 8: Real Location Mode ('gps' vs 'manual')
  // Never silently substitute hardcoded city coordinates.
  const [locationMode, setLocationMode] = useState('gps');
  const [gpsState, setGpsState] = useState('idle'); // 'idle' | 'requesting' | 'granted' | 'denied' | 'unavailable' | 'timeout'
  const [gpsCoords, setGpsCoords] = useState(null);
  const [locationStatus, setLocationStatus] = useState('');

  // Explicit Manual Coordinate Inputs (No hardcoded SF coordinates)
  const [manualLat, setManualLat] = useState('');
  const [manualLon, setManualLon] = useState('');
  const [manualLabel, setManualLabel] = useState('');

  // Triage vital flags
  const [isConscious, setIsConscious] = useState(true);
  const [hasBreathingDiff, setHasBreathingDiff] = useState(true);
  const [isBleedingSeverely, setIsBleedingSeverely] = useState(false);
  const [isAlone, setIsAlone] = useState(true);

  // Safety Confirmation
  const [acknowledgedDispatch, setAcknowledgedDispatch] = useState(false);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [isSecureOrigin, setIsSecureOrigin] = useState(true);

  const prevIsOpenRef = useRef(false);
  const prevPreselectedIdRef = useRef(preselectedMember?.id);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      setIsSecureOrigin(Boolean(window.isSecureContext || isLocal));
    }
  }, []);

  useEffect(() => {
    syncMemberSelection({
      isOpen,
      members,
      preselectedMember,
      selectedMemberId,
      reporterName,
      manualLabel,
      prevIsOpenRef,
      prevPreselectedIdRef,
      setSelectedMemberId,
      setReporterName,
      setManualLabel
    });
  }, [preselectedMember, members, isOpen]);

  const selectedMember = activeMembers.find((m) => m.id.toString() === selectedMemberId) || null;
  const activeContactsForMember = (selectedMember?.trusted_contacts || []).filter((c) => c.is_active !== false);

  // Request real device coordinates ONLY after explicit user permission action
  const detectGps = () => {
    setLocationMode('gps');
    setError('');
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setGpsState('unavailable');
      setGpsCoords(null);
      setLocationStatus(
        'Browser Geolocation API is not supported in this environment. Switch to "Manual Coordinate Entry" to enter verified coordinates.'
      );
      return;
    }

    setGpsState('requesting');
    setLocationStatus('Requesting browser location permission & acquiring GPS fix...');

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = parseFloat(pos.coords.latitude.toFixed(6));
        const lon = parseFloat(pos.coords.longitude.toFixed(6));
        const accuracy = pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null;
        const capturedAt = new Date(pos.timestamp || Date.now()).toISOString();
        setGpsCoords({
          lat,
          lon,
          accuracy,
          capturedAt
        });
        setGpsState('granted');
        setLocationStatus(
          `Verified Browser GPS acquired: (${lat}, ${lon})${accuracy ? ` • Accuracy ±${accuracy}m` : ''} • Timestamp: ${new Date(capturedAt).toLocaleTimeString()}`
        );
      },
      (err) => {
        setGpsCoords(null);
        if (err.code === 1) {
          setGpsState('denied');
          setLocationStatus(
            'Location Permission Denied by user/browser. No fallback coordinates were substituted. Grant permission or switch to Manual Coordinate Entry.'
          );
        } else if (err.code === 3) {
          setGpsState('timeout');
          setLocationStatus(
            'GPS Fix Timed Out. No default location was substituted. Retry GPS acquisition or enter Manual Coordinates.'
          );
        } else {
          setGpsState('unavailable');
          setLocationStatus(
            `GPS Position Unavailable (${err.message || 'sensor error'}). No default location was substituted. Enter Manual Coordinates below.`
          );
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleSosSubmit = async (e) => {
    e.preventDefault();
    if (loading || submitting) return;

    if (!isOnline) {
      setError('Cannot dispatch SOS while offline. Network connectivity (cellular/Wi-Fi) is required to evaluate triage, reach responders, and alert trusted contacts.');
      return;
    }

    if (!selectedMemberId) {
      setError('Please select an active family member profile before dispatching an SOS.');
      return;
    }
    if (!acknowledgedDispatch) {
      setError('Please confirm the emergency dispatch authorization checkbox before proceeding.');
      return;
    }

    let lat, lon, locLabel, accuracyM = null, locSource = 'browser_gps';

    if (locationMode === 'gps') {
      if (gpsState !== 'granted' || !gpsCoords) {
        setError(
          'Live Browser GPS coordinates have not been acquired yet (or permission was denied). We never silently substitute fake coordinates. Click "Acquire Live Browser GPS" or switch to "Manual Coordinate Entry".'
        );
        return;
      }
      lat = gpsCoords.lat;
      lon = gpsCoords.lon;
      accuracyM = gpsCoords.accuracy;
      locSource = 'browser_gps';
      locLabel = manualLabel.trim()
        ? `${manualLabel.trim()} (${lat.toFixed(4)}, ${lon.toFixed(4)})`
        : `Verified Browser GPS (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
    } else {
      const parsedLat = parseFloat(manualLat);
      const parsedLon = parseFloat(manualLon);
      if (
        Number.isNaN(parsedLat) ||
        Number.isNaN(parsedLon) ||
        parsedLat < -90 ||
        parsedLat > 90 ||
        parsedLon < -180 ||
        parsedLon > 180
      ) {
        setError('Valid numeric Latitude (-90 to 90) and Longitude (-180 to 180) are required for Manual Coordinate Entry.');
        return;
      }
      lat = parsedLat;
      lon = parsedLon;
      accuracyM = null;
      locSource = 'manual';
      locLabel = manualLabel.trim()
        ? `${manualLabel.trim()} (${lat.toFixed(4)}, ${lon.toFixed(4)})`
        : `Manual Coordinates (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
    }

    setSubmitting(true);
    setLoading(true);
    setError('');

    try {
      const payload = {
        member_id: parseInt(selectedMemberId, 10),
        reporter_name: reporterName || (selectedMember ? selectedMember.name : 'Family Member'),
        incident_type: incidentType,
        description: description || `Emergency SOS incident reported for ${reporterName}`,
        latitude: lat,
        longitude: lon,
        location_label: locLabel,
        location_accuracy_m: accuracyM,
        location_source: locSource,
        is_conscious: isConscious,
        has_breathing_difficulty: hasBreathingDiff,
        is_bleeding_severely: isBleedingSeverely,
        is_alone: isAlone
      };

      const result = await triggerSos(payload);
      onEmergencyTriggered(result);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to dispatch SOS alert');
    } finally {
      setLoading(false);
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="sos-modal-title">
      <div className="modal-content" style={{ border: '1px solid var(--red-border)', maxWidth: '580px' }}>
        {/* Modal Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div style={{ background: 'var(--red-500)', padding: '0.4rem', borderRadius: '8px', color: '#fff' }}>
              <ShieldAlert size={20} />
            </div>
            <div>
              <h3 id="sos-modal-title" style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--color-text)' }}>
                Emergency SOS Dispatch
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                AI Triage • Verified Coordinates • Saved Trusted Contact Alerts • Live Responder Matching
              </p>
            </div>
          </div>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {/* Offline Warning Banner */}
        {!isOnline && (
          <div
            className="alert-banner alert-banner-offline"
            role="alert"
            style={{ marginBottom: '1rem', padding: '0.65rem 0.85rem' }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem' }}>
              <WifiOff size={16} color="#fbbf24" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div style={{ fontSize: '0.78rem', color: '#fef3c7' }}>
                <strong>SOS Dispatch Unavailable Offline:</strong> Active internet connection (cellular or Wi-Fi) is required to evaluate AI triage, notify configured trusted contacts, and dispatch community responders. Live emergency coordination cannot function without internet access.
              </div>
            </div>
          </div>
        )}

        {/* Safety Notice Banner */}
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px',
          padding: '0.65rem 0.85rem',
          marginBottom: '1rem',
          fontSize: '0.78rem',
          color: '#fca5a5',
          display: 'flex',
          gap: '0.5rem',
          alignItems: 'flex-start'
        }}>
          <AlertTriangle size={15} color="#ef4444" style={{ flexShrink: 0, marginTop: '2px' }} />
          <div>
            <strong>Safety Notice:</strong> Dispatches live alerts to configured household trusted contacts and coordinates community responders on this platform. Does <em>not</em> dial 112/108 public emergency services.
          </div>
        </div>

        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
            padding: '0.65rem 0.85rem',
            borderRadius: '6px',
            marginBottom: '1rem',
            fontSize: '0.8rem'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSosSubmit}>
          {/* Member & Category */}
          <div className="form-row-2col">
            <div className="form-group">
              <label className="form-label" htmlFor="impacted-member">Active Household Member *</label>
              <select
                id="impacted-member"
                className="form-select"
                value={selectedMemberId}
                required
                onChange={(e) => {
                  setSelectedMemberId(e.target.value);
                  const mem = activeMembers.find(m => m.id.toString() === e.target.value);
                  if (mem) {
                    setReporterName(mem.name);
                    if (mem.address) setManualLabel(mem.address);
                  }
                }}
              >
                {activeMembers.length === 0 && (
                  <option value="">No active family members available</option>
                )}
                {activeMembers.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.relationship}{m.blood_group ? ` • ${m.blood_group}` : ''}{m.is_demo ? ' • Demo' : ''})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="incident-category">Emergency Category *</label>
              <select
                id="incident-category"
                className="form-select"
                value={incidentType}
                onChange={(e) => setIncidentType(e.target.value)}
              >
                {INCIDENT_CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Configured Trusted Contacts Summary for Selected Member */}
          {selectedMember && (
            <div style={{
              background: 'var(--bg-secondary)',
              border: activeContactsForMember.length > 0 ? '1px solid var(--border-subtle)' : '1px dashed rgba(245, 158, 11, 0.45)',
              borderRadius: '6px',
              padding: '0.55rem 0.75rem',
              marginBottom: '0.85rem',
              fontSize: '0.75rem'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.35rem' }}>
                <span style={{ color: 'var(--color-text)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <Users size={13} color="var(--color-primary)" />
                  Active Trusted Contacts for {selectedMember.name}: {activeContactsForMember.length}
                </span>
                {selectedMember.medical_notes && (
                  <span style={{ color: '#fca5a5', fontSize: '0.7rem' }}>
                    Medical Profile Attached
                  </span>
                )}
              </div>
              {activeContactsForMember.length > 0 ? (
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.72rem', marginTop: '0.2rem' }}>
                  Alerts will be dispatched to:{' '}
                  {activeContactsForMember.map((c) => {
                    const isDemo = isDemoEntity(c) || isDemoEntity(selectedMember);
                    const safeContact = c.email
                      ? maskEmail(c.email, { isDemo, demoSeed: c.name })
                      : maskPhoneNumber(c.phone, { isDemo, demoSeed: c.id });
                    return `${c.name} (${c.notification_preferences}: ${safeContact})`;
                  }).join(' • ')}
                </div>
              ) : (
                <div style={{ color: '#fbbf24', fontSize: '0.72rem', marginTop: '0.2rem' }}>
                  No active trusted contacts configured for this member. The SOS incident and responder matching will still be recorded, and the timeline will log NO_ACTIVE_CONTACTS.
                </div>
              )}
            </div>
          )}

          {/* Clinical Triage Indicators */}
          <div style={{
            background: 'var(--bg-primary)',
            padding: '0.85rem',
            borderRadius: '8px',
            marginBottom: '1rem',
            border: '1px solid var(--border-subtle)'
          }}>
            <div style={{
              fontSize: '0.78rem',
              fontWeight: 700,
              color: 'var(--color-primary)',
              marginBottom: '0.5rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem'
            }}>
              <HeartHandshake size={14} /> Clinical Triage Factors (Machine Learning Inputs):
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={!isConscious}
                  onChange={(e) => setIsConscious(!e.target.checked)}
                />
                <span style={{ color: !isConscious ? '#f87171' : 'inherit' }}>Unconscious / Unresponsive</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={hasBreathingDiff}
                  onChange={(e) => setHasBreathingDiff(e.target.checked)}
                />
                <span style={{ color: hasBreathingDiff ? '#fb923c' : 'inherit' }}>Breathing Difficulty</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={isBleedingSeverely}
                  onChange={(e) => setIsBleedingSeverely(e.target.checked)}
                />
                <span style={{ color: isBleedingSeverely ? '#f87171' : 'inherit' }}>Severe Bleeding</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={isAlone}
                  onChange={(e) => setIsAlone(e.target.checked)}
                />
                <span>Patient Alone / Isolated</span>
              </label>
            </div>
          </div>

          {/* Phase 6 Section 8: Real Geolocation or Explicit Manual Coordinate Entry */}
          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.35rem' }}>
              <label className="form-label" style={{ margin: 0 }}>
                Incident Location Coordinates *
              </label>
              <div style={{ display: 'flex', gap: '0.35rem' }}>
                <button
                  type="button"
                  className={locationMode === 'gps' ? 'btn-primary' : 'btn-secondary'}
                  style={{ fontSize: '0.72rem', padding: '0.2rem 0.55rem' }}
                  onClick={() => setLocationMode('gps')}
                >
                  <Navigation size={11} /> Live Browser GPS
                </button>
                <button
                  type="button"
                  className={locationMode === 'manual' ? 'btn-primary' : 'btn-secondary'}
                  style={{ fontSize: '0.72rem', padding: '0.2rem 0.55rem' }}
                  onClick={() => {
                    setLocationMode('manual');
                    setError('');
                  }}
                >
                  <MapPin size={11} /> Manual Coordinate Entry
                </button>
              </div>
            </div>

            {locationMode === 'gps' ? (
              <div style={{
                padding: '0.65rem 0.8rem',
                background: 'var(--bg-primary)',
                borderRadius: '6px',
                border: gpsState === 'granted'
                  ? '1px solid var(--emerald-border)'
                  : (gpsState === 'denied' || gpsState === 'unavailable' || gpsState === 'timeout')
                  ? '1px solid rgba(239, 68, 68, 0.45)'
                  : '1px solid var(--border-subtle)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <div style={{ fontSize: '0.78rem', color: 'var(--color-text)' }}>
                    {gpsState === 'granted' && gpsCoords ? (
                      <div style={{ color: '#10b981', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, flexWrap: 'wrap' }}>
                          <CheckCircle2 size={15} color="#10b981" />
                          Verified GPS Fix: ({gpsCoords.lat}, {gpsCoords.lon})
                          {gpsCoords.accuracy !== null && (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                padding: '0.1rem 0.45rem',
                                borderRadius: '4px',
                                fontSize: '0.68rem',
                                fontWeight: 700,
                                background: gpsCoords.accuracy <= 15 ? 'rgba(16, 185, 129, 0.15)' : gpsCoords.accuracy <= 50 ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                                color: gpsCoords.accuracy <= 15 ? '#10b981' : gpsCoords.accuracy <= 50 ? '#d97706' : '#ef4444',
                                border: `1px solid ${gpsCoords.accuracy <= 15 ? 'rgba(16, 185, 129, 0.3)' : gpsCoords.accuracy <= 50 ? 'rgba(245, 158, 11, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`
                              }}
                            >
                              ±{gpsCoords.accuracy}m Accuracy {gpsCoords.accuracy <= 15 ? '(High)' : gpsCoords.accuracy <= 50 ? '(Medium)' : '(Low)'}
                            </span>
                          )}
                        </span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                          <Clock size={11} /> Captured at: {new Date(gpsCoords.capturedAt).toLocaleString()}
                        </span>
                      </div>
                    ) : (
                      <span>Request real device GPS coordinates (requires browser permission)</span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '0.72rem', padding: '0.35rem 0.75rem', minHeight: '36px' }}
                    onClick={detectGps}
                    disabled={gpsState === 'requesting'}
                  >
                    <Navigation size={11} />
                    {gpsState === 'requesting'
                      ? 'Acquiring GPS...'
                      : gpsState === 'granted'
                      ? 'Refresh GPS Fix'
                      : 'Acquire Live Browser GPS'}
                  </button>
                </div>

                {locationStatus && (
                  <div style={{
                    fontSize: '0.72rem',
                    marginTop: '0.4rem',
                    color: gpsState === 'granted'
                      ? '#6ee7b7'
                      : (gpsState === 'denied' || gpsState === 'unavailable' || gpsState === 'timeout')
                      ? '#fca5a5'
                      : '#94a3b8'
                  }}>
                    {locationStatus}
                  </div>
                )}

                {!isSecureOrigin && (
                  <div style={{
                    marginTop: '0.5rem',
                    padding: '0.5rem 0.65rem',
                    background: 'rgba(245, 158, 11, 0.1)',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    borderRadius: '6px',
                    fontSize: '0.72rem',
                    color: '#fbbf24',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.4rem'
                  }}>
                    <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
                    <div>
                      <strong>Mobile Notice:</strong> When accessing over plain HTTP Wi-Fi (<code>{typeof window !== 'undefined' ? window.location.hostname : ''}</code>), mobile browsers disable the Geolocation API for security. Switch to <strong>Manual Coordinate Entry</strong> or use Chrome Port Forwarding.
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div style={{
                padding: '0.75rem',
                background: 'var(--bg-primary)',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)'
              }}>
                <div className="form-row-2col">
                  <div className="form-group" style={{ marginBottom: '0.5rem' }}>
                    <label className="form-label" htmlFor="sos-manual-lat" style={{ fontSize: '0.72rem' }}>Latitude (-90 to 90) *</label>
                    <input
                      id="sos-manual-lat"
                      type="number"
                      step="any"
                      min="-90"
                      max="90"
                      required
                      className="form-input"
                      placeholder="Enter latitude (e.g. 12.9716)"
                      value={manualLat}
                      onChange={(e) => setManualLat(e.target.value)}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: '0.5rem' }}>
                    <label className="form-label" htmlFor="sos-manual-lon" style={{ fontSize: '0.72rem' }}>Longitude (-180 to 180) *</label>
                    <input
                      id="sos-manual-lon"
                      type="number"
                      step="any"
                      min="-180"
                      max="180"
                      required
                      className="form-input"
                      placeholder="Enter longitude (e.g. 77.5946)"
                      value={manualLon}
                      onChange={(e) => setManualLon(e.target.value)}
                    />
                  </div>
                </div>
                <div className="form-group" style={{ marginBottom: '0.25rem' }}>
                  <label className="form-label" htmlFor="sos-manual-label" style={{ fontSize: '0.72rem' }}>Location Description / Address Label</label>
                  <input
                    id="sos-manual-label"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Residence Kitchen, Highway Exit 14"
                    value={manualLabel}
                    onChange={(e) => setManualLabel(e.target.value)}
                  />
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block' }}>
                  Recorded with <code>location_source="manual"</code> and exact submission timestamp.
                </span>
              </div>
            )}
          </div>

          {/* Notes */}
          <div className="form-group">
            <label className="form-label" htmlFor="incident-notes">Incident Notes / Bystander Observations</label>
            <input
              id="incident-notes"
              type="text"
              className="form-input"
              placeholder="e.g. Slipped in bathroom, clutching left chest, dizzy"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* Mandatory Safety Confirmation Checkbox */}
          <div style={{
            background: 'var(--bg-primary)',
            padding: '0.75rem 0.85rem',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            marginBottom: '1.25rem'
          }}>
            <label className="checkbox-row" style={{ alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                required
                checked={acknowledgedDispatch}
                onChange={(e) => setAcknowledgedDispatch(e.target.checked)}
                style={{ marginTop: '3px' }}
              />
              <span style={{ fontSize: '0.8rem', color: 'var(--color-text)' }}>
                <strong>Confirmation:</strong> I authorize dispatching this incident to the FamilyConnect AI coordinator and notifying the configured active household trusted contacts.
              </span>
            </label>
          </div>

          {/* Submit Action */}
          <div>
            <button
              type="submit"
              disabled={loading || submitting || !acknowledgedDispatch || activeMembers.length === 0 || !isOnline}
              className="compact-sos-btn"
              style={{
                width: '100%',
                justifyContent: 'center',
                padding: '0.85rem',
                minHeight: '48px',
                opacity: !isOnline ? 0.6 : 1,
                cursor: !isOnline ? 'not-allowed' : 'pointer',
                background: !isOnline ? '#475569' : undefined
              }}
            >
              {!isOnline ? (
                <>
                  <WifiOff size={18} />
                  <span>OFFLINE - CONNECTIVITY REQUIRED TO DISPATCH</span>
                </>
              ) : (
                <>
                  <ShieldAlert size={18} />
                  <span>{loading || submitting ? 'Evaluating Triage & Dispatching Alerts...' : 'CONFIRM & DISPATCH SOS'}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
