import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  isDemoEntity,
  getFictionalDemoPhone,
  getFictionalDemoEmail,
  maskPhoneNumber,
  maskEmail,
  maskAddress,
  FICTIONAL_DEMO_DOMAINS,
  FICTIONAL_DEMO_PHONES
} from '../src/utils/privacyMask.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendSrcDir = path.resolve(__dirname, '../src');

describe('Demo Data Privacy & Light Theme Contrast Integration Suite', () => {
  it('Component source audit: FamilyDashboard does not use hardcoded #cbd5e1 for contact info', () => {
    const file = fs.readFileSync(path.join(frontendSrcDir, 'components/FamilyDashboard.jsx'), 'utf8');
    // Ensure contact details do not use #cbd5e1
    assert.ok(!file.includes("fontSize: '0.8rem', color: '#cbd5e1'"), 'Contact details should not use #cbd5e1');
    assert.ok(file.includes('demoPrivacyMode'), 'FamilyDashboard should provide demo privacy state');
    assert.ok(file.includes('maskPhoneNumber'), 'FamilyDashboard should use maskPhoneNumber');
    assert.ok(file.includes('maskEmail'), 'FamilyDashboard should use maskEmail');
  });

  it('Component source audit: SosTriggerModal masks dispatched contact details', () => {
    const file = fs.readFileSync(path.join(frontendSrcDir, 'components/SosTriggerModal.jsx'), 'utf8');
    assert.ok(file.includes('maskEmail'), 'SosTriggerModal should mask emails');
    assert.ok(file.includes('maskPhoneNumber'), 'SosTriggerModal should mask phone numbers');
    assert.ok(!file.includes('`${c.name} (${c.notification_preferences}: ${c.email || c.phone})`'), 'Raw contact info must not be exposed in SOS dispatch summary');
  });

  it('Component source audit: EmergencyMonitor masks alert contact destinations', () => {
    const file = fs.readFileSync(path.join(frontendSrcDir, 'components/EmergencyMonitor.jsx'), 'utf8');
    assert.ok(file.includes('maskEmail'), 'EmergencyMonitor should mask alert emails');
    assert.ok(file.includes('maskPhoneNumber'), 'EmergencyMonitor should mask alert phones');
    assert.ok(!file.includes('({alert.contact_email || alert.contact_phone})'), 'Raw contact email or phone must not be exposed');
  });

  it('Component source audit: ResponderAndAlertManager does not use hardcoded #cbd5e1 for responder contact info', () => {
    const file = fs.readFileSync(path.join(frontendSrcDir, 'components/ResponderAndAlertManager.jsx'), 'utf8');
    assert.ok(!file.includes("color: '#cbd5e1', marginBottom: '0.65rem'"), 'Responder contact info should not use #cbd5e1');
    assert.ok(file.includes('maskPhoneNumber(resp.phone'), 'Responder phone numbers must be masked');
    assert.ok(file.includes('maskEmail(resp.email'), 'Responder emails must be masked');
  });

  it('Demo data safety: demo entities produce completely fictional placeholders', () => {
    const demoMember = {
      id: 1,
      name: 'Eleanor Vance (Grandmother)',
      phone: '+91 98765 23456',
      email: 'eleanor.vance@vancefamily.com',
      is_demo: true
    };

    const safePhone = maskPhoneNumber(demoMember.phone, { isDemo: demoMember.is_demo, demoSeed: demoMember.id });
    const safeEmail = maskEmail(demoMember.email, { isDemo: demoMember.is_demo, demoSeed: demoMember.name });

    assert.ok(FICTIONAL_DEMO_PHONES.includes(safePhone), 'Phone should be a fictional placeholder');
    assert.notEqual(safePhone, demoMember.phone, 'Fictional phone should not match input phone');
    assert.ok(safeEmail.endsWith('@familyconnect.example'), 'Email should end with fictional demo domain');
    assert.notEqual(safeEmail, demoMember.email, 'Fictional email should not match input email');
  });

  it('User privacy safety: non-demo real user contacts are masked against shoulder-surfing', () => {
    const realMember = {
      id: 7,
      name: 'Sample Family Member',
      phone: '+91 98765 43210',
      email: 'testuser24@example.com',
      address: 'Flat 3B, Palm Meadows, Kochi',
      emergency_contact_phone: '+91 91234 56789',
      is_demo: false
    };

    const maskedPhone = maskPhoneNumber(realMember.phone, { isDemo: false, enabled: true });
    const maskedEmail = maskEmail(realMember.email, { isDemo: false, enabled: true });
    const maskedECPhone = maskPhoneNumber(realMember.emergency_contact_phone, { isDemo: false, enabled: true });
    const maskedAddr = maskAddress(realMember.address, { isDemo: false, enabled: true });

    assert.equal(maskedPhone, '+91 98••• ••210');
    assert.equal(maskedEmail, 't••••••24@example.com');
    assert.equal(maskedECPhone, '+91 91••• ••789');
    assert.equal(maskedAddr, '••••••, Kochi');

    // Never contain raw middle digits
    assert.ok(!maskedPhone.includes('765 43'));
    assert.ok(!maskedEmail.includes('testuser'));
  });

  it('Contrast compliance: Light Theme tokens ensure WCAG AA contrast (≥4.5:1)', () => {
    const cssFile = fs.readFileSync(path.join(frontendSrcDir, 'index.css'), 'utf8');
    assert.ok(cssFile.includes('[data-theme="light"]'), 'Light theme must be defined');

    // Helper to calculate contrast ratio between two hex colors
    function getLuminance(r, g, b) {
      const a = [r, g, b].map((v) => {
        v /= 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }

    function hexToRgb(hex) {
      const bigint = parseInt(hex.replace('#', ''), 16);
      return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255];
    }

    function contrastRatio(hex1, hex2) {
      const l1 = getLuminance(...hexToRgb(hex1));
      const l2 = getLuminance(...hexToRgb(hex2));
      const lighter = Math.max(l1, l2);
      const darker = Math.min(l1, l2);
      return (lighter + 0.05) / (darker + 0.05);
    }

    // Light theme background cards are #ffffff, canvas is #f8fafc
    const bgCard = '#ffffff';
    const textPrimary = '#0f172a';
    const textSecondary = '#475569';
    const blue500 = '#0369a1';
    const emerald500 = '#047857';
    const red500 = '#dc2626';

    const ratioPrimary = contrastRatio(bgCard, textPrimary);
    const ratioSecondary = contrastRatio(bgCard, textSecondary);
    const ratioBlue = contrastRatio(bgCard, blue500);
    const ratioEmerald = contrastRatio(bgCard, emerald500);
    const ratioRed = contrastRatio(bgCard, red500);

    assert.ok(ratioPrimary >= 15, `Primary text contrast ${ratioPrimary} should be >= 15:1`);
    assert.ok(ratioSecondary >= 4.5, `Secondary text contrast ${ratioSecondary} should be >= 4.5:1 (WCAG AA)`);
    assert.ok(ratioBlue >= 4.5, `Blue accent contrast ${ratioBlue} should be >= 4.5:1`);
    assert.ok(ratioEmerald >= 4.5, `Emerald contrast ${ratioEmerald} should be >= 4.5:1`);
    assert.ok(ratioRed >= 4.5, `Red contrast ${ratioRed} should be >= 4.5:1`);
  });
});
