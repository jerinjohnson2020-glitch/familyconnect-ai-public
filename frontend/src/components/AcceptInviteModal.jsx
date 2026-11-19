import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertCircle, CheckCircle2, User, Lock, Phone, UserCheck, X } from 'lucide-react';
import { validateInvitationToken, acceptInvitation } from '../services/api';
import { validatePhoneNumber, DEFAULT_PHONE_PLACEHOLDER } from '../utils/phone';

export default function AcceptInviteModal({ token, onAcceptSuccess, onCancel }) {
  const [validating, setValidating] = useState(true);
  const [tokenInfo, setTokenInfo] = useState(null);
  const [validationError, setValidationError] = useState(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function checkToken() {
      try {
        setValidating(true);
        const res = await validateInvitationToken(token);
        if (!isMounted) return;
        if (res.valid) {
          setTokenInfo(res);
          setValidationError(null);
        } else {
          setValidationError(res.error || 'Invitation token is invalid or expired.');
        }
      } catch (err) {
        if (!isMounted) return;
        setValidationError(err.message || 'Unable to validate invitation token.');
      } finally {
        if (isMounted) setValidating(false);
      }
    }

    if (token) {
      checkToken();
    } else {
      setValidating(false);
      setValidationError('No invitation token provided.');
    }

    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);

    if (!username.trim() || !password.trim()) {
      setFormError('Username and password are required.');
      return;
    }

    if (password.length < 8) {
      setFormError('Password must be at least 8 characters long.');
      return;
    }

    const hasLetter = /[a-zA-Z]/.test(password);
    const hasDigit = /[0-9]/.test(password);
    if (!hasLetter || !hasDigit) {
      setFormError('Password must contain at least one letter and one number.');
      return;
    }

    let normalizedPhone = undefined;
    if (phone.trim()) {
      const phoneCheck = validatePhoneNumber(phone, { required: false });
      if (!phoneCheck.valid) {
        setFormError(phoneCheck.error);
        return;
      }
      normalizedPhone = phoneCheck.normalized;
    }

    try {
      setSubmitting(true);
      const res = await acceptInvitation({
        token,
        username: username.trim(),
        password,
        full_name: fullName.trim() || undefined,
        phone: normalizedPhone
      });

      if (onAcceptSuccess) {
        onAcceptSuccess(res.user);
      }
    } catch (err) {
      setFormError(err.message || 'Failed to accept invitation.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="invite-modal-title">
      <div className="modal-content" style={{ maxWidth: '480px', width: '92%' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{ background: 'var(--color-primary-soft)', padding: '0.45rem', borderRadius: '8px' }}>
              <ShieldCheck size={22} color="var(--color-primary)" />
            </div>
            <div>
              <h2 id="invite-modal-title" style={{ margin: 0, fontSize: '1.15rem', color: 'var(--color-text)' }}>
                Household Invitation
              </h2>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                Join your family emergency circle
              </span>
            </div>
          </div>
          {onCancel && (
            <button
              type="button"
              className="modal-close-btn"
              onClick={onCancel}
              aria-label="Close dialog"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {validating ? (
          <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
            <div className="login-logo-badge" style={{ margin: '0 auto 1rem', animation: 'pulse 1.5s infinite' }}>
              <ShieldCheck size={26} color="var(--color-primary)" />
            </div>
            <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--color-text)' }}>
              Validating secure invitation token...
            </p>
          </div>
        ) : validationError ? (
          <div style={{ padding: '1.5rem', textAlign: 'center' }}>
            <div style={{
              display: 'inline-flex',
              padding: '0.8rem',
              borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              marginBottom: '1rem'
            }}>
              <AlertCircle size={32} />
            </div>
            <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--color-text)', fontSize: '1.1rem' }}>
              Invitation Unavailable
            </h3>
            <p style={{ margin: '0 0 1.5rem 0', color: 'var(--color-text-muted)', fontSize: '0.88rem', lineHeight: 1.5 }}>
              {validationError}
            </p>
            <button
              type="button"
              className="btn-primary"
              style={{ width: '100%' }}
              onClick={onCancel}
            >
              Return to Login
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ padding: '1.25rem' }}>
            {/* Invitation Details Banner */}
            <div style={{
              background: 'var(--color-primary-soft)',
              border: '1px solid var(--color-border)',
              borderRadius: '8px',
              padding: '0.85rem 1rem',
              marginBottom: '1.25rem'
            }}>
              <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--color-text)', lineHeight: 1.5 }}>
                You have been invited to join <strong>{tokenInfo?.household_name}</strong> as a <strong>{tokenInfo?.role}</strong> for <code>{tokenInfo?.email}</code>.
              </p>
            </div>

            {formError && (
              <div className="alert-banner alert-banner-danger" style={{ marginBottom: '1rem' }} role="alert">
                <AlertCircle size={16} color="#ef4444" />
                <span>{formError}</span>
              </div>
            )}

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label htmlFor="inv-username" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: 'var(--color-text)' }}>
                Choose Username *
              </label>
              <div style={{ position: 'relative' }}>
                <User size={16} color="var(--color-text-muted)" style={{ position: 'absolute', left: '10px', top: '12px' }} />
                <input
                  id="inv-username"
                  type="text"
                  className="form-input"
                  style={{ paddingLeft: '2.2rem' }}
                  placeholder="e.g. alex_chen"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label htmlFor="inv-password" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: 'var(--color-text)' }}>
                Create Password *
              </label>
              <div style={{ position: 'relative' }}>
                <Lock size={16} color="var(--color-text-muted)" style={{ position: 'absolute', left: '10px', top: '12px' }} />
                <input
                  id="inv-password"
                  type="password"
                  className="form-input"
                  style={{ paddingLeft: '2.2rem' }}
                  placeholder="Min 8 chars with letter & digit"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', display: 'block', marginTop: '0.25rem' }}>
                At least 8 characters, with letters and numbers.
              </span>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label htmlFor="inv-fullname" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: 'var(--color-text)' }}>
                Full Name (Optional)
              </label>
              <div style={{ position: 'relative' }}>
                <UserCheck size={16} color="var(--color-text-muted)" style={{ position: 'absolute', left: '10px', top: '12px' }} />
                <input
                  id="inv-fullname"
                  type="text"
                  className="form-input"
                  style={{ paddingLeft: '2.2rem' }}
                  placeholder="e.g. Alex Chen"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '1.5rem' }}>
              <label htmlFor="inv-phone" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: 'var(--color-text)' }}>
                Phone Number (Default: +91)
              </label>
              <div style={{ position: 'relative' }}>
                <Phone size={16} color="var(--color-text-muted)" style={{ position: 'absolute', left: '10px', top: '12px' }} />
                <input
                  id="inv-phone"
                  type="tel"
                  className="form-input"
                  style={{ paddingLeft: '2.2rem' }}
                  placeholder="+91 98765 43210"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', display: 'block', marginTop: '0.25rem' }}>
                Optional. Accepts 10-digit Indian numbers (e.g. 9876543210) or with country code.
              </span>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              {onCancel && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={onCancel}
                  disabled={submitting}
                >
                  Cancel
                </button>
              )}
              <button
                type="submit"
                className="btn-primary"
                disabled={submitting}
                style={{ minWidth: '140px' }}
              >
                {submitting ? 'Joining...' : 'Join Household'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
