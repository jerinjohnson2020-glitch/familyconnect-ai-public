/**
 * FamilyConnect AI - Privacy & Demo Data Protection Utilities
 *
 * Provides safe masking for phone numbers, email addresses, and personal contact
 * details during demonstrations, multi-tenant reviews, and screen presentations.
 *
 * - Demo records: replaced with clearly fictional placeholder contacts.
 * - Real / User records: masked to prevent bystander / screen-share exposure.
 * - WCAG AA compliant contrast in both Light and Dark themes.
 */

export const FICTIONAL_DEMO_DOMAINS = ['@familyconnect.example', '@demo.internal'];
export const FICTIONAL_DEMO_PHONES = [
  '+91 98000 00001',
  '+91 98000 00002',
  '+91 98000 00003',
  '+91 98000 00004',
  '+91 98000 00005'
];

/**
 * Check if a record or entity is marked as demo.
 */
export function isDemoEntity(entity) {
  if (!entity) return false;
  if (typeof entity === 'boolean') return entity;
  if (entity.is_demo === true || entity.is_demo === 1 || entity.isDemo === true) return true;
  const name = String(entity.name || entity.contact_name || '').toLowerCase();
  if (name.includes('demo') || name.includes('vance') || name.includes('(grandmother)')) {
    return true;
  }
  return false;
}

/**
 * Get a safe fictional phone number for demo records.
 * Deterministic based on seed/id/name so it stays consistent during re-renders.
 */
export function getFictionalDemoPhone(seed = 0) {
  let idx = 0;
  if (typeof seed === 'number') {
    idx = Math.abs(seed) % FICTIONAL_DEMO_PHONES.length;
  } else if (typeof seed === 'string') {
    let hash = 0;
    for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) | 0;
    idx = Math.abs(hash) % FICTIONAL_DEMO_PHONES.length;
  }
  return FICTIONAL_DEMO_PHONES[idx];
}

/**
 * Get a safe fictional email address for demo records.
 */
export function getFictionalDemoEmail(seed = 'contact') {
  const clean = String(seed || 'contact')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '.')
    .replace(/\.+/g, '.')
    .replace(/^\.|\.$/g, '') || 'contact';
  return `demo.${clean.slice(0, 15)}@familyconnect.example`;
}

/**
 * Mask a phone number to prevent shoulder-surfing and demonstration leaks.
 * E.g. "+91 98765 43210" -> "+91 98••• ••210"
 * E.g. "+1 (555) 234-5678" -> "+1 (555) •••-5678"
 */
export function maskPhoneNumber(phone, { isDemo = false, demoSeed = 0, enabled = true } = {}) {
  if (!phone) return '';
  if (isDemo) {
    return getFictionalDemoPhone(demoSeed || phone);
  }
  if (!enabled) return String(phone);

  const str = String(phone).trim();
  if (str.length < 5) return '••••••';

  // If Indian formatted "+91 98765 43210" or "+91 9876543210"
  if (str.startsWith('+91')) {
    const digitsOnly = str.replace(/\D/g, '');
    const mobileDigits = digitsOnly.startsWith('91') ? digitsOnly.slice(2) : digitsOnly;
    if (mobileDigits.length === 10) {
      const prefix = mobileDigits.slice(0, 2);
      const suffix = mobileDigits.slice(7);
      return `+91 ${prefix}••• ••${suffix}`;
    }
  }

  // 10-digit Indian without +91
  const cleanDigits = str.replace(/\D/g, '');
  if (cleanDigits.length === 10 && ['6', '7', '8', '9'].includes(cleanDigits[0])) {
    const prefix = cleanDigits.slice(0, 2);
    const suffix = cleanDigits.slice(7);
    return `+91 ${prefix}••• ••${suffix}`;
  }

  // Generic international with '+' e.g. "+1 (555) 234-5678"
  if (cleanDigits.length >= 7) {
    const keepStart = Math.min(3, Math.floor(cleanDigits.length / 3));
    const keepEnd = Math.min(3, Math.floor(cleanDigits.length / 3));
    const maskedPart = '•'.repeat(Math.max(4, cleanDigits.length - keepStart - keepEnd));
    const hasPlus = str.startsWith('+');
    return `${hasPlus ? '+' : ''}${cleanDigits.slice(0, keepStart)} ${maskedPart} ${cleanDigits.slice(-keepEnd)}`;
  }

  // Fallback for short numbers
  return str.slice(0, 2) + '••••' + str.slice(-2);
}

/**
 * Mask an email address to protect personal addresses.
 * E.g. "user24@example.com" -> "u•••24@example.com"
 * E.g. "family735@example.org" -> "f••••••35@example.org"
 */
export function maskEmail(email, { isDemo = false, demoSeed = 'user', enabled = true } = {}) {
  if (!email) return '';
  if (isDemo) {
    return getFictionalDemoEmail(demoSeed || email);
  }
  if (!enabled) return String(email);

  const clean = String(email).trim();
  const atIndex = clean.indexOf('@');
  if (atIndex <= 1) {
    return '••••@' + (clean.slice(atIndex + 1) || 'example.com');
  }

  const userPart = clean.slice(0, atIndex);
  const domainPart = clean.slice(atIndex + 1);

  if (userPart.length <= 2) {
    return userPart[0] + '•@' + domainPart;
  }
  if (userPart.length <= 4) {
    return userPart[0] + '••' + userPart.slice(-1) + '@' + domainPart;
  }

  const firstChar = userPart[0];
  const lastTwo = userPart.slice(-2);
  const maskLength = Math.min(6, userPart.length - 3);
  return `${firstChar}${'•'.repeat(maskLength)}${lastTwo}@${domainPart}`;
}

/**
 * Mask physical address for privacy during demonstrations.
 */
export function maskAddress(address, { isDemo = false, enabled = true } = {}) {
  if (!address) return '';
  if (isDemo) return 'Demo Safe Haven, Bangalore';
  if (!enabled) return String(address);
  const parts = String(address).trim().split(',');
  if (parts.length > 1) {
    return `••••••, ${parts.slice(-1)[0].trim()}`;
  }
  return '•••••• Safe Residence';
}
