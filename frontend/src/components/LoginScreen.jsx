import React, { useState } from 'react';
import {
  ShieldAlert,
  Lock,
  User,
  KeyRound,
  AlertCircle,
  CheckCircle,
  HelpCircle,
  Radio,
  Users,
  Shield,
  UserPlus,
  Mail,
  Phone,
  WifiOff,
  Download,
  Share,
  Sun,
  Moon
} from 'lucide-react';
import { login, register, registerResponder } from '../services/api';
import { validatePhoneNumber, DEFAULT_PHONE_PLACEHOLDER } from '../utils/phone';
import { isIosSafari, isStandaloneMode, shouldShowIosInstallPrompt } from '../utils/pwaInstall';
import IosInstallModal from './IosInstallModal';

export default function LoginScreen({
  onLoginSuccess,
  isSosShortcutPending = false,
  isOnline = true,
  installPrompt = null,
  isInstalled = false,
  onInstallClick = null,
  themePreference = 'system',
  effectiveTheme = 'light',
  onThemeChange = null
}) {
  const [mode, setMode] = useState('login'); // 'login' | 'register' | 'responder'
  const [showIosModal, setShowIosModal] = useState(false);

  const showIosInstallCard = shouldShowIosInstallPrompt({
    isStandalone: isInstalled,
    hasBeforeInstallPrompt: Boolean(installPrompt)
  });

  // Login form state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // Register form state
  const [regFullName, setRegFullName] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPhone, setRegPhone] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regCreateMember, setRegCreateMember] = useState(true);

  // Responder application form state
  const [respFullName, setRespFullName] = useState('');
  const [respEmail, setRespEmail] = useState('');
  const [respPhone, setRespPhone] = useState('');
  const [respOrg, setRespOrg] = useState('');
  const [respBadge, setRespBadge] = useState('');
  const [respSkills, setRespSkills] = useState('');
  const [respUsername, setRespUsername] = useState('');
  const [respPassword, setRespPassword] = useState('');
  const [respSuccess, setRespSuccess] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLoginSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please provide both username and password.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await login(username.trim(), password);
      if (onLoginSuccess) {
        onLoginSuccess(data.user);
      }
    } catch (err) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!regUsername.trim() || !regEmail.trim() || !regPassword) {
      setError('Username, email, and password are required.');
      return;
    }
    if (regPassword.length < 8) {
      setError('Password must be at least 8 characters long and contain both letters and numbers.');
      return;
    }

    let normalizedRegPhone = undefined;
    if (regPhone.trim()) {
      const phoneCheck = validatePhoneNumber(regPhone, { required: false });
      if (!phoneCheck.valid) {
        setError(phoneCheck.error);
        return;
      }
      normalizedRegPhone = phoneCheck.normalized;
    }

    setLoading(true);
    setError('');

    try {
      const data = await register({
        username: regUsername.trim(),
        email: regEmail.trim(),
        password: regPassword,
        full_name: regFullName.trim() || undefined,
        phone: normalizedRegPhone,
        create_self_member: regCreateMember
      });
      if (onLoginSuccess) {
        onLoginSuccess(data.user);
      }
    } catch (err) {
      setError(err.message || 'Registration failed. Please check your inputs.');
    } finally {
      setLoading(false);
    }
  };

  const handleResponderSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!respFullName.trim() || !respEmail.trim() || !respPhone.trim() || !respOrg.trim() || !respUsername.trim() || !respPassword) {
      setError('All required fields must be filled.');
      return;
    }
    if (respPassword.length < 8) {
      setError('Password must be at least 8 characters long and contain both letters and numbers.');
      return;
    }

    const phoneCheck = validatePhoneNumber(respPhone, { required: true });
    if (!phoneCheck.valid) {
      setError(phoneCheck.error);
      return;
    }

    setLoading(true);
    setError('');

    try {
      await registerResponder({
        full_name: respFullName.trim(),
        email: respEmail.trim(),
        phone: phoneCheck.normalized,
        organization: respOrg.trim(),
        badge_id: respBadge.trim() || undefined,
        skills: respSkills.trim() || undefined,
        username: respUsername.trim(),
        password: respPassword
      });
      setRespSuccess(true);
    } catch (err) {
      setError(err.message || 'Responder application submission failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickFill = (userVal, passVal) => {
    setMode('login');
    setUsername(userVal);
    setPassword(passVal);
    setError('');
  };

  return (
    <div className="login-container">
      <div className="login-card" style={{ maxWidth: mode === 'responder' ? '520px' : (mode === 'register' ? '460px' : '420px') }}>
        {/* Optional Header Theme Switcher */}
        {onThemeChange && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.25rem' }}>
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={() => {
                const next = effectiveTheme === 'dark' ? 'light' : 'dark';
                onThemeChange(next);
              }}
              title={`Active theme: ${effectiveTheme === 'dark' ? 'Dark' : 'Light'}. Click to toggle.`}
              aria-label={`Switch to ${effectiveTheme === 'dark' ? 'Light' : 'Dark'} mode`}
              style={{ minHeight: '36px', minWidth: '36px', padding: '0.25rem 0.55rem', fontSize: '0.74rem' }}
            >
              {effectiveTheme === 'dark' ? (
                <>
                  <Sun size={13} color="var(--color-warning)" />
                  <span>Light</span>
                </>
              ) : (
                <>
                  <Moon size={13} color="var(--color-primary)" />
                  <span>Dark</span>
                </>
              )}
            </button>
          </div>
        )}

        {/* Brand Header */}
        <div className="login-header">
          <div className="login-logo-badge">
            <ShieldAlert size={28} color="#ffffff" />
          </div>
          <h2>FamilyConnect AI</h2>
          <p className="login-subtitle">
            Secure Emergency Response & Safety Network
          </p>
          <div className="demo-chip" style={{ margin: '0.4rem auto 0' }}>
            Production-Ready Household Security
          </div>
        </div>

        {/* Auth Mode Tabs */}
        <div style={{
          display: 'flex',
          background: 'var(--color-surface-elevated)',
          borderRadius: '8px',
          padding: '3px',
          marginBottom: '1.25rem',
          border: '1px solid var(--color-border)'
        }}>
          <button
            type="button"
            onClick={() => { setMode('login'); setError(''); setRespSuccess(false); }}
            style={{
              flex: 1,
              padding: '0.45rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              background: mode === 'login' ? 'var(--color-primary)' : 'transparent',
              color: mode === 'login' ? 'var(--color-on-primary)' : 'var(--color-text-muted)',
              transition: 'all 0.2s ease'
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setMode('register'); setError(''); setRespSuccess(false); }}
            style={{
              flex: 1,
              padding: '0.45rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              background: mode === 'register' ? 'var(--color-primary)' : 'transparent',
              color: mode === 'register' ? 'var(--color-on-primary)' : 'var(--color-text-muted)',
              transition: 'all 0.2s ease'
            }}
          >
            Household
          </button>
          <button
            type="button"
            onClick={() => { setMode('responder'); setError(''); setRespSuccess(false); }}
            style={{
              flex: 1.2,
              padding: '0.45rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              background: mode === 'responder' ? 'var(--color-primary)' : 'transparent',
              color: mode === 'responder' ? 'var(--color-on-primary)' : 'var(--color-text-muted)',
              transition: 'all 0.2s ease'
            }}
          >
            Apply as Responder
          </button>
        </div>

        {/* Offline Warning Banner */}
        {!isOnline && (
          <div className="alert-banner alert-banner-offline" style={{ marginBottom: '1.25rem' }} role="alert">
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem' }}>
              <WifiOff size={18} color="#fbbf24" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div style={{ fontSize: '0.8rem', color: '#fef3c7', lineHeight: 1.4 }}>
                <strong>Network Disconnected (Offline):</strong> Authentication and real-time emergency sync require active internet connectivity. Reconnect to Wi-Fi or cellular network to sign in.
              </div>
            </div>
          </div>
        )}

        {/* PWA Install Promotion (if eligible) */}
        {installPrompt && !isInstalled && (
          <div style={{
            background: 'rgba(37, 99, 235, 0.12)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            borderRadius: '8px',
            padding: '0.65rem 0.85rem',
            marginBottom: '1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.75rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Download size={16} color="#60a5fa" />
              <span style={{ fontSize: '0.8rem', color: '#bfdbfe' }}>
                Install FamilyConnect AI app for one-tap emergency access
              </span>
            </div>
            {onInstallClick && (
              <button
                type="button"
                className="btn-pwa-install"
                onClick={onInstallClick}
                style={{ flexShrink: 0, padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
              >
                Install App
              </button>
            )}
          </div>
        )}

        {/* iOS Safari PWA Install Guidance Card */}
        {showIosInstallCard && (
          <div style={{
            background: 'rgba(59, 130, 246, 0.10)',
            border: '1px solid rgba(59, 130, 246, 0.28)',
            borderRadius: '8px',
            padding: '0.65rem 0.85rem',
            marginBottom: '1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.75rem'
          }} data-testid="ios-install-login-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Share size={16} color="#60a5fa" />
              <span style={{ fontSize: '0.8rem', color: '#bfdbfe' }}>
                Add to your iPhone Home Screen for instant SOS dispatch
              </span>
            </div>
            <button
              type="button"
              className="btn-pwa-install btn-ios-install"
              onClick={() => setShowIosModal(true)}
              style={{ flexShrink: 0, padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
              data-testid="btn-ios-install-login"
            >
              Install on iOS
            </button>
          </div>
        )}

        {/* SOS Shortcut Intent Guidance Banner */}
        {isSosShortcutPending && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            borderRadius: '8px',
            padding: '0.65rem 0.85rem',
            marginBottom: '1.25rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem'
          }}>
            <ShieldAlert size={20} color="#ef4444" style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '0.8rem', color: '#fca5a5', lineHeight: 1.4 }}>
              <strong>Emergency SOS Shortcut Detected:</strong> Please sign in to access your household safety coordination dialog.
            </span>
          </div>
        )}

        {/* Error Feedback */}
        {error && (
          <div className="alert-banner alert-banner-danger" style={{ marginBottom: '1.25rem' }} role="alert">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertCircle size={17} color="#ef4444" />
              <span style={{ fontSize: '0.82rem' }}>{error}</span>
            </div>
          </div>
        )}

        {/* Mode: Sign In */}
        {mode === 'login' ? (
          <form onSubmit={handleLoginSubmit} className="login-form">
            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label htmlFor="login-username" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <User size={14} color="var(--text-muted)" />
                Username
              </label>
              <input
                id="login-username"
                type="text"
                className="form-control"
                placeholder="e.g. alex_admin, sarah_chen"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
                autoComplete="username"
                required
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label htmlFor="login-password" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Lock size={14} color="var(--text-muted)" />
                Password
              </label>
              <input
                id="login-password"
                type="password"
                className="form-control"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="current-password"
                required
              />
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              style={{ width: '100%', padding: '0.75rem', fontWeight: 700 }}
            >
              {loading ? 'Authenticating...' : 'Sign In to Household'}
            </button>
          </form>
        ) : (
          /* Mode: Register Household */
          <form onSubmit={handleRegisterSubmit} className="login-form">
            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <User size={14} color="var(--text-muted)" />
                Full Name / Household Head
              </label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. Sarah Connor"
                value={regFullName}
                onChange={(e) => setRegFullName(e.target.value)}
                disabled={loading}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <User size={14} color="var(--text-muted)" />
                Username (for sign in) *
              </label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. sconnor"
                value={regUsername}
                onChange={(e) => setRegUsername(e.target.value)}
                disabled={loading}
                required
              />
            </div>

            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Mail size={14} color="var(--text-muted)" />
                Real Email Address *
              </label>
              <input
                type="email"
                className="form-control"
                placeholder="e.g. sarah@familydomain.com"
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
                disabled={loading}
                required
              />
            </div>

            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Phone size={14} color="var(--text-muted)" />
                Phone Number (Default: +91)
              </label>
              <input
                type="tel"
                className="form-control"
                placeholder="e.g. +91 98765 43210"
                value={regPhone}
                onChange={(e) => setRegPhone(e.target.value)}
                disabled={loading}
              />
              <span style={{ fontSize: '0.72rem', color: '#64748b', display: 'block', marginTop: '0.25rem' }}>
                Accepts 10-digit Indian numbers (e.g. 9876543210) or with country code.
              </span>
            </div>

            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Lock size={14} color="var(--text-muted)" />
                Password (min 8 chars, letters & numbers) *
              </label>
              <input
                type="password"
                className="form-control"
                placeholder="Create strong password"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                disabled={loading}
                required
              />
            </div>

            <div style={{ marginBottom: '1.15rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.78rem', color: '#cbd5e1', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={regCreateMember}
                  onChange={(e) => setRegCreateMember(e.target.checked)}
                  disabled={loading}
                />
                <span>Create my initial family member profile automatically</span>
              </label>
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              style={{ width: '100%', padding: '0.75rem', fontWeight: 700 }}
            >
              {loading ? 'Creating Household...' : 'Create Household Account'}
            </button>
          </form>
        )}

        {/* Mode: Apply as Responder */}
        {mode === 'responder' && (
          respSuccess ? (
            <div style={{ textAlign: 'center', padding: '1.5rem 0.5rem' }}>
              <div style={{ display: 'inline-flex', padding: '0.8rem', borderRadius: '50%', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', marginBottom: '1rem' }}>
                <CheckCircle size={36} />
              </div>
              <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-primary)', fontSize: '1.15rem' }}>Application Submitted</h3>
              <p style={{ margin: '0 0 1.5rem 0', color: '#94a3b8', fontSize: '0.86rem', lineHeight: 1.55 }}>
                Thank you for applying to the FamilyConnect AI First Responder network. For community safety, all emergency responder accounts require administrative vetting before activation. You will receive an email confirmation once reviewed.
              </p>
              <button
                type="button"
                className="btn-primary"
                style={{ width: '100%', padding: '0.7rem' }}
                onClick={() => { setMode('login'); setRespSuccess(false); }}
              >
                Return to Sign In
              </button>
            </div>
          ) : (
            <form onSubmit={handleResponderSubmit} className="login-form">
              <div className="form-group" style={{ marginBottom: '0.8rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <User size={14} color="var(--text-muted)" />
                  Full Name *
                </label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Officer Jane Doe / Medic Alex Smith"
                  value={respFullName}
                  onChange={(e) => setRespFullName(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.8rem' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Mail size={14} color="var(--text-muted)" />
                    Official Email *
                  </label>
                  <input
                    type="email"
                    className="form-control"
                    placeholder="name@agency.org"
                    value={respEmail}
                    onChange={(e) => setRespEmail(e.target.value)}
                    disabled={loading}
                    required
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Phone size={14} color="var(--text-muted)" />
                    Dispatch Phone (+91) *
                  </label>
                  <input
                    type="tel"
                    className="form-control"
                    placeholder="+91 98765 43210"
                    value={respPhone}
                    onChange={(e) => setRespPhone(e.target.value)}
                    disabled={loading}
                    required
                  />
                  <span style={{ fontSize: '0.72rem', color: '#64748b', display: 'block', marginTop: '0.25rem' }}>
                    Accepts 10 digits or +91 format.
                  </span>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '0.75rem', marginBottom: '0.8rem' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Shield size={14} color="var(--text-muted)" />
                    Agency / Organization *
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Metro EMS / County Fire"
                    value={respOrg}
                    onChange={(e) => setRespOrg(e.target.value)}
                    disabled={loading}
                    required
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <KeyRound size={14} color="var(--text-muted)" />
                    Badge / Unit ID
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. EMS-402"
                    value={respBadge}
                    onChange={(e) => setRespBadge(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '0.8rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Radio size={14} color="var(--text-muted)" />
                  Skills / Certifications (Optional)
                </label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. EMT-B, ACLS, Wilderness SAR"
                  value={respSkills}
                  onChange={(e) => setRespSkills(e.target.value)}
                  disabled={loading}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.15rem' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <User size={14} color="var(--text-muted)" />
                    Username *
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Choose username"
                    value={respUsername}
                    onChange={(e) => setRespUsername(e.target.value)}
                    disabled={loading}
                    required
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Lock size={14} color="var(--text-muted)" />
                    Password *
                  </label>
                  <input
                    type="password"
                    className="form-control"
                    placeholder="Min 8 chars"
                    value={respPassword}
                    onChange={(e) => setRespPassword(e.target.value)}
                    disabled={loading}
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="btn-primary"
                disabled={loading}
                style={{ width: '100%', padding: '0.75rem', fontWeight: 700 }}
              >
                {loading ? 'Submitting Application...' : 'Submit Responder Application'}
              </button>
            </form>
          )
        )}

        {/* Demo Quick-Fill Roles (Sign In mode only) */}
        {mode === 'login' && (
          <div className="demo-roles-section">
            <div className="demo-roles-divider">
              <span>Demo Accounts (Deactivated)</span>
            </div>

            <div className="demo-role-buttons">
              <button
                type="button"
                className="demo-role-btn disabled"
                disabled
                aria-disabled="true"
                style={{
                  opacity: 0.55,
                  cursor: 'not-allowed',
                  borderStyle: 'dashed',
                  background: 'rgba(15, 23, 42, 0.4)'
                }}
                title="Demo account deactivated for production safety"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Shield size={14} color="#64748b" />
                  <span className="demo-role-name" style={{ color: '#94a3b8' }}>Family Administrator</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <span className="demo-role-user">admin</span>
                  <span style={{ fontSize: '0.65rem', color: '#f87171', background: 'rgba(239, 68, 68, 0.15)', padding: '0.1rem 0.35rem', borderRadius: '4px', fontWeight: 700 }}>
                    Disabled
                  </span>
                </div>
              </button>

              <button
                type="button"
                className="demo-role-btn disabled"
                disabled
                aria-disabled="true"
                style={{
                  opacity: 0.55,
                  cursor: 'not-allowed',
                  borderStyle: 'dashed',
                  background: 'rgba(15, 23, 42, 0.4)'
                }}
                title="Demo account deactivated for production safety"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Users size={14} color="#64748b" />
                  <span className="demo-role-name" style={{ color: '#94a3b8' }}>Family Member</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <span className="demo-role-user">marcus</span>
                  <span style={{ fontSize: '0.65rem', color: '#f87171', background: 'rgba(239, 68, 68, 0.15)', padding: '0.1rem 0.35rem', borderRadius: '4px', fontWeight: 700 }}>
                    Disabled
                  </span>
                </div>
              </button>

              <button
                type="button"
                className="demo-role-btn disabled"
                disabled
                aria-disabled="true"
                style={{
                  opacity: 0.55,
                  cursor: 'not-allowed',
                  borderStyle: 'dashed',
                  background: 'rgba(15, 23, 42, 0.4)'
                }}
                title="Demo account deactivated for production safety"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Radio size={14} color="#64748b" />
                  <span className="demo-role-name" style={{ color: '#94a3b8' }}>First Responder</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <span className="demo-role-user">officer_david</span>
                  <span style={{ fontSize: '0.65rem', color: '#f87171', background: 'rgba(239, 68, 68, 0.15)', padding: '0.1rem 0.35rem', borderRadius: '4px', fontWeight: 700 }}>
                    Disabled
                  </span>
                </div>
              </button>
            </div>

            <p style={{
              fontSize: '0.72rem',
              color: 'var(--text-muted)',
              marginTop: '0.65rem',
              marginBottom: 0,
              textAlign: 'center',
              lineHeight: 1.4
            }}>
              Demo logins are deactivated. Please sign in with your active registered account, or create a household / responder profile above.
            </p>
          </div>
        )}

        {/* Security Architecture Notice */}
        <div className="login-security-notice">
          <HelpCircle size={14} color="#64748b" style={{ flexShrink: 0, marginTop: '2px' }} />
          <p>
            <strong>Security Architecture Notice:</strong> Bearer tokens are stored in browser session storage for demonstration isolation (cleared when closing the browser tab). No passwords or hashes are stored in source code.
          </p>
        </div>
      </div>

      <IosInstallModal isOpen={showIosModal} onClose={() => setShowIosModal(false)} />
    </div>
  );
}
