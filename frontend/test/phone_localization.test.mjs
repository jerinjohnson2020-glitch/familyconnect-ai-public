import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePhoneNumber, normalizePhoneNumber, DEFAULT_COUNTRY_CODE, DEFAULT_PHONE_PLACEHOLDER } from '../src/utils/phone.js';

test('Test 1: Default Country Code and Placeholder constants', () => {
  assert.equal(DEFAULT_COUNTRY_CODE, '+91', 'Default country code must be +91');
  assert.equal(DEFAULT_PHONE_PLACEHOLDER, '+91 98765 43210', 'Placeholder must be +91 98765 43210');
});

test('Test 2: Standard 10-digit Indian numbers without country code normalize to +91 98765 43210', () => {
  const formats = [
    '9876543210',
    '98765 43210',
    '98765-43210',
    '8765432109',
    '7654321098',
    '6282001122'
  ];

  for (const raw of formats) {
    const res = validatePhoneNumber(raw);
    assert.equal(res.valid, true, `Expected ${raw} to be valid`);
    assert.match(res.normalized, /^\+91 [6-9]\d{4} \d{5}$/, `Expected ${res.normalized} to match standard +91 format`);
  }

  assert.equal(validatePhoneNumber('9876543210').normalized, '+91 98765 43210');
  assert.equal(validatePhoneNumber('8765432109').normalized, '+91 87654 32109');
});

test('Test 3: Indian numbers with explicit +91, domestic trunk 0, or 91 without plus normalize consistently', () => {
  const inputs = [
    '+919876543210',
    '+91 98765 43210',
    '+91-98765-43210',
    '+91  9876543210',
    '09876543210',
    '919876543210'
  ];

  for (const raw of inputs) {
    const res = validatePhoneNumber(raw);
    assert.equal(res.valid, true, `Expected ${raw} to be valid`);
    assert.equal(res.normalized, '+91 98765 43210', `Expected ${raw} to normalize to +91 98765 43210`);
  }
});

test('Test 4: Invalid Indian numbers are rejected with helpful messages', () => {
  // 10 digits starting with 1-5 (not a mobile number in India)
  const nonMobile = validatePhoneNumber('1234567890');
  assert.equal(nonMobile.valid, false);
  assert.match(nonMobile.error, /start with 6, 7, 8, or 9/);

  // +91 followed by digits starting with 1
  const badStart = validatePhoneNumber('+91 12345 67890');
  assert.equal(badStart.valid, false);
  assert.match(badStart.error, /start with 6, 7, 8, or 9/);

  // +91 followed by too few digits
  const tooFew = validatePhoneNumber('+91 98765');
  assert.equal(tooFew.valid, false);
  assert.match(tooFew.error, /Expected exactly 10 digits after \+91/);

  // Short number
  const shortNum = validatePhoneNumber('12345');
  assert.equal(shortNum.valid, false);
  assert.match(shortNum.error, /too short/);

  // Invalid characters
  const badChars = validatePhoneNumber('98765abcde');
  assert.equal(badChars.valid, false);
  assert.match(badChars.error, /invalid characters/);
});

test('Test 5: Placeholder phone numbers ending in 000-0000 are rejected', () => {
  const placeholder1 = validatePhoneNumber('+1 555 000-0000');
  assert.equal(placeholder1.valid, false);
  assert.match(placeholder1.error, /000-0000/);

  const placeholder2 = validatePhoneNumber('+91 98765 000-0000');
  assert.equal(placeholder2.valid, false);
  assert.match(placeholder2.error, /000-0000/);
});

test('Test 6: Valid international numbers are preserved without adding +91', () => {
  const intlNumbers = [
    '+1 415 891 3344',
    '+1 (555) 234-5678',
    '+44 7911 123456',
    '+61 2 9374 4000',
    '+81 3 1234 5678'
  ];

  for (const num of intlNumbers) {
    const res = validatePhoneNumber(num);
    assert.equal(res.valid, true, `Expected international number ${num} to be valid`);
    assert.equal(res.normalized, num, `Expected international number ${num} to be preserved intact`);
    assert.ok(!res.normalized.startsWith('+91'), `Should not add +91 to ${num}`);
  }
});

test('Test 7: US/NANP 11-digit numbers without plus normalize to +1 format', () => {
  const res = validatePhoneNumber('1-415-891-3344');
  assert.equal(res.valid, true);
  assert.equal(res.normalized, '+1 415 891 3344');
});

test('Test 8: Optional vs Required handling', () => {
  // Empty/null optional
  const optNull = validatePhoneNumber(null, { required: false });
  assert.equal(optNull.valid, true);
  assert.equal(optNull.normalized, null);

  const optEmpty = validatePhoneNumber('', { required: false });
  assert.equal(optEmpty.valid, true);
  assert.equal(optEmpty.normalized, null);

  // Empty/null required
  const reqNull = validatePhoneNumber(null, { required: true });
  assert.equal(reqNull.valid, false);
  assert.match(reqNull.error, /required/);

  const reqEmpty = validatePhoneNumber('', { required: true });
  assert.equal(reqEmpty.valid, false);
  assert.match(reqEmpty.error, /required/);
});

test('Test 9: normalizePhoneNumber convenience helper', () => {
  assert.equal(normalizePhoneNumber('9876543210'), '+91 98765 43210');
  assert.equal(normalizePhoneNumber('+919876543210'), '+91 98765 43210');
  assert.equal(normalizePhoneNumber('+1 415 891 3344'), '+1 415 891 3344');
  assert.equal(normalizePhoneNumber(''), '');
  assert.equal(normalizePhoneNumber(null), '');
});
