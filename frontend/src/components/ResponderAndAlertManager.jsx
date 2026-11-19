import React, { useState, useEffect } from 'react';
import {
  UserCheck,
  Plus,
  Edit2,
  Trash2,
  Power,
  Navigation,
  MapPin,
  Phone,
  Mail,
  Building2,
  Bell,
  Send,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Shield,
  FileCheck,
  XCircle,
  X
} from 'lucide-react';
import {
  createResponder,
  updateResponder,
  updateResponderLocation,
  deleteOrDeactivateResponder,
  sendTestNotification,
  getNotificationConfig,
  getResponderApplications,
  reviewResponderApplication
} from '../services/api';
import { validatePhoneNumber, DEFAULT_PHONE_PLACEHOLDER } from '../utils/phone';
import { isDemoEntity, maskPhoneNumber, maskEmail } from '../utils/privacyMask';

const EMPTY_RESPONDER_FORM = {
  name: '',
  role: 'Paramedic',
  organization: '',
  phone: '',
  email: '',
  skills: 'CPR, First Aid',
  is_available: true,
  is_active: true,
  includeCoordinates: false,
  latitude: '',
  longitude: '',
  location_source: 'manual',
  location_accuracy_m: null
};

export default function ResponderAndAlertManager({
  responders = [],
  notifConfig = null,
  onRefresh,
  onNotifConfigUpdated = null,
  user = null
}) {
  const [showResponderModal, setShowResponderModal] = useState(false);
  const [editingResponderId, setEditingResponderId] = useState(null);
  const [responderForm, setResponderForm] = useState(EMPTY_RESPONDER_FORM);
  const [submittingResponder, setSubmittingResponder] = useState(false);
  const [responderError, setResponderError] = useState('');
  const [notice, setNotice] = useState(null);

  // Filter toggles
  const [showInactive, setShowInactive] = useState(false);

  // Location Update Modal State
  const [locModalResponder, setLocModalResponder] = useState(null);
  const [locForm, setLocForm] = useState({
    latitude: '',
    longitude: '',
    location_source: 'manual',
    is_available: true
  });
  const [gpsStatus, setGpsStatus] = useState('');
  const [gpsAcquiring, setGpsAcquiring] = useState(false);
  const [savingLocation, setSavingLocation] = useState(false);

  // Notification Test Form State
  const [testChannel, setTestChannel] = useState('EMAIL');
  const [testRecipient, setTestRecipient] = useState('');
  const [confirmTestSend, setConfirmTestSend] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState('');

  const isAdmin = user?.role === 'admin';
  const isReviewer = Boolean(user?.is_platform_reviewer);
  const [activeSubTab, setActiveSubTab] = useState('profiles'); // 'profiles' | 'applications' | 'notifications'
  const [applications, setApplications] = useState([]);
  const [appsLoading, setAppsLoading] = useState(false);
  const [reviewNotes, setReviewNotes] = useState({});
  const [reviewActionLoading, setReviewActionLoading] = useState(null);

  const loadApplications = async () => {
    if (!isReviewer) return;
    try {
      setAppsLoading(true);
      const data = await getResponderApplications();
      setApplications(data || []);
    } catch (err) {
      console.warn('Failed to fetch responder applications:', err);
    } finally {
      setAppsLoading(false);
    }
  };

  useEffect(() => {
    if (isReviewer) {
      loadApplications();
    }
  }, [isReviewer]);

  const handleReviewDecision = async (appId, action) => {
    const notes = reviewNotes[appId] || '';
    try {
      setReviewActionLoading(appId);
      await reviewResponderApplication(appId, { action, review_notes: notes });
      setNotice({
        type: 'success',
        text: `Responder application #${appId} ${action === 'APPROVE' ? 'APPROVED and activated' : 'REJECTED'}.`
      });
      await loadApplications();
      if (onRefresh) onRefresh();
    } catch (err) {
      setNotice({
        type: 'error',
        text: err.message || `Failed to ${action.toLowerCase()} application.`
      });
    } finally {
      setReviewActionLoading(null);
    }
  };

  const canUpdateResponderLocation = (resp) => {
    if (!user) return false;
    if (user.role === 'admin') return true;
    if (user.role === 'responder' && user.responder_id === resp.id) return true;
    return false;
  };

  const handleOpenAddResponder = () => {
    setEditingResponderId(null);
    setResponderForm(EMPTY_RESPONDER_FORM);
    setResponderError('');
    setShowResponderModal(true);
  };

  const handleOpenEditResponder = (resp) => {
    setEditingResponderId(resp.id);
    const hasCoords = typeof resp.latitude === 'number' && typeof resp.longitude === 'number';
    setResponderForm({
      name: resp.name || '',
      role: resp.role || 'Paramedic',
      organization: resp.organization || '',
      phone: resp.phone || '',
      email: resp.email || '',
      skills: resp.skills || 'CPR, First Aid',
      is_available: resp.is_available !== false,
      is_active: resp.is_active !== false,
      includeCoordinates: hasCoords,
      latitude: hasCoords ? String(resp.latitude) : '',
      longitude: hasCoords ? String(resp.longitude) : '',
      location_source: resp.location_source || 'manual',
      location_accuracy_m: typeof resp.location_accuracy_m === 'number' ? resp.location_accuracy_m : null
    });
    setResponderError('');
    setShowResponderModal(true);
  };

  const handleAcquireGpsForResponderForm = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setResponderError('Browser Geolocation API is unavailable in this environment. Enter manual coordinates or leave coordinates unset.');
      return;
    }
    setResponderError('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude.toFixed(6);
        const lon = pos.coords.longitude.toFixed(6);
        const accuracy = pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null;
        let warning = '';
        if (accuracy && accuracy > 500) {
          warning = ` Note: Coarse GPS accuracy reading (±${accuracy}m). Outdoor clear sky line-of-sight recommended.`;
        }
        setResponderForm((prev) => ({
          ...prev,
          includeCoordinates: true,
          latitude: lat,
          longitude: lon,
          location_source: 'browser_gps',
          location_accuracy_m: accuracy
        }));
        if (warning) {
          setResponderError(warning);
        }
      },
      (err) => {
        let msg = 'GPS acquisition failed.';
        if (err.code === 1) {
          msg = 'Location permission denied by user or browser. No fake coordinates were substituted. Please enable location permissions in browser settings or enter verified coordinates manually.';
        } else if (err.code === 2) {
          msg = 'GPS location unavailable from device sensors. No fake coordinates were substituted. Check device location services or enter verified coordinates manually.';
        } else if (err.code === 3) {
          msg = 'GPS acquisition timed out (10s limit). No fake coordinates were substituted. Please retry or enter verified coordinates manually.';
        } else {
          msg = `GPS error (${err.message || 'unknown'}). No fake coordinates were substituted.`;
        }
        setResponderError(msg);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleSubmitResponder = async (e) => {
    e.preventDefault();
    setSubmittingResponder(true);
    setResponderError('');

    const phoneCheck = validatePhoneNumber(responderForm.phone, { required: true });
    if (!phoneCheck.valid) {
      setResponderError(phoneCheck.error);
      setSubmittingResponder(false);
      return;
    }

    try {
      let lat = null;
      let lon = null;
      let locSource = 'unconfigured';
      let locAccuracy = null;

      if (responderForm.includeCoordinates) {
        const parsedLat = parseFloat(responderForm.latitude);
        const parsedLon = parseFloat(responderForm.longitude);
        if (Number.isNaN(parsedLat) || Number.isNaN(parsedLon)) {
          setResponderError('Please enter valid numeric latitude and longitude, or uncheck "Set Responder Coordinates".');
          setSubmittingResponder(false);
          return;
        }
        lat = parsedLat;
        lon = parsedLon;
        locSource = responderForm.location_source === 'browser_gps' ? 'browser_gps' : 'manual';
        locAccuracy = responderForm.location_accuracy_m || null;
      }

      const payload = {
        name: responderForm.name.trim(),
        role: responderForm.role.trim(),
        organization: responderForm.organization.trim() || null,
        phone: phoneCheck.normalized,
        email: responderForm.email.trim() || null,
        skills: responderForm.skills.trim() || 'First Aid',
        is_available: Boolean(responderForm.is_available),
        is_active: Boolean(responderForm.is_active),
        latitude: lat,
        longitude: lon,
        location_source: locSource,
        location_accuracy_m: locAccuracy
      };

      if (editingResponderId) {
        await updateResponder(editingResponderId, payload);
        setNotice({ type: 'success', text: `Updated responder profile for ${payload.name}.` });
      } else {
        await createResponder(payload);
        setNotice({ type: 'success', text: `Created responder profile for ${payload.name}.` });
      }

      setShowResponderModal(false);
      await onRefresh();
    } catch (err) {
      setResponderError(err.message || 'Failed to save responder');
    } finally {
      setSubmittingResponder(false);
    }
  };

  const handleOpenLocationModal = (resp) => {
    setLocModalResponder(resp);
    setLocForm({
      latitude: typeof resp.latitude === 'number' ? String(resp.latitude) : '',
      longitude: typeof resp.longitude === 'number' ? String(resp.longitude) : '',
      location_source: resp.location_source === 'browser_gps' ? 'browser_gps' : 'manual',
      location_accuracy_m: typeof resp.location_accuracy_m === 'number' ? resp.location_accuracy_m : null,
      is_available: resp.is_available !== false
    });
    setGpsStatus('');
  };

  const handleAcquireLiveGpsModal = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setGpsStatus('Browser Geolocation API is unavailable in this environment. Enter manual coordinates below.');
      return;
    }
    setGpsAcquiring(true);
    setGpsStatus('Requesting live Browser GPS fix...');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude.toFixed(6);
        const lon = pos.coords.longitude.toFixed(6);
        const accuracy = pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null;
        const timeStr = new Date(pos.timestamp || Date.now()).toLocaleTimeString();
        setLocForm((prev) => ({
          ...prev,
          latitude: lat,
          longitude: lon,
          location_source: 'browser_gps',
          location_accuracy_m: accuracy
        }));
        setGpsAcquiring(false);
        const accuracyStr = accuracy ? ` • Reported Accuracy: ±${accuracy}m` : '';
        const warning = accuracy && accuracy > 500 ? ' (Warning: Coarse reading. Outdoor clear sky line-of-sight recommended)' : '';
        setGpsStatus(`Verified Browser GPS acquired: (${lat}, ${lon})${accuracyStr} at ${timeStr}${warning}`);
      },
      (err) => {
        setGpsAcquiring(false);
        let msg = '';
        if (err.code === 1) {
          msg = 'Location permission denied by user or browser. No fake coordinates were substituted. Please enable browser location permission or enter manual coordinates.';
        } else if (err.code === 2) {
          msg = 'GPS location unavailable from device sensors. No default coordinates were substituted. Enter manual coordinates below.';
        } else if (err.code === 3) {
          msg = 'GPS acquisition timed out (10s limit). No default coordinates were substituted. Please retry or enter manual coordinates.';
        } else {
          msg = `GPS unavailable (${err.message || 'sensor error'}). No default coordinates were substituted.`;
        }
        setGpsStatus(msg);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleSaveLocationUpdate = async (e) => {
    e.preventDefault();
    if (!locModalResponder) return;
    const parsedLat = parseFloat(locForm.latitude);
    const parsedLon = parseFloat(locForm.longitude);
    if (Number.isNaN(parsedLat) || Number.isNaN(parsedLon)) {
      setGpsStatus('Valid numeric latitude and longitude are required.');
      return;
    }

    setSavingLocation(true);
    try {
      await updateResponderLocation(locModalResponder.id, {
        latitude: parsedLat,
        longitude: parsedLon,
        location_source: locForm.location_source || 'manual',
        location_accuracy_m: locForm.location_accuracy_m || null,
        is_available: Boolean(locForm.is_available)
      });
      const accText = locForm.location_accuracy_m ? ` ±${locForm.location_accuracy_m}m` : '';
      setNotice({
        type: 'success',
        text: `Updated real coordinates for ${locModalResponder.name}: (${parsedLat}, ${parsedLon}) [${locForm.location_source}${accText}].`
      });
      setLocModalResponder(null);
      await onRefresh();
    } catch (err) {
      setGpsStatus(err.message || 'Failed to update responder coordinates.');
    } finally {
      setSavingLocation(false);
    }
  };

  const handleToggleResponderActive = async (resp) => {
    setNotice(null);
    try {
      const nextActive = resp.is_active === false;
      await updateResponder(resp.id, { is_active: nextActive });
      setNotice({
        type: 'success',
        text: `${resp.name} marked ${nextActive ? 'Active' : 'Inactive'}.`
      });
      await onRefresh();
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Failed to update responder status.' });
    }
  };

  const handleToggleResponderAvailability = async (resp) => {
    setNotice(null);
    try {
      const nextAvail = !resp.is_available;
      if (isAdmin) {
        await updateResponder(resp.id, { is_available: nextAvail });
      } else if (typeof resp.latitude === 'number' && typeof resp.longitude === 'number') {
        await updateResponderLocation(resp.id, {
          latitude: resp.latitude,
          longitude: resp.longitude,
          location_source: resp.location_source || 'manual',
          is_available: nextAvail
        });
      }
      setNotice({
        type: 'success',
        text: `${resp.name} availability set to ${nextAvail ? 'Available' : 'Busy / Off-Duty'}.`
      });
      await onRefresh();
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Failed to update availability.' });
    }
  };

  const handleDeleteOrDeactivateResponder = async (resp) => {
    if (!window.confirm(`Remove or deactivate responder ${resp.name}?`)) return;
    setNotice(null);
    try {
      const res = await deleteOrDeactivateResponder(resp.id, true);
      setNotice({ type: 'success', text: res.detail || `${resp.name} updated.` });
      await onRefresh();
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Failed to remove responder.' });
    }
  };

  const handleSendTestNotification = async (e) => {
    e.preventDefault();
    setTestError('');
    setTestResult(null);

    if (!confirmTestSend) {
      setTestError('Please check the confirmation box to authorize sending a live test notification.');
      return;
    }
    if (!testRecipient.trim()) {
      setTestError('Please enter a real recipient email address or phone number.');
      return;
    }

    let finalRecipient = testRecipient.trim();
    if (testChannel === 'SMS') {
      const phoneCheck = validatePhoneNumber(finalRecipient, { required: true });
      if (!phoneCheck.valid) {
        setTestError(phoneCheck.error);
        return;
      }
      finalRecipient = phoneCheck.normalized;
    }

    setSendingTest(true);
    try {
      const res = await sendTestNotification({
        channel: testChannel,
        recipient: finalRecipient,
        confirm_send: true
      });
      setTestResult(res);
      if (onNotifConfigUpdated) {
        const refreshedCfg = await getNotificationConfig().catch(() => null);
        if (refreshedCfg) onNotifConfigUpdated(refreshedCfg);
      }
    } catch (err) {
      setTestError(err.message || 'Test notification request failed.');
    } finally {
      setSendingTest(false);
    }
  };

  const visibleResponders = responders.filter((r) => {
    // Strictly exclude demo/seed responders from authorized production list
    if (r.is_demo) return false;
    // Hide inactive responders unless explicitly enabled by admin
    if (!showInactive && r.is_active === false) return false;
    return true;
  });

  const latestTest = testResult || notifConfig?.last_test_result || null;

  return (
    <div>
      {/* Platform Reviewer Subtabs */}
      {isReviewer && (
        <div style={{
          display: 'flex',
          background: 'var(--color-surface-elevated)',
          borderRadius: '8px',
          padding: '4px',
          marginBottom: '1.25rem',
          border: '1px solid var(--color-border)',
          maxWidth: '560px'
        }}>
          <button
            type="button"
            onClick={() => setActiveSubTab('profiles')}
            style={{
              flex: 1,
              padding: '0.5rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              background: activeSubTab === 'profiles' ? 'var(--color-primary)' : 'transparent',
              color: activeSubTab === 'profiles' ? 'var(--color-on-primary)' : 'var(--color-text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.4rem'
            }}
          >
            <UserCheck size={14} /> Active Responders ({visibleResponders.length})
          </button>
          <button
            type="button"
            onClick={() => { setActiveSubTab('applications'); loadApplications(); }}
            style={{
              flex: 1.2,
              padding: '0.5rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              background: activeSubTab === 'applications' ? 'var(--color-primary)' : 'transparent',
              color: activeSubTab === 'applications' ? 'var(--color-on-primary)' : 'var(--color-text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.4rem'
            }}
          >
            <Shield size={14} /> Review Applications ({applications.filter(a => a.status === 'PENDING').length})
          </button>
        </div>
      )}

      {/* Global Notice */}
      {notice && (
        <div
          style={{
            background: notice.type === 'error' ? 'var(--color-danger-soft)' : 'var(--color-success-soft)',
            border: `1px solid ${notice.type === 'error' ? 'var(--color-danger)' : 'var(--color-success)'}`,
            color: notice.type === 'error' ? 'var(--color-danger)' : 'var(--color-success)',
            padding: '0.65rem 0.95rem',
            borderRadius: '8px',
            marginBottom: '1.25rem',
            fontSize: '0.82rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            {notice.type === 'error' ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
            <span>{notice.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setNotice(null)}
            style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {activeSubTab === 'applications' ? (
        <div className="fc-panel" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.25rem' }}>
            <div>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Shield size={18} color="#38bdf8" /> Community First-Responder Applications
              </h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Authorized reviewer queue. Vetting credentials protects family safety before granting incident access.
              </p>
            </div>
            <button
              type="button"
              className="btn-secondary"
              onClick={loadApplications}
              disabled={appsLoading}
              style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
            >
              {appsLoading ? 'Refreshing...' : '↻ Refresh Queue'}
            </button>
          </div>

          {applications.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem 1rem', color: '#94a3b8' }}>
              <FileCheck size={40} color="#38bdf8" style={{ marginBottom: '0.75rem', opacity: 0.7 }} />
              <p style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600, color: '#f1f5f9' }}>
                No Responder Applications Found
              </p>
              <p style={{ margin: '0.35rem 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                When community first responders submit their credentials, they will appear here for verification.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {applications.map((app) => {
                const isPending = app.status === 'PENDING';
                const isApproved = app.status === 'APPROVED';
                const isRejected = app.status === 'REJECTED';
                const statusColor = isPending ? '#fbbf24' : isApproved ? '#34d399' : '#f87171';
                const statusBg = isPending ? 'rgba(245, 158, 11, 0.15)' : isApproved ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';

                return (
                  <div
                    key={app.id}
                    style={{
                      background: 'rgba(15, 23, 42, 0.6)',
                      border: '1px solid rgba(148, 163, 184, 0.2)',
                      borderRadius: '8px',
                      padding: '1.15rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.85rem'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                            {app.applicant_name}
                          </h3>
                          <span style={{
                            background: statusBg,
                            color: statusColor,
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.7rem',
                            fontWeight: 700
                          }}>
                            {app.status}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.82rem', color: '#cbd5e1', marginTop: '0.25rem' }}>
                          <strong>{app.organization}</strong> {app.badge_id ? `• Badge/ID: ${app.badge_id}` : ''}
                        </div>
                      </div>

                      <div style={{ fontSize: '0.72rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <Clock size={12} />
                        <span>Submitted {new Date(app.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <Mail size={13} color="var(--color-primary)" />
                        <span style={{ color: 'var(--text-primary)' }}>{maskEmail(app.email, { isDemo: isDemoEntity(app), demoSeed: app.name })}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <Phone size={13} color="#059669" />
                        <span style={{ color: 'var(--text-primary)' }}>{maskPhoneNumber(app.phone, { isDemo: isDemoEntity(app), demoSeed: app.id })}</span>
                      </div>
                      {app.skills && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', gridColumn: '1 / -1' }}>
                          <span style={{ color: 'var(--text-secondary)' }}><strong style={{ color: 'var(--text-primary)' }}>Skills:</strong> {app.skills}</span>
                        </div>
                      )}
                    </div>

                    {app.review_notes && (
                      <div style={{
                        background: 'rgba(15, 23, 42, 0.4)',
                        border: '1px solid rgba(148, 163, 184, 0.15)',
                        borderRadius: '6px',
                        padding: '0.55rem 0.75rem',
                        fontSize: '0.78rem',
                        color: '#cbd5e1'
                      }}>
                        <strong>Review Notes:</strong> {app.review_notes}
                      </div>
                    )}

                    {isPending && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginTop: '0.4rem', borderTop: '1px solid rgba(148, 163, 184, 0.15)', paddingTop: '0.85rem' }}>
                        <input
                          type="text"
                          className="form-input"
                          style={{ fontSize: '0.8rem', padding: '0.45rem 0.75rem' }}
                          placeholder="Optional reviewer notes (shared with applicant via email)..."
                          value={reviewNotes[app.id] || ''}
                          onChange={(e) => setReviewNotes({ ...reviewNotes, [app.id]: e.target.value })}
                          disabled={reviewActionLoading === app.id}
                        />
                        <div style={{ display: 'flex', gap: '0.65rem', justifyContent: 'flex-end' }}>
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#f87171', fontSize: '0.8rem', padding: '0.4rem 0.85rem' }}
                            onClick={() => handleReviewDecision(app.id, 'REJECT')}
                            disabled={reviewActionLoading === app.id}
                          >
                            <XCircle size={14} /> Reject Application
                          </button>
                          <button
                            type="button"
                            className="btn-primary"
                            style={{ background: '#16a34a', borderColor: '#15803d', fontSize: '0.8rem', padding: '0.4rem 0.95rem' }}
                            onClick={() => handleReviewDecision(app.id, 'APPROVE')}
                            disabled={reviewActionLoading === app.id}
                          >
                            <CheckCircle2 size={14} /> Approve &amp; Activate
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Section 1: Notification Configuration & Explicit Live Test Screen (Phase 6 Section 7) */}
          {user?.role !== 'responder' && (
            <div className="fc-panel" style={{ marginBottom: '1.25rem', borderLeft: '3px solid #38bdf8' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.85rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <Bell size={17} color="#38bdf8" /> Notification Provider Status &amp; Explicit Live Test
                  </h2>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                    Verify SMTP / Resend email or Twilio SMS configuration with an explicit user-confirmed test message. No fallback or placeholder addresses are ever used.
                  </p>
                </div>

                {notifConfig && (
                  <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                <span style={{
                  fontSize: '0.72rem',
                  padding: '0.2rem 0.55rem',
                  borderRadius: '5px',
                  background: notifConfig.email_provider !== 'unconfigured' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                  color: notifConfig.email_provider !== 'unconfigured' ? '#34d399' : '#f87171',
                  border: '1px solid rgba(148, 163, 184, 0.25)',
                  fontWeight: 700
                }}>
                  Email Provider: {notifConfig.email_provider}
                </span>
                <span style={{
                  fontSize: '0.72rem',
                  padding: '0.2rem 0.55rem',
                  borderRadius: '5px',
                  background: notifConfig.sms_provider !== 'unconfigured' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                  color: notifConfig.sms_provider !== 'unconfigured' ? '#34d399' : '#fbbf24',
                  border: '1px solid rgba(148, 163, 184, 0.25)',
                  fontWeight: 700
                }}>
                  SMS Provider: {notifConfig.sms_provider}
                </span>
              </div>
            )}
          </div>

          {/* Most Recent Test Status */}
          {latestTest && (
            <div style={{
              background: latestTest.status === 'DELIVERED' || latestTest.status === 'SENT'
                ? 'rgba(16, 185, 129, 0.12)'
                : 'rgba(239, 68, 68, 0.12)',
              border: `1px solid ${latestTest.status === 'DELIVERED' || latestTest.status === 'SENT' ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)'}`,
              borderRadius: '6px',
              padding: '0.6rem 0.8rem',
              marginBottom: '0.85rem',
              fontSize: '0.78rem',
              color: 'var(--text-primary)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.4rem' }}>
                <strong style={{
                  color: latestTest.status === 'DELIVERED' || latestTest.status === 'SENT' ? '#34d399' : '#f87171',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem'
                }}>
                  {latestTest.status === 'DELIVERED' || latestTest.status === 'SENT'
                    ? <CheckCircle2 size={14} />
                    : <AlertTriangle size={14} />}
                  Most Recent Test Result: {latestTest.status} via {latestTest.provider} ({latestTest.channel})
                </strong>
                {latestTest.tested_at && (
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    Tested at: {new Date(latestTest.tested_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
              <div style={{ marginTop: '0.2rem', fontSize: '0.74rem', color: '#cbd5e1' }}>
                Recipient: <strong>{latestTest.recipient}</strong>
                {latestTest.provider_message_id ? ` • Provider Msg ID: ${latestTest.provider_message_id}` : ''}
                {latestTest.error_message ? ` • Diagnostic: ${latestTest.error_message}` : ''}
              </div>
            </div>
          )}

          {testError && (
            <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#fca5a5', padding: '0.55rem 0.75rem', borderRadius: '6px', marginBottom: '0.75rem', fontSize: '0.78rem' }}>
              {testError}
            </div>
          )}

          <form onSubmit={handleSendTestNotification} style={{ display: 'grid', gridTemplateColumns: '140px 1fr auto', gap: '0.65rem', alignItems: 'end' }}>
            <div>
              <label className="form-label" htmlFor="test-channel" style={{ fontSize: '0.72rem' }}>Channel</label>
              <select
                id="test-channel"
                className="form-select"
                value={testChannel}
                onChange={(e) => setTestChannel(e.target.value)}
              >
                <option value="EMAIL">EMAIL</option>
                <option value="SMS">SMS</option>
              </select>
            </div>
            <div>
              <label className="form-label" htmlFor="test-recipient" style={{ fontSize: '0.72rem' }}>
                Destination {testChannel === 'EMAIL' ? 'Email Address' : 'Phone Number'}
              </label>
              <input
                id="test-recipient"
                type={testChannel === 'EMAIL' ? 'email' : 'text'}
                className="form-input"
                placeholder={testChannel === 'EMAIL' ? 'Enter real email address to test' : '+91 98765 43210'}
                value={testRecipient}
                onChange={(e) => setTestRecipient(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className="btn-primary"
              disabled={sendingTest || !confirmTestSend}
              style={{ height: '38px' }}
            >
              <Send size={13} /> {sendingTest ? 'Sending Test...' : 'Send Explicit Test'}
            </button>
          </form>

          <div style={{ marginTop: '0.55rem' }}>
            <label
              htmlFor="confirm-test-send"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
                cursor: sendingTest ? 'not-allowed' : 'pointer',
                fontWeight: 500
              }}
            >
              <input
                id="confirm-test-send"
                type="checkbox"
                checked={confirmTestSend}
                disabled={sendingTest}
                onChange={(e) => setConfirmTestSend(e.target.checked)}
                style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }}
              />
              <span style={{ color: 'var(--text-primary)' }}>
                I explicitly confirm sending a test notification to the destination entered above.
              </span>
            </label>
          </div>
        </div>
      )}

      {/* Section 2: Responder Management Toolbar */}
      <div className="toolbar-strip" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Authorized Emergency Responders &amp; Real Geolocation
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.15rem' }}>
            Responders are ranked by Haversine distance only when both incident and responder coordinates are verified
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            <span>Show Inactive Responders</span>
          </label>

          {isAdmin && (
            <button
              type="button"
              className="btn-primary"
              onClick={handleOpenAddResponder}
            >
              <Plus size={15} /> Add Responder
            </button>
          )}
        </div>
      </div>

      {notice && (
        <div
          style={{
            background: notice.type === 'error' ? 'rgba(239, 68, 68, 0.16)' : 'rgba(16, 185, 129, 0.14)',
            border: `1px solid ${notice.type === 'error' ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.35)'}`,
            color: notice.type === 'error' ? '#fca5a5' : '#6ee7b7',
            padding: '0.6rem 0.85rem',
            borderRadius: '8px',
            marginBottom: '1rem',
            fontSize: '0.8rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
        >
          <span>{notice.text}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Responder Cards Grid or Clear Empty State */}
      {visibleResponders.length === 0 ? (
        <div
          className="fc-panel"
          style={{
            textAlign: 'center',
            padding: '3rem 1.5rem',
            borderRadius: '8px',
            border: '1px dashed var(--border-subtle)',
            background: 'var(--bg-secondary)',
            color: '#94a3b8'
          }}
        >
          <Shield size={44} color="#38bdf8" style={{ margin: '0 auto 0.85rem', opacity: 0.8 }} />
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
            No Authorized Emergency Responders Found
          </h3>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8', maxWidth: '520px', margin: '0 auto 1.25rem', lineHeight: 1.5 }}>
            There are currently no active, verified community responders configured for this household or area.
            Community responders can apply through the responder onboarding workflow, and platform reviewers can inspect and approve credentials.
          </p>
          {isAdmin && (
            <button
              type="button"
              className="btn-primary"
              onClick={handleOpenAddResponder}
              style={{ margin: '0 auto' }}
            >
              <Plus size={15} /> Add Authorized Responder
            </button>
          )}
        </div>
      ) : (
        <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))' }}>
          {visibleResponders.map((resp) => {
            const hasValidCoords = typeof resp.latitude === 'number' && typeof resp.longitude === 'number';
            const isInactive = resp.is_active === false;
            const canUpdateLoc = canUpdateResponderLocation(resp);
            const locAgeMinutes = resp.location_updated_at
              ? Math.round((Date.now() - new Date(resp.location_updated_at).getTime()) / 60000)
              : null;
            const isStaleLoc = hasValidCoords && locAgeMinutes !== null && locAgeMinutes > 60;

            return (
              <div
                key={resp.id}
                className="fc-panel"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  opacity: isInactive ? 0.65 : 1
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.65rem' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                        <h3 style={{ fontSize: '1.02rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {resp.name}
                        </h3>
                        {resp.is_demo && (
                          <span style={{
                            fontSize: '0.62rem',
                            padding: '0.08rem 0.38rem',
                            borderRadius: '4px',
                            background: 'rgba(245, 158, 11, 0.15)',
                            color: '#fbbf24',
                            border: '1px solid rgba(245, 158, 11, 0.35)',
                            fontWeight: 700
                          }}>
                            DEMO SEED
                          </span>
                        )}
                        {isInactive && (
                          <span style={{
                            fontSize: '0.62rem',
                            padding: '0.08rem 0.38rem',
                            borderRadius: '4px',
                            background: 'rgba(239, 68, 68, 0.15)',
                            color: '#f87171',
                            border: '1px solid rgba(239, 68, 68, 0.35)',
                            fontWeight: 700
                          }}>
                            INACTIVE
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: '#38bdf8', fontWeight: 600, marginTop: '0.1rem' }}>
                        {resp.role}
                        {resp.organization ? ` • ${resp.organization}` : ''}
                      </div>
                    </div>

                    <span style={{
                      fontSize: '0.68rem',
                      padding: '0.15rem 0.5rem',
                      borderRadius: '5px',
                      background: resp.is_available ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: resp.is_available ? '#34d399' : '#fbbf24',
                      border: `1px solid ${resp.is_available ? 'rgba(16, 185, 129, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                      fontWeight: 700
                    }}>
                      {resp.is_available ? '● AVAILABLE' : '● BUSY / OFF-DUTY'}
                    </span>
                  </div>

                  {/* Contact & Capabilities */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.65rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                      <Phone size={12} color="var(--color-primary)" />
                      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {maskPhoneNumber(resp.phone, { isDemo: resp.is_demo, demoSeed: resp.id })}
                      </span>
                      {resp.is_demo && (
                        <span style={{
                          fontSize: '0.62rem',
                          padding: '0.05rem 0.3rem',
                          borderRadius: '3px',
                          background: 'var(--amber-500-bg)',
                          color: 'var(--amber-500)',
                          border: '1px solid var(--amber-border)',
                          fontWeight: 700
                        }}>
                          DEMO
                        </span>
                      )}
                    </div>
                    {resp.email && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <Mail size={12} color="var(--color-primary)" />
                        <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                          {maskEmail(resp.email, { isDemo: resp.is_demo, demoSeed: resp.name })}
                        </span>
                      </div>
                    )}
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                      <strong style={{ color: 'var(--text-primary)' }}>Capabilities:</strong> {resp.skills}
                    </div>
                  </div>

                  {/* Real Geolocation Box */}
                  <div style={{
                    background: 'var(--bg-secondary)',
                    border: hasValidCoords ? '1px solid var(--border-subtle)' : '1px dashed rgba(245, 158, 11, 0.45)',
                    borderRadius: '6px',
                    padding: '0.55rem 0.7rem',
                    fontSize: '0.75rem',
                    marginBottom: '0.8rem'
                  }}>
                    {hasValidCoords ? (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.3rem' }}>
                          <span style={{ color: '#34d399', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <MapPin size={12} /> ({resp.latitude.toFixed(5)}, {resp.longitude.toFixed(5)})
                          </span>
                          <span style={{ fontSize: '0.66rem', color: '#38bdf8', background: 'rgba(56, 189, 248, 0.12)', padding: '0.08rem 0.35rem', borderRadius: '4px' }}>
                            {resp.location_source === 'browser_gps' ? 'Browser GPS' : resp.location_source === 'manual_coordinates' ? 'Manual Coords' : (resp.location_source || 'manual')}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
                          <Clock size={10} />
                          <span>
                            {resp.location_updated_at
                              ? `Updated: ${new Date(resp.location_updated_at).toLocaleString()}`
                              : 'Timestamp not recorded'}
                          </span>
                          {resp.location_accuracy_m != null && (
                            <span style={{ color: '#94a3b8' }}>• ±{Math.round(resp.location_accuracy_m)}m accuracy</span>
                          )}
                          {isStaleLoc && (
                            <span style={{ color: '#fbbf24', fontWeight: 600 }}>• Stale (&gt;1h)</span>
                          )}
                        </div>
                      </>
                    ) : (
                      <div style={{ color: '#fbbf24', display: 'flex', alignItems: 'flex-start', gap: '0.4rem' }}>
                        <AlertTriangle size={13} style={{ marginTop: '2px', flexShrink: 0 }} />
                        <div>
                          <strong>Coordinates Not Set:</strong> Excluded from Haversine distance ranking until real GPS or manual coordinates are configured.
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Action Buttons */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {canUpdateLoc && (
                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ flex: 1, justifyContent: 'center', fontSize: '0.73rem', padding: '0.32rem 0.5rem', borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}
                        onClick={() => handleOpenLocationModal(resp)}
                      >
                        <Navigation size={12} /> Set GPS / Coords
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ fontSize: '0.73rem', padding: '0.32rem 0.5rem' }}
                        onClick={() => handleToggleResponderAvailability(resp)}
                      >
                        {resp.is_available ? 'Mark Busy' : 'Mark Available'}
                      </button>
                    </div>
                  )}

                  {isAdmin && (
                    <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="btn-secondary responder-action-btn"
                        style={{ flex: 1, minWidth: '90px', justifyContent: 'center', fontSize: '0.73rem', padding: '0.3rem 0.5rem' }}
                        onClick={() => handleOpenEditResponder(resp)}
                      >
                        <Edit2 size={12} /> Edit
                      </button>
                      <button
                        type="button"
                        className="btn-secondary responder-action-btn"
                        style={{ fontSize: '0.73rem', padding: '0.3rem 0.5rem' }}
                        onClick={() => handleToggleResponderActive(resp)}
                      >
                        <Power size={12} /> {isInactive ? 'Activate' : 'Deactivate'}
                      </button>
                      <button
                        type="button"
                        className="btn-danger-outline responder-action-icon-btn destructive-action-btn"
                        style={{ fontSize: '0.73rem', padding: '0.3rem 0.5rem' }}
                        onClick={() => handleDeleteOrDeactivateResponder(resp)}
                        title="Delete responder"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add / Edit Responder Modal */}
      {showResponderModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="resp-modal-title">
          <div className="modal-content" style={{ maxWidth: '580px' }}>
            <div className="modal-header">
              <h3 id="resp-modal-title" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {editingResponderId ? 'Edit Responder Profile' : 'Register Responder Profile'}
              </h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setShowResponderModal(false)}
              >
                ✕
              </button>
            </div>

            {responderError && (
              <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', padding: '0.65rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.8rem' }}>
                {responderError}
              </div>
            )}

            <form onSubmit={handleSubmitResponder}>
              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="resp-name">Full Name / Unit Callsign *</label>
                  <input
                    id="resp-name"
                    type="text"
                    required
                    className="form-input"
                    placeholder="Enter responder name"
                    value={responderForm.name}
                    onChange={(e) => setResponderForm({ ...responderForm, name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="resp-role">Role / Qualification *</label>
                  <input
                    id="resp-role"
                    type="text"
                    required
                    className="form-input"
                    placeholder="Paramedic, Physician, First Responder"
                    value={responderForm.role}
                    onChange={(e) => setResponderForm({ ...responderForm, role: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="resp-org">Organization / Agency (Optional)</label>
                  <input
                    id="resp-org"
                    type="text"
                    className="form-input"
                    placeholder="City EMS, Community CERT, Hospital"
                    value={responderForm.organization}
                    onChange={(e) => setResponderForm({ ...responderForm, organization: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="resp-phone">Phone Number (+91) *</label>
                  <input
                    id="resp-phone"
                    type="text"
                    required
                    className="form-input"
                    placeholder="+91 98765 43210"
                    value={responderForm.phone}
                    onChange={(e) => setResponderForm({ ...responderForm, phone: e.target.value })}
                  />
                  <span style={{ fontSize: '0.7rem', color: '#64748b', display: 'block', marginTop: '0.2rem' }}>
                    Default: India (+91). Accepts 10 digits or with country code.
                  </span>
                </div>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="resp-email">Email Address (Optional)</label>
                  <input
                    id="resp-email"
                    type="email"
                    className="form-input"
                    placeholder="responder@agency.org"
                    value={responderForm.email}
                    onChange={(e) => setResponderForm({ ...responderForm, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="resp-skills">Clinical / Rescue Capabilities</label>
                  <input
                    id="resp-skills"
                    type="text"
                    className="form-input"
                    placeholder="CPR, AED, Trauma, First Aid"
                    value={responderForm.skills}
                    onChange={(e) => setResponderForm({ ...responderForm, skills: e.target.value })}
                  />
                </div>
              </div>

              {/* Optional Real Coordinates Section */}
              <div style={{
                background: 'var(--bg-secondary)',
                padding: '0.85rem',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                marginBottom: '0.85rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={responderForm.includeCoordinates}
                      onChange={(e) => setResponderForm({ ...responderForm, includeCoordinates: e.target.checked })}
                    />
                    <span>Set Verified Geographic Coordinates</span>
                  </label>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '0.72rem', padding: '0.22rem 0.55rem' }}
                    onClick={handleAcquireGpsForResponderForm}
                  >
                    <Navigation size={11} /> Acquire Browser GPS
                  </button>
                </div>

                {responderForm.includeCoordinates ? (
                  <>
                    <div className="form-row-2col" style={{ marginTop: '0.65rem' }}>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label" htmlFor="resp-lat">Latitude (-90 to 90) *</label>
                        <input
                          id="resp-lat"
                          type="number"
                          step="any"
                          min="-90"
                          max="90"
                          required
                          className="form-input"
                          placeholder="e.g. 37.7749"
                          value={responderForm.latitude}
                          onChange={(e) => setResponderForm({ ...responderForm, latitude: e.target.value, location_source: 'manual' })}
                        />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label" htmlFor="resp-lon">Longitude (-180 to 180) *</label>
                        <input
                          id="resp-lon"
                          type="number"
                          step="any"
                          min="-180"
                          max="180"
                          required
                          className="form-input"
                          placeholder="e.g. -122.4194"
                          value={responderForm.longitude}
                          onChange={(e) => setResponderForm({ ...responderForm, longitude: e.target.value, location_source: 'manual' })}
                        />
                      </div>
                    </div>
                    {responderForm.location_accuracy_m && (
                      <div style={{ fontSize: '0.7rem', color: '#38bdf8', marginTop: '0.35rem' }}>
                        Acquired Accuracy: ±{responderForm.location_accuracy_m}m ({responderForm.location_source === 'browser_gps' ? 'Browser GPS' : 'Manual'})
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.4rem', marginBottom: 0 }}>
                    Coordinates left unset. No default or random coordinates will be assigned.
                  </p>
                )}
              </div>

              <div style={{ display: 'flex', gap: '1.25rem', marginBottom: '1rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={responderForm.is_available}
                    onChange={(e) => setResponderForm({ ...responderForm, is_available: e.target.checked })}
                  />
                  <span>Available for Dispatch</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={responderForm.is_active}
                    onChange={(e) => setResponderForm({ ...responderForm, is_active: e.target.checked })}
                  />
                  <span>Active Responder</span>
                </label>
              </div>

              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowResponderModal(false)}
                  disabled={submittingResponder}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submittingResponder}
                  style={{ flex: 1, justifyContent: 'center' }}
                >
                  {submittingResponder ? 'Saving...' : editingResponderId ? 'Update Responder' : 'Save Responder'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Responder Location Update Modal */}
      {locModalResponder && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="loc-modal-title">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <div>
                <h3 id="loc-modal-title" style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Update Location: {locModalResponder.name}
                </h3>
                <p style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  Acquire live Browser GPS or enter verified manual coordinates
                </p>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setLocModalResponder(null)}
              >
                ✕
              </button>
            </div>

            <div style={{ marginBottom: '0.85rem' }}>
              <button
                type="button"
                className="btn-secondary"
                style={{ width: '100%', justifyContent: 'center', borderColor: 'rgba(56, 189, 248, 0.45)', color: '#38bdf8' }}
                onClick={handleAcquireLiveGpsModal}
                disabled={gpsAcquiring}
              >
                <Navigation size={14} />
                {gpsAcquiring ? 'Acquiring Browser GPS...' : 'Acquire Live Browser GPS Coordinates'}
              </button>
              {gpsStatus && (
                <div style={{ fontSize: '0.74rem', color: '#cbd5e1', marginTop: '0.45rem', padding: '0.45rem 0.6rem', background: 'var(--bg-primary)', borderRadius: '6px' }}>
                  {gpsStatus}
                </div>
              )}
            </div>

            <form onSubmit={handleSaveLocationUpdate}>
              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="upd-lat">Latitude (-90 to 90) *</label>
                  <input
                    id="upd-lat"
                    type="number"
                    step="any"
                    min="-90"
                    max="90"
                    required
                    className="form-input"
                    value={locForm.latitude}
                    onChange={(e) => setLocForm({ ...locForm, latitude: e.target.value, location_source: 'manual' })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="upd-lon">Longitude (-180 to 180) *</label>
                  <input
                    id="upd-lon"
                    type="number"
                    step="any"
                    min="-180"
                    max="180"
                    required
                    className="form-input"
                    value={locForm.longitude}
                    onChange={(e) => setLocForm({ ...locForm, longitude: e.target.value, location_source: 'manual' })}
                  />
                </div>
              </div>

              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  id="upd-avail"
                  type="checkbox"
                  checked={locForm.is_available}
                  onChange={(e) => setLocForm({ ...locForm, is_available: e.target.checked })}
                />
                <label htmlFor="upd-avail" style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  Unit Available for Dispatch
                </label>
              </div>

              <div style={{ display: 'flex', gap: '0.65rem', marginTop: '1rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setLocModalResponder(null)}
                  disabled={savingLocation}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={savingLocation}
                  style={{ flex: 1, justifyContent: 'center' }}
                >
                  {savingLocation ? 'Saving...' : `Save Coordinates (${locForm.location_source})`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      </>
    )}
    </div>
  );
}
