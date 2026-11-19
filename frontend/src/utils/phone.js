/**
 * FamilyConnect AI - Phone Number Localization & Normalization Utilities
 * Default Country Code: India (+91)
 *
 * Supported formats:
 *   - 10-digit Indian mobile: "9876543210" -> normalized to "+91 98765 43210"
 *   - Explicit +91: "+919876543210" or "+91 98765 43210" -> normalized to "+91 98765 43210"
 *   - Domestic trunk: "09876543210" -> normalized to "+91 98765 43210"
 *   - 91 prefix without plus: "919876543210" -> normalized to "+91 98765 43210"
 *   - International: "+1 (555) 234-5678", "+44 7911 123456" -> preserved as valid international format
 */

export const DEFAULT_COUNTRY_CODE = '+91';
export const DEFAULT_PHONE_PLACEHOLDER = '+91 98765 43210';

export function validatePhoneNumber(phone, { required = false } = {}) {
  if (phone == null) {
    if (required) return { valid: false, error: 'Phone number is required.' };
    return { valid: true, normalized: null };
  }

  const cleaned = String(phone).trim();
  if (!cleaned) {
    if (required) return { valid: false, error: 'Phone number is required.' };
    return { valid: true, normalized: null };
  }

  // Reject placeholder test patterns
  if (cleaned.endsWith('000-0000')) {
    return { valid: false, error: 'Placeholder phone numbers ending in 000-0000 are not allowed.' };
  }

  // Allowed characters: digits, spaces, hyphens, parentheses, and optional '+' prefix
  if (!/^[0-9+\-().\s]+$/.test(cleaned)) {
    return {
      valid: false,
      error: 'Phone number contains invalid characters. Use digits, spaces, hyphens, and optional "+" country prefix.'
    };
  }

  const digits = cleaned.replace(/\D/g, '');
  if (digits.length < 7) {
    return { valid: false, error: 'Phone number is too short (must contain at least 7 digits).' };
  }

  // 1. Explicit +91 prefix
  if (cleaned.startsWith('+91')) {
    const inDigits = digits.startsWith('91') ? digits.slice(2) : digits;
    if (inDigits.length !== 10) {
      return {
        valid: false,
        error: `Invalid Indian mobile number. Expected exactly 10 digits after +91, but got ${inDigits.length}. Example: +91 98765 43210`
      };
    }
    if (!['6', '7', '8', '9'].includes(inDigits[0])) {
      return {
        valid: false,
        error: `Invalid Indian mobile number. Mobile numbers in India must start with 6, 7, 8, or 9 (got '${inDigits[0]}').`
      };
    }
    return {
      valid: true,
      normalized: `+91 ${inDigits.slice(0, 5)} ${inDigits.slice(5)}`
    };
  }

  // 2. Domestic 0-prefixed 11-digit format (e.g. 09876543210)
  if (digits.length === 11 && digits.startsWith('0') && ['6', '7', '8', '9'].includes(digits[1])) {
    const inDigits = digits.slice(1);
    return {
      valid: true,
      normalized: `+91 ${inDigits.slice(0, 5)} ${inDigits.slice(5)}`
    };
  }

  // 3. 12 digits starting with 91 (e.g. 919876543210)
  if (digits.length === 12 && digits.startsWith('91') && ['6', '7', '8', '9'].includes(digits[2])) {
    const inDigits = digits.slice(2);
    return {
      valid: true,
      normalized: `+91 ${inDigits.slice(0, 5)} ${inDigits.slice(5)}`
    };
  }

  // 4. Standard 10-digit Indian Mobile Number (Default country: India +91)
  if (digits.length === 10 && !cleaned.startsWith('+')) {
    if (['6', '7', '8', '9'].includes(digits[0])) {
      return {
        valid: true,
        normalized: `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`
      };
    }
    return {
      valid: false,
      error: 'Invalid Indian mobile number. A 10-digit mobile number must start with 6, 7, 8, or 9 (e.g. 98765 43210). For other countries, include "+" with the country code.'
    };
  }

  // 5. International number starting with '+' (and not +91)
  if (cleaned.startsWith('+')) {
    if (digits.length < 7 || digits.length > 15) {
      return { valid: false, error: 'Invalid international phone number. Expected 7 to 15 digits including country code.' };
    }
    return {
      valid: true,
      normalized: cleaned
    };
  }

  // 6. NANP/US 11-digit number starting with 1 (e.g. 1-415-891-3344)
  if (digits.length === 11 && digits.startsWith('1')) {
    return {
      valid: true,
      normalized: `+1 ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`
    };
  }

  return {
    valid: false,
    error: 'Invalid phone number format. Please provide a 10-digit Indian mobile number (e.g. 98765 43210 or +91 98765 43210) or an international number starting with "+".'
  };
}

export function normalizePhoneNumber(phone, { required = false } = {}) {
  const result = validatePhoneNumber(phone, { required });
  if (result.valid) {
    return result.normalized ?? '';
  }
  return String(phone || '').trim();
}
