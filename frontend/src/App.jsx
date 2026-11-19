import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  AlertTriangle,
  Radio,
  UserCheck,
  CheckCircle2,
  RefreshCw,
  Info,
  Clock,
  HeartHandshake,
  WifiOff
} from 'lucide-react';
import Header from './components/Header';
import FamilyDashboard from './components/FamilyDashboard';
import EmergencyMonitor from './components/EmergencyMonitor';
import ResponderAndAlertManager from './components/ResponderAndAlertManager';
import AiTriageTester from './components/AiTriageTester';
import FirstAidAssistant from './components/FirstAidAssistant';
import SosTriggerModal from './components/SosTriggerModal';
import LoginScreen from './components/LoginScreen';
import AcceptInviteModal from './components/AcceptInviteModal';
import MobileNav from './components/MobileNav';
import {
  getMembers,
  getEmergencies,
  getResponders,
  getMe,
  logout,
  onUnauthorized,
  getAuthToken,
  connectIncidentWebSocket,
  getNotificationConfig
} from './services/api';

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);

  // Theme state: 'dark' | 'light' | 'system' (default: dark)
  const [themePreference, setThemePreference] = useState(() => {
    if (typeof window === 'undefined') return 'dark';
    try {
      const saved = localStorage.getItem('familyconnect-theme');
      if (saved === 'light' || saved === 'dark' || saved === 'system') {
        return saved;
      }
    } catch (err) {
      console.warn('[Theme] Could not read localStorage:', err);
    }
    return 'dark';
  });

  const [effectiveTheme, setEffectiveTheme] = useState(() => {
    if (typeof window === 'undefined') return 'dark';
    try {
      const saved = localStorage.getItem('familyconnect-theme');
      if (saved === 'light' || saved === 'dark') return saved;
      if (saved === 'system') {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
          return 'light';
        }
        return 'dark';
      }
    } catch (e) {}
    return 'dark';
  });

  // Synchronize effective theme to DOM without triggering app unmount/remount
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const resolveTheme = () => {
      if (themePreference === 'dark') return 'dark';
      if (themePreference === 'light') return 'light';
      if (themePreference === 'system') {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
          return 'light';
        }
        return 'dark';
      }
      return 'dark';
    };

    const applyTheme = () => {
      const resolved = resolveTheme();
      setEffectiveTheme(resolved);
      document.documentElement.setAttribute('data-theme', resolved);
      const metaTheme = document.querySelector('meta[name="theme-color"]');
      if (metaTheme) {
        metaTheme.setAttribute('content', resolved === 'dark' ? '#080c18' : '#ffffff');
      }
    };

    applyTheme();

    let mediaQuery = null;
    const handleMediaChange = () => {
      if (themePreference === 'system') {
        applyTheme();
      }
    };

    if (window.matchMedia) {
      mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', handleMediaChange);
      } else if (mediaQuery.addListener) {
        mediaQuery.addListener(handleMediaChange);
      }
    }

    return () => {
      if (mediaQuery) {
        if (mediaQuery.removeEventListener) {
          mediaQuery.removeEventListener('change', handleMediaChange);
        } else if (mediaQuery.removeListener) {
          mediaQuery.removeListener(handleMediaChange);
        }
      }
    };
  }, [themePreference]);

  const handleThemeChange = (newTheme) => {
    if (newTheme !== 'light' && newTheme !== 'dark' && newTheme !== 'system') return;
    setThemePreference(newTheme);
    try {
      localStorage.setItem('familyconnect-theme', newTheme);
    } catch (err) {
      console.warn('[Theme] Could not write localStorage:', err);
    }
  };

  const [activeTab, setActiveTab] = useState('emergencies');
  const [members, setMembers] = useState([]);
  const [emergencies, setEmergencies] = useState([]);
  const [responders, setResponders] = useState([]);
  const [sosModalOpen, setSosModalOpen] = useState(false);
  const [preselectedMember, setPreselectedMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(null);
  const [bannerAlert, setBannerAlert] = useState(null);
  const [wsState, setWsState] = useState('disconnected'); // 'connected' | 'disconnected' | 'error'
  const [notifConfig, setNotifConfig] = useState(null);
  const [isOnline, setIsOnline] = useState(() => (typeof navigator !== 'undefined' ? navigator.onLine : true));
  const [installPrompt, setInstallPrompt] = useState(null);
  const [isInstalled, setIsInstalled] = useState(false);

  const [inviteToken, setInviteToken] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get('token');
    }
    return null;
  });
  const [pendingSosAction, setPendingSosAction] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get('action') === 'sos';
    }
    return false;
  });

  // Track online/offline status and PWA install prompt lifecycle
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleOnline = () => {
      setIsOnline(true);
      if (user) loadData();
    };
    const handleOffline = () => {
      setIsOnline(false);
    };
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator?.standalone === true;
    if (isStandalone) {
      setIsInstalled(true);
    }

    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setInstallPrompt(e);
    };

    const handleAppInstalled = () => {
      setInstallPrompt(null);
      setIsInstalled(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, [user]);

  const handleInstallClick = async () => {
    if (!installPrompt) return;
    try {
      installPrompt.prompt();
      const choice = await installPrompt.userChoice;
      if (choice && choice.outcome === 'accepted') {
        setInstallPrompt(null);
      }
    } catch {
      // Ignore user dismissal or browser cancellation
    }
  };

  // 1. Session verification on initial load & refresh
  useEffect(() => {
    // Intercept 401 unauthenticated responses
    onUnauthorized(() => {
      setUser(null);
      setMembers([]);
      setEmergencies([]);
      setResponders([]);
    });

    const verifyExistingSession = async () => {
      const token = getAuthToken();
      if (!token) {
        setAuthChecking(false);
        setLoading(false);
        return;
      }

      try {
        const profile = await getMe();
        setUser(profile);
      } catch (err) {
        console.warn('Session verification rejected:', err);
        setUser(null);
      } finally {
        setAuthChecking(false);
      }
    };

    verifyExistingSession();
  }, []);

  // 2. Fetch platform data once user is authenticated
  const loadData = async () => {
    if (!user) return;
    try {
      if (user.role === 'responder') {
        // Responders cannot browse the general family member roster (least-privilege privacy)
        const [emergenciesData, respondersData] = await Promise.all([
          getEmergencies(),
          getResponders(false, true, true)
        ]);
        setEmergencies(emergenciesData);
        setResponders(respondersData);
        setMembers([]);
      } else {
        const [membersData, emergenciesData, respondersData, notifData] = await Promise.all([
          getMembers(true, false),
          getEmergencies(),
          getResponders(false, true, true),
          getNotificationConfig().catch(() => null)
        ]);
        setMembers(membersData);
        setEmergencies(emergenciesData);
        setResponders(respondersData);
        if (notifData) setNotifConfig(notifData);
      }
      setApiError(null);
    } catch (err) {
      console.error('Failed to load platform data:', err);
      setApiError(err.message || 'Unable to connect to FamilyConnect API. Ensure backend is running.');
    } finally {
      setLoading(false);
    }
  };

  // Phase 5C: Real-Time WebSocket coordination + fallback polling
  useEffect(() => {
    if (!user) return;
    loadData();

    const disconnectWs = connectIncidentWebSocket(
      (event) => {
        if (
          [
            'INCIDENT_CREATED',
            'INCIDENT_STATUS_UPDATED',
            'INCIDENT_LOCATION_UPDATED',
            'RESPONDER_STATUS_UPDATED',
            'ALERT_ACKNOWLEDGED',
            'ALERT_UPDATED'
          ].includes(event.event_type)
        ) {
          if (event.event_type === 'INCIDENT_CREATED') {
            const payload = event.payload || {};
            const reporter = payload.reporter_name || 'Family Member';
            const sevLevel = payload.severity_level || 'HIGH';
            const sevScore = payload.severity_score ? ` (${(payload.severity_score * 100).toFixed(0)}% confidence)` : '';
            setBannerAlert({
              type: 'danger',
              message: `Emergency SOS registered for ${reporter}! AI Triage: ${sevLevel}${sevScore}. Nearest responders ranked & trusted contacts processed.`
            });
            setTimeout(() => setBannerAlert(null), 9000);
          } else if (event.event_type === 'INCIDENT_STATUS_UPDATED') {
            const payload = event.payload || {};
            const incId = event.incident_id || payload.incident_id;
            const newStatus = payload.status;
            if (newStatus) {
              setBannerAlert({
                type: 'info',
                message: `Incident #${incId} status updated to ${newStatus}.`
              });
              setTimeout(() => setBannerAlert(null), 7000);
            }
          }
          loadData();
        }
      },
      (state) => {
        setWsState(state);
        if (state === 'connected') {
          loadData();
        }
      }
    );

    const interval = setInterval(loadData, 10000);
    return () => {
      disconnectWs();
      clearInterval(interval);
    };
  }, [user]);

  // Phase 5A: Handle PWA shortcut (?action=sos)
  useEffect(() => {
    if (!pendingSosAction) return;
    if (authChecking) return;

    // If user is not authenticated, keep pendingSosAction active so that after login,
    // the SOS workflow opens. (Login screen will guide the user).
    if (!user) return;

    // Responders cannot initiate SOS dispatches (least privilege)
    if (user.role === 'responder') {
      setPendingSosAction(false);
      if (typeof window !== 'undefined') {
        const url = new URL(window.location.href);
        url.searchParams.delete('action');
        window.history.replaceState({}, document.title, url.pathname + (url.search ? url.search : ''));
      }
      return;
    }

    // Wait until initial data loading completes so member roster is known
    if (loading) return;

    // Consume the pending SOS action and clean URL to prevent retriggering on refresh
    setPendingSosAction(false);
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href);
      url.searchParams.delete('action');
      window.history.replaceState({}, document.title, url.pathname + (url.search ? url.search : ''));
    }

    const activeMembers = members.filter((m) => m && m.is_active !== false);
    if (activeMembers.length === 0) {
      // Guide user through existing workflow to add a member first
      setActiveTab('family');
      setBannerAlert({
        type: 'info',
        message: 'No active household members found. Please register a family member profile before triggering an emergency SOS.'
      });
      setTimeout(() => setBannerAlert(null), 8000);
    } else {
      // Open the existing SOS modal dialog for user to review vitals and explicitly confirm dispatch
      setPreselectedMember(null);
      setSosModalOpen(true);
    }
  }, [pendingSosAction, authChecking, user, loading, members]);

  const handleLoginSuccess = (authenticatedUser) => {
    setUser(authenticatedUser);
    setApiError(null);
    setLoading(true);
    if (authenticatedUser.role === 'responder') {
      setActiveTab('emergencies');
    }
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    setMembers([]);
    setEmergencies([]);
    setResponders([]);
    setApiError(null);
    setActiveTab('emergencies');
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }
  };

  const openSosModal = (member = null) => {
    // Only administrators and family members can trigger SOS
    if (user?.role === 'responder') return;
    setPreselectedMember(member);
    setSosModalOpen(true);
  };

  const handleEmergencyTriggered = (newIncident) => {
    setBannerAlert({
      type: 'danger',
      message: `Emergency SOS registered for ${newIncident.reporter_name}! AI Triage: ${newIncident.severity_level} (${(newIncident.severity_score * 100).toFixed(0)}% confidence). Nearest responders ranked & trusted contacts processed.`
    });
    setActiveTab('emergencies');
    loadData();
    setTimeout(() => setBannerAlert(null), 9000);
  };

  // Real data calculations (No invented stats)
  const activeIncidents = emergencies.filter(e => e.status !== 'RESOLVED');
  const highPriorityCount = emergencies.filter(
    e => e.status !== 'RESOLVED' && (e.severity_level === 'CRITICAL' || e.severity_level === 'HIGH')
  ).length;
  const activeMembersList = members.filter(m => m.is_active !== false);
  const activeRespondersList = responders.filter(r => r.is_active !== false && !r.is_demo);
  const availableRespondersCount = activeRespondersList.filter(r => r.is_available).length;
  const resolvedCount = emergencies.filter(e => e.status === 'RESOLVED').length;

  // Session verification loader
  if (authChecking) {
    return (
      <div className="login-container">
        <div style={{ textAlign: 'center', color: '#94a3b8' }}>
          <div className="login-logo-badge" style={{ margin: '0 auto 1rem', animation: 'pulse 1.5s infinite' }}>
            <ShieldAlert size={28} color="#ffffff" />
          </div>
          <p style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f1f5f9' }}>
            Verifying secure session...
          </p>
        </div>
      </div>
    );
  }

  // If an invitation token is present in the URL, prompt the invitation acceptance modal
  if (inviteToken) {
    return (
      <AcceptInviteModal
        token={inviteToken}
        onAcceptSuccess={(acceptedUser) => {
          setUser(acceptedUser);
          setInviteToken(null);
          if (typeof window !== 'undefined') {
            window.history.replaceState({}, document.title, window.location.pathname);
          }
        }}
        onCancel={() => {
          setInviteToken(null);
          if (typeof window !== 'undefined') {
            window.history.replaceState({}, document.title, window.location.pathname);
          }
        }}
      />
    );
  }

  // Unauthenticated: Render Login Screen
  if (!user) {
    return (
      <LoginScreen
        onLoginSuccess={handleLoginSuccess}
        isSosShortcutPending={pendingSosAction}
        isOnline={isOnline}
        installPrompt={installPrompt}
        isInstalled={isInstalled}
        onInstallClick={handleInstallClick}
        themePreference={themePreference}
        effectiveTheme={effectiveTheme}
        onThemeChange={handleThemeChange}
      />
    );
  }

  return (
    <div className={`app-container ${activeTab === 'first-aid' ? 'first-aid-active' : ''}`}>
      <Header
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        activeIncidentsCount={activeIncidents.length}
        membersCount={activeMembersList.length}
        respondersCount={activeRespondersList.length}
        user={user}
        onLogout={handleLogout}
        onOpenSos={() => openSosModal(null)}
        isOnline={isOnline}
        installPrompt={installPrompt}
        isInstalled={isInstalled}
        onInstallClick={handleInstallClick}
        themePreference={themePreference}
        effectiveTheme={effectiveTheme}
        onThemeChange={handleThemeChange}
      />

      {/* Global Offline Network Warning Banner */}
      {!isOnline && (
        <div className="alert-banner alert-banner-offline" role="alert" style={{ marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <WifiOff size={18} color="#fbbf24" style={{ flexShrink: 0 }} />
            <span>
              <strong>You are currently offline:</strong> FamilyConnect AI requires active internet connectivity (Wi-Fi or cellular) to dispatch emergency SOS alerts, rank community responders, and transmit trusted-contact notifications. Live coordination is paused until connection is restored.
            </span>
          </div>
        </div>
      )}

      {/* Global Connection / API Error Banner */}
      {apiError && (
        <div className="alert-banner alert-banner-danger" role="alert">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={18} color="#ef4444" />
            <span>{apiError}</span>
          </div>
          <button
            type="button"
            className="btn-secondary"
            style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
            onClick={loadData}
          >
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {/* Real-time Dispatch Toast */}
      {bannerAlert && (
        <div className="alert-banner alert-banner-danger" role="status">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ShieldAlert size={18} color="#ef4444" />
            <span>{bannerAlert.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setBannerAlert(null)}
            style={{ background: 'transparent', border: 'none', color: '#fca5a5', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <main id="main-content">
        {activeTab === 'emergencies' && (
          <>
            {/* Operational Emergency Action Strip */}
            <section className="emergency-action-strip" aria-label="Emergency Action Panel">
              <div className="strip-info">
                <div style={{ background: 'rgba(239, 68, 68, 0.15)', padding: '0.6rem', borderRadius: '8px' }}>
                  <ShieldAlert size={22} color="#f87171" />
                </div>
                <div className="strip-text">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <h2>Emergency Coordination Center</h2>
                    <span style={{
                      fontSize: '0.65rem',
                      padding: '0.1rem 0.45rem',
                      borderRadius: '4px',
                      background: !isOnline
                        ? 'rgba(239, 68, 68, 0.15)'
                        : wsState === 'connected' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: !isOnline
                        ? '#f87171'
                        : wsState === 'connected' ? '#34d399' : '#fbbf24',
                      border: `1px solid ${!isOnline ? 'rgba(239, 68, 68, 0.35)' : wsState === 'connected' ? 'rgba(16, 185, 129, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                      fontWeight: 700
                    }}>
                      {!isOnline ? '● OFFLINE - NETWORK DISCONNECTED' : wsState === 'connected' ? '● LIVE WEBSOCKET CONNECTED' : '● POLLING FALLBACK'}
                    </span>
                    {notifConfig && (
                      <span style={{
                        fontSize: '0.65rem',
                        padding: '0.1rem 0.45rem',
                        borderRadius: '4px',
                        background: notifConfig.live_delivery_available ? 'rgba(56, 189, 248, 0.15)' : 'rgba(148, 163, 184, 0.15)',
                        color: notifConfig.live_delivery_available ? '#38bdf8' : '#94a3b8',
                        border: '1px solid rgba(148, 163, 184, 0.3)',
                        fontWeight: 600
                      }}>
                        {notifConfig.live_delivery_available
                          ? `Alerts: Live (${notifConfig.email_provider !== 'unconfigured' ? notifConfig.email_provider : ''}${notifConfig.sms_provider !== 'unconfigured' ? ' ' + notifConfig.sms_provider : ''})`
                          : 'Alerts: Provider Unconfigured (Honest FAILED Status)'}
                      </span>
                    )}
                  </div>
                  <p>One-tap SOS triggers AI triage, real geolocation mapping, live WebSocket sync, and trusted-contact alerts.</p>
                </div>
              </div>

              {user.role === 'responder' ? (
                <div style={{
                  padding: '0.55rem 0.95rem',
                  background: 'rgba(245, 158, 11, 0.12)',
                  border: '1px solid rgba(245, 158, 11, 0.35)',
                  borderRadius: '6px',
                  fontSize: '0.78rem',
                  color: '#fbbf24',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  fontWeight: 600
                }}>
                  <Radio size={14} />
                  <span>Responder Mode Active (Assigned Incidents Only)</span>
                </div>
              ) : (
                <button
                  type="button"
                  className="compact-sos-btn"
                  onClick={() => openSosModal(null)}
                  aria-haspopup="dialog"
                >
                  <ShieldAlert size={18} />
                  <span>TRIGGER SOS</span>
                </button>
              )}
            </section>

            {/* Calculated Live Metrics Grid */}
            <section className="metrics-grid" aria-label="Operational Metrics Summary">
              <div className="metric-card">
                <div>
                  <div className="metric-label">Active Emergencies</div>
                  <div className="metric-val" style={{ color: activeIncidents.length > 0 ? '#f87171' : '#ffffff' }}>
                    {loading ? '—' : activeIncidents.length}
                  </div>
                </div>
                <div className="metric-icon-box" style={{ background: 'rgba(239, 68, 68, 0.12)', color: '#f87171' }}>
                  <Radio size={18} />
                </div>
              </div>

              <div className="metric-card">
                <div>
                  <div className="metric-label">High / Critical Priority</div>
                  <div className="metric-val" style={{ color: highPriorityCount > 0 ? '#fb923c' : '#ffffff' }}>
                    {loading ? '—' : highPriorityCount}
                  </div>
                </div>
                <div className="metric-icon-box" style={{ background: 'rgba(249, 115, 22, 0.12)', color: '#fb923c' }}>
                  <AlertTriangle size={18} />
                </div>
              </div>

              <div className="metric-card">
                <div>
                  <div className="metric-label">Available Responders</div>
                  <div className="metric-val" style={{ color: '#38bdf8' }}>
                    {loading ? '—' : `${availableRespondersCount}/${activeRespondersList.length}`}
                  </div>
                </div>
                <div className="metric-icon-box" style={{ background: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8' }}>
                  <UserCheck size={18} />
                </div>
              </div>

              <div className="metric-card">
                <div>
                  <div className="metric-label">Resolved Incidents</div>
                  <div className="metric-val" style={{ color: '#34d399' }}>
                    {loading ? '—' : resolvedCount}
                  </div>
                </div>
                <div className="metric-icon-box" style={{ background: 'rgba(16, 185, 129, 0.12)', color: '#34d399' }}>
                  <CheckCircle2 size={18} />
                </div>
              </div>
            </section>

            <EmergencyMonitor
              emergencies={emergencies}
              onRefresh={loadData}
              loading={loading}
              onOpenSos={() => openSosModal(null)}
              allResponders={responders}
              user={user}
            />
          </>
        )}

        {activeTab === 'family' && user.role !== 'responder' && (
          <FamilyDashboard
            members={members}
            onRefresh={loadData}
            onTriggerSosForMember={(m) => openSosModal(m)}
            loading={loading}
            user={user}
          />
        )}

        {activeTab === 'responders' && (
          <ResponderAndAlertManager
            responders={responders}
            notifConfig={notifConfig}
            onRefresh={loadData}
            onNotifConfigUpdated={(cfg) => setNotifConfig(cfg)}
            user={user}
          />
        )}

        {activeTab === 'first-aid' && (
          <FirstAidAssistant />
        )}

        {activeTab === 'ai-sandbox' && (
          <AiTriageTester />
        )}
      </main>

      {/* Trust & Safety Disclaimer Footer (suppressed on First Aid tab to allow full-height single scroll chat) */}
      {activeTab !== 'first-aid' && (
        <footer className="trust-disclaimer-footer" role="contentinfo">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Info size={15} color="#94a3b8" />
            <span>
              <strong>Clinical &amp; Safety Notice:</strong> FamilyConnect AI coordinates user-configured household profiles, trusted contacts, and community responders.
              Severity classifications are generated by a scikit-learn Random Forest model trained on synthetic triage scenarios and do not constitute certified medical diagnosis.
            </span>
          </div>
          <div style={{ color: '#64748b', fontSize: '0.72rem' }}>
            Private Coordination Platform • Does not dial 112/108 public emergency services
          </div>
        </footer>
      )}

      {/* SOS Modal (Only enabled for admin and members) */}
      {user.role !== 'responder' && (
        <SosTriggerModal
          isOpen={sosModalOpen}
          onClose={() => {
            setSosModalOpen(false);
            setPreselectedMember(null);
          }}
          members={members}
          preselectedMember={preselectedMember}
          onEmergencyTriggered={handleEmergencyTriggered}
          isOnline={isOnline}
        />
      )}

      {/* Mobile Bottom Navigation Bar */}
      <MobileNav
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        activeIncidentsCount={activeIncidents.length}
        membersCount={activeMembersList.length}
        respondersCount={activeRespondersList.length}
        user={user}
      />
    </div>
  );
}
