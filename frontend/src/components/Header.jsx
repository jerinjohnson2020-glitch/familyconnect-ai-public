import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Users,
  Radio,
  Cpu,
  LogOut,
  Shield,
  UserCheck,
  Download,
  Share,
  BookOpen,
  Sun,
  Moon
} from 'lucide-react';
import { isIosSafari, isStandaloneMode, shouldShowIosInstallPrompt } from '../utils/pwaInstall';
import IosInstallModal from './IosInstallModal';

export default function Header({
  activeTab,
  setActiveTab,
  activeIncidentsCount,
  membersCount,
  respondersCount = 0,
  user,
  onLogout,
  onOpenSos = null,
  isOnline = true,
  installPrompt: propInstallPrompt = null,
  isInstalled: propIsInstalled = false,
  onInstallClick: propOnInstallClick = null,
  themePreference = 'system',
  effectiveTheme = 'light',
  onThemeChange = null
}) {
  const isResponder = user?.role === 'responder';
  const [localInstallPrompt, setLocalInstallPrompt] = useState(null);
  const [localIsInstalled, setLocalIsInstalled] = useState(false);
  const [showIosModal, setShowIosModal] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator?.standalone === true;
    if (isStandalone) {
      setLocalIsInstalled(true);
    }

    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setLocalInstallPrompt(e);
    };

    const handleAppInstalled = () => {
      setLocalInstallPrompt(null);
      setLocalIsInstalled(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const handleLocalInstallClick = async () => {
    const promptToUse = propInstallPrompt || localInstallPrompt;
    if (!promptToUse) return;
    try {
      promptToUse.prompt();
      const choice = await promptToUse.userChoice;
      if (choice && choice.outcome === 'accepted') {
        setLocalInstallPrompt(null);
      }
    } catch {
      // Ignore user dismissal or browser cancellation
    }
  };

  const effectiveInstallPrompt = propInstallPrompt !== null ? propInstallPrompt : localInstallPrompt;
  const effectiveIsInstalled = propIsInstalled || localIsInstalled;
  const effectiveOnInstallClick = propOnInstallClick || handleLocalInstallClick;

  const showIosInstallBtn = shouldShowIosInstallPrompt({
    isStandalone: effectiveIsInstalled,
    hasBeforeInstallPrompt: Boolean(effectiveInstallPrompt)
  });

  const getRoleBadge = (role) => {
    switch (role) {
      case 'admin':
        return { label: 'Family Admin', bg: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', border: 'rgba(59, 130, 246, 0.3)' };
      case 'member':
        return { label: 'Family Member', bg: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: 'rgba(16, 185, 129, 0.3)' };
      case 'responder':
        return { label: 'First Responder', bg: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', border: 'rgba(245, 158, 11, 0.3)' };
      default:
        return { label: role || 'User', bg: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8', border: 'rgba(148, 163, 184, 0.3)' };
    }
  };

  const roleStyle = getRoleBadge(user?.role);

  return (
    <header className="app-header" role="banner">
      <div className="brand-section">
        <div className="brand-icon-wrapper" aria-hidden="true">
          <ShieldAlert size={22} color="#ffffff" />
        </div>
        <div className="brand-title-wrap">
          <h1>FamilyConnect AI</h1>
          <div className="brand-meta">
            {!isOnline ? (
              <span className="offline-indicator-pill" title="Network disconnected. Live coordination and SOS dispatch paused.">
                <span className="offline-dot" />
                Offline
              </span>
            ) : (
              <span className="live-indicator-pill" title="AI Triage engine is operational">
                <span className="live-dot" />
                Engine Online
              </span>
            )}
            <span className="demo-chip">Configurable Live System</span>
            {effectiveInstallPrompt && (
              <button
                type="button"
                className="btn-pwa-install"
                onClick={effectiveOnInstallClick}
                title="Install FamilyConnect AI on home screen"
              >
                <Download size={11} />
                <span>Install App</span>
              </button>
            )}
            {showIosInstallBtn && (
              <button
                type="button"
                className="btn-pwa-install btn-ios-install"
                onClick={() => setShowIosModal(true)}
                title="Install FamilyConnect AI on iOS Home Screen"
                data-testid="btn-ios-install-header"
              >
                <Share size={11} />
                <span>Install on iPhone</span>
              </button>
            )}
            {effectiveIsInstalled && (
              <span className="pwa-installed-pill" title="Running as installed Progressive Web App">
                PWA Installed
              </span>
            )}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <nav className="nav-tabs desktop-nav-tabs" aria-label="Main Navigation">
          <button
            type="button"
            className={`nav-tab ${activeTab === 'emergencies' ? 'active' : ''}`}
            onClick={() => setActiveTab('emergencies')}
            aria-selected={activeTab === 'emergencies'}
            role="tab"
          >
            <Radio size={15} />
            <span>Incident Feed</span>
            {activeIncidentsCount > 0 && (
              <span className="tab-badge" aria-label={`${activeIncidentsCount} active emergencies`}>
                {activeIncidentsCount}
              </span>
            )}
          </button>

          {/* Family Dashboard is hidden for responders due to least-privilege privacy */}
          {!isResponder && (
            <button
              type="button"
              className={`nav-tab ${activeTab === 'family' ? 'active' : ''}`}
              onClick={() => setActiveTab('family')}
              aria-selected={activeTab === 'family'}
              role="tab"
            >
              <Users size={15} />
              <span>Family Dashboard</span>
              {membersCount > 0 && (
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  ({membersCount})
                </span>
              )}
            </button>
          )}

          <button
            type="button"
            className={`nav-tab ${activeTab === 'responders' ? 'active' : ''}`}
            onClick={() => setActiveTab('responders')}
            aria-selected={activeTab === 'responders'}
            role="tab"
          >
            <UserCheck size={15} />
            <span>Responders &amp; Alerts</span>
            {respondersCount > 0 && (
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                ({respondersCount})
              </span>
            )}
          </button>

          <button
            type="button"
            className={`nav-tab ${activeTab === 'first-aid' ? 'active' : ''}`}
            onClick={() => setActiveTab('first-aid')}
            aria-selected={activeTab === 'first-aid'}
            role="tab"
          >
            <BookOpen size={15} />
            <span>First Aid Guide</span>
          </button>

          <button
            type="button"
            className={`nav-tab ${activeTab === 'ai-sandbox' ? 'active' : ''}`}
            onClick={() => setActiveTab('ai-sandbox')}
            aria-selected={activeTab === 'ai-sandbox'}
            role="tab"
          >
            <Cpu size={15} />
            <span>AI Triage Sandbox</span>
          </button>
        </nav>

        {/* Quick Emergency SOS Action (Admin and Members) */}
        {!isResponder && onOpenSos && (
          <button
            type="button"
            className="header-sos-btn"
            onClick={() => onOpenSos(null)}
            title="Trigger Emergency SOS"
            aria-label="Trigger Emergency SOS"
          >
            <ShieldAlert size={16} />
            <span>SOS</span>
          </button>
        )}

        {/* Visual Theme Toggle */}
        {onThemeChange && (
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={() => {
              const nextTheme = effectiveTheme === 'dark' ? 'light' : 'dark';
              onThemeChange(nextTheme);
            }}
            title={`Active theme: ${effectiveTheme === 'dark' ? 'Dark' : 'Light'} (${themePreference} preference). Click to switch to ${effectiveTheme === 'dark' ? 'Light' : 'Dark'} mode.`}
            aria-label={`Switch to ${effectiveTheme === 'dark' ? 'Light' : 'Dark'} mode`}
          >
            {effectiveTheme === 'dark' ? (
              <>
                <Sun size={15} color="var(--color-warning)" />
                <span style={{ fontSize: '0.74rem' }}>Light</span>
              </>
            ) : (
              <>
                <Moon size={15} color="var(--color-primary)" />
                <span style={{ fontSize: '0.74rem' }}>Dark</span>
              </>
            )}
          </button>
        )}

        {/* User Identity & Session Controls */}
        {user && (
          <div className="user-session-badge" style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.2 }}>
              <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--color-text)' }}>
                {user.username}
              </span>
              <span
                style={{
                  fontSize: '0.68rem',
                  fontWeight: 600,
                  padding: '0.1rem 0.45rem',
                  borderRadius: '4px',
                  background: roleStyle.bg,
                  color: roleStyle.color,
                  border: `1px solid ${roleStyle.border}`,
                  marginTop: '0.15rem'
                }}
              >
                {roleStyle.label}
              </span>
            </div>

            <button
              type="button"
              className="btn-secondary"
              onClick={onLogout}
              title="Sign out of FamilyConnect AI"
              style={{
                padding: '0.4rem 0.65rem',
                fontSize: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                borderColor: 'var(--color-danger-soft)',
                color: 'var(--color-danger)'
              }}
            >
              <LogOut size={13} />
              <span>Sign Out</span>
            </button>
          </div>
        )}
      </div>

      <IosInstallModal isOpen={showIosModal} onClose={() => setShowIosModal(false)} />
    </header>
  );
}
