import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
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

describe('Privacy Mask & Safe Demo Data Utilities', () => {
  it('detects demo entities by flag, name, or kinship description', () => {
    assert.equal(isDemoEntity({ is_demo: true }), true);
    assert.equal(isDemoEntity({ is_demo: 1 }), true);
    assert.equal(isDemoEntity({ name: 'Eleanor Vance (Grandmother)' }), true);
    assert.equal(isDemoEntity({ name: 'Marcus Vance' }), true);
    assert.equal(isDemoEntity({ contact_name: 'Vance Demo Contact' }), true);
    assert.equal(isDemoEntity({ name: 'Sample Family Member', is_demo: false }), false);
    assert.equal(isDemoEntity(null), false);
  });

  it('generates consistent fictional demo phone numbers', () => {
    const p1 = getFictionalDemoPhone(1);
    const p2 = getFictionalDemoPhone(1);
    assert.equal(p1, p2);
    assert.ok(FICTIONAL_DEMO_PHONES.includes(p1));
    assert.ok(p1.startsWith('+91 98000 0000'));
  });

  it('generates consistent fictional demo emails using safe fictional domains', () => {
    const e1 = getFictionalDemoEmail('Eleanor Vance');
    assert.ok(e1.endsWith('@familyconnect.example'));
    assert.ok(e1.startsWith('demo.eleanor.vance'));
  });

  it('replaces demo contact numbers with safe fictional placeholders', () => {
    const masked = maskPhoneNumber('+91 98765 12345', { isDemo: true, demoSeed: 2 });
    assert.ok(FICTIONAL_DEMO_PHONES.includes(masked));
    assert.notEqual(masked, '+91 98765 12345');
  });

  it('replaces demo emails with safe fictional domain placeholders', () => {
    const masked = maskEmail('eleanor@vance.com', { isDemo: true, demoSeed: 'eleanor' });
    assert.ok(masked.endsWith('@familyconnect.example'));
    assert.notEqual(masked, 'eleanor@vance.com');
  });

  it('masks real Indian phone numbers to conceal middle 5 digits', () => {
    const raw = '+91 98765 43210';
    const masked = maskPhoneNumber(raw, { isDemo: false, enabled: true });
    assert.equal(masked, '+91 98••• ••210');
    // Ensure raw middle digits are not in masked string
    assert.ok(!masked.includes('765 43'));
  });

  it('masks unformatted 10-digit Indian phone numbers', () => {
    const raw = '9876543210';
    const masked = maskPhoneNumber(raw, { isDemo: false, enabled: true });
    assert.equal(masked, '+91 98••• ••210');
    assert.ok(!masked.includes('76543'));
  });

  it('masks international phone numbers', () => {
    const raw = '+14155551234';
    const masked = maskPhoneNumber(raw, { isDemo: false, enabled: true });
    assert.ok(masked.includes('•••'));
    assert.ok(!masked.includes('55512'));
  });

  it('masks real email addresses preserving only first char, last chars, and domain', () => {
    const raw = 'testuser24@example.com';
    const masked = maskEmail(raw, { isDemo: false, enabled: true });
    assert.equal(masked, 't••••••24@example.com');
    assert.ok(!masked.includes('testuser'));
    assert.ok(masked.endsWith('@example.com'));
  });

  it('handles short usernames in email masking gracefully', () => {
    const raw = 'me@example.org';
    const masked = maskEmail(raw, { isDemo: false, enabled: true });
    assert.equal(masked, 'm•@example.org');
  });

  it('masks physical addresses during demonstrations', () => {
    const raw = 'Flat 4B, Skyview Towers, MG Road, Kochi';
    const masked = maskAddress(raw, { isDemo: false, enabled: true });
    assert.equal(masked, '••••••, Kochi');
    assert.ok(!masked.includes('Skyview'));

    const demoAddress = maskAddress(raw, { isDemo: true });
    assert.equal(demoAddress, 'Demo Safe Haven, Bangalore');
  });

  it('returns raw value when enabled=false (unmasked by authorized user)', () => {
    const rawPhone = '+91 98765 43210';
    assert.equal(maskPhoneNumber(rawPhone, { isDemo: false, enabled: false }), rawPhone);

    const rawEmail = 'test@example.com';
    assert.equal(maskEmail(rawEmail, { isDemo: false, enabled: false }), rawEmail);
  });
});
