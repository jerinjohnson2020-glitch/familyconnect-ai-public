import React, { useEffect, useRef } from 'react';
import { Share, PlusSquare, X, ShieldAlert, Smartphone } from 'lucide-react';

export default function IosInstallModal({ isOpen, onClose }) {
  const closeBtnRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;

    // Focus close button on open for keyboard accessibility
    if (closeBtnRef.current) {
      closeBtnRef.current.focus();
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ios-install-title"
      data-testid="ios-install-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-content ios-install-modal">
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'rgba(239, 68, 68, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <ShieldAlert size={18} color="var(--color-primary)" />
            </div>
            <div>
              <h3 id="ios-install-title" style={{ margin: 0, fontSize: '1.05rem', color: 'var(--color-text)' }}>
                Install on iPhone / iPad
              </h3>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                Safari Home Screen Setup
              </span>
            </div>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            className="btn-close"
            onClick={onClose}
            aria-label="Close installation guide"
            data-testid="btn-close-ios-modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="ios-install-body">
          <div className="ios-install-callout">
            <Smartphone size={20} color="#60a5fa" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong>One-Tap Emergency Access:</strong> Add FamilyConnect AI to your iOS Home Screen for instant SOS dispatch, full-screen view, and offline safety guide access.
            </div>
          </div>

          <p style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', margin: '0.75rem 0' }}>
            Follow these 3 quick steps in Safari:
          </p>

          <ol className="ios-install-steps">
            <li>
              <div className="step-icon">
                <Share size={18} color="#60a5fa" />
              </div>
              <div className="step-text">
                <div className="step-title">1. Tap the Share Button</div>
                <div className="step-desc">
                  Tap the <strong>Share</strong> button (box with upward arrow) in Safari's bottom navigation bar (or top toolbar on iPad).
                </div>
              </div>
            </li>
            <li>
              <div className="step-icon">
                <PlusSquare size={18} color="#34d399" />
              </div>
              <div className="step-text">
                <div className="step-title">2. Select "Add to Home Screen"</div>
                <div className="step-desc">
                  Scroll down through the share options and tap <strong>Add to Home Screen</strong>.
                </div>
              </div>
            </li>
            <li>
              <div className="step-icon">
                <span className="step-number">3</span>
              </div>
              <div className="step-text">
                <div className="step-title">3. Confirm Installation</div>
                <div className="step-desc">
                  Tap <strong>Add</strong> in the top-right corner. The FamilyConnect AI icon will now appear on your Home Screen.
                </div>
              </div>
            </li>
          </ol>
        </div>

        <div className="modal-actions" style={{ justifyContent: 'flex-end', marginTop: '1.25rem' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onClose}
            data-testid="btn-dismiss-ios-modal"
          >
            Got It
          </button>
        </div>
      </div>
    </div>
  );
}
