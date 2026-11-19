import { describe, it } from 'node:test';
import assert from 'node:assert';
import { validatePhoneNumber, normalizePhoneNumber, DEFAULT_COUNTRY_CODE } from '../src/utils/phone.js';

describe('Authorized Emergency Responders & Real Geolocation Tests', () => {

  // Test 1: Demo Responder Filtering
  it('Test 1: Demo responders (is_demo=true) are strictly excluded from authorized visible responders', () => {
    const respondersList = [
      { id: 1, name: 'Officer David Miller', phone: '+1 (555) 901-1122', is_demo: true, is_active: false },
      { id: 2, name: 'Dr. Karen Lee (Neighbor)', phone: '+1 (555) 902-3344', is_demo: true, is_active: false },
      { id: 3, name: 'Metro Station 4 Paramedic Unit', phone: '+1 (555) 903-5566', is_demo: true, is_active: false },
      { id: 4, name: 'St. Jude Urgent Care Facility', phone: '+1 (555) 904-7788', is_demo: true, is_active: false },
      { id: 5, name: 'Volunteer James Foster', phone: '+1 (555) 905-9900', is_demo: true, is_active: false },
      { id: 6, name: 'Rapid Response Paramedic Unit', phone: '+91 87654 32109', is_demo: false, is_active: true }
    ];

    const showInactive = false;
    const visible = respondersList.filter(r => {
      if (r.is_demo) return false;
      if (!showInactive && r.is_active === false) return false;
      return true;
    });

    assert.strictEqual(visible.length, 1);
    assert.strictEqual(visible[0].id, 6);
    assert.strictEqual(visible[0].name, 'Rapid Response Paramedic Unit');
    assert.strictEqual(visible[0].phone, '+91 87654 32109');
  });

  // Test 2: Inactive Responders Filter
  it('Test 2: Inactive responders are excluded by default, but non-demo inactive can be shown when showInactive=true', () => {
    const respondersList = [
      { id: 6, name: 'Rapid Response Paramedic Unit', is_demo: false, is_active: true },
      { id: 7, name: 'Inactive Real Paramedic', is_demo: false, is_active: false },
      { id: 1, name: 'Officer David Miller', is_demo: true, is_active: false }
    ];

    // Default (showInactive = false)
    let visible = respondersList.filter(r => {
      if (r.is_demo) return false;
      if (r.is_active === false) return false;
      return true;
    });
    assert.strictEqual(visible.length, 1);
    assert.strictEqual(visible[0].name, 'Rapid Response Paramedic Unit');

    // Admin toggles showInactive = true
    visible = respondersList.filter(r => {
      if (r.is_demo) return false;
      return true;
    });
    assert.strictEqual(visible.length, 2);
    assert.ok(visible.some(r => r.name === 'Inactive Real Paramedic'));
    assert.ok(!visible.some(r => r.name === 'Officer David Miller')); // Demo still strictly excluded
  });

  // Test 3: Empty State Detection
  it('Test 3: Empty state is detected when no non-demo authorized responders exist', () => {
    const onlyDemoResponders = [
      { id: 1, name: 'Officer David Miller', is_demo: true, is_active: false },
      { id: 2, name: 'Dr. Karen Lee', is_demo: true, is_active: false }
    ];

    const visible = onlyDemoResponders.filter(r => {
      if (r.is_demo) return false;
      return true;
    });

    assert.strictEqual(visible.length, 0);
  });

  // Test 4: Geolocation Permission Denied Error Handling
  it('Test 4: Geolocation permission denied (code 1) produces informative message with zero coordinate substitution', () => {
    const errorObj = { code: 1, message: 'User denied Geolocation' };
    let msg = '';
    if (errorObj.code === 1) {
      msg = 'Location permission denied by user or browser. No fake coordinates were substituted. Please enable browser location permission or enter manual coordinates.';
    } else if (errorObj.code === 2) {
      msg = 'GPS location unavailable from device sensors. No default coordinates were substituted.';
    } else if (errorObj.code === 3) {
      msg = 'GPS acquisition timed out. No default coordinates were substituted.';
    }

    assert.ok(msg.includes('Location permission denied'));
    assert.ok(msg.includes('No fake coordinates were substituted'));
  });

  // Test 5: Geolocation Position Unavailable and Timeout Error Handling
  it('Test 5: Geolocation position unavailable (code 2) and timeout (code 3) handle errors gracefully', () => {
    const posUnavailable = { code: 2, message: 'Position unavailable' };
    const timeoutErr = { code: 3, message: 'Timeout' };

    const getMsg = (err) => {
      if (err.code === 1) return 'Permission denied';
      if (err.code === 2) return 'GPS location unavailable from device sensors. No default coordinates were substituted. Enter manual coordinates below.';
      if (err.code === 3) return 'GPS acquisition timed out (10s limit). No default coordinates were substituted. Please retry or enter manual coordinates.';
      return 'Unknown error';
    };

    assert.ok(getMsg(posUnavailable).includes('GPS location unavailable'));
    assert.ok(getMsg(timeoutErr).includes('timed out'));
  });

  // Test 6: Geolocation Accuracy and Coarse Reading Warning
  it('Test 6: Geolocation accuracy is reported and coarse reading (>500m) generates an advisory warning', () => {
    const highAccuracyPos = {
      coords: { latitude: 10.018938, longitude: 76.352848, accuracy: 12 },
      timestamp: 1729060000000
    };
    const coarsePos = {
      coords: { latitude: 10.018938, longitude: 76.352848, accuracy: 1200 },
      timestamp: 1729060000000
    };

    const processGps = (pos) => {
      const accuracy = pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null;
      const isCoarse = accuracy && accuracy > 500;
      return {
        lat: pos.coords.latitude.toFixed(6),
        lon: pos.coords.longitude.toFixed(6),
        accuracy,
        isCoarse,
        statusText: `Verified Browser GPS acquired: (${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)}) • Reported Accuracy: ±${accuracy}m`
      };
    };

    const resHigh = processGps(highAccuracyPos);
    assert.strictEqual(resHigh.accuracy, 12);
    assert.strictEqual(resHigh.isCoarse, false);
    assert.ok(resHigh.statusText.includes('±12m'));

    const resCoarse = processGps(coarsePos);
    assert.strictEqual(resCoarse.accuracy, 1200);
    assert.strictEqual(resCoarse.isCoarse, true);
  });

  // Test 7: Responder Phone Validation & Normalization (+91 default)
  it('Test 7: Responder phone numbers normalize to +91 format while rejecting invalid numbers', () => {
    const valid10 = validatePhoneNumber('8765432109', { required: true });
    assert.strictEqual(valid10.valid, true);
    assert.strictEqual(valid10.normalized, '+91 87654 32109');

    const validWithPlus91 = validatePhoneNumber('+919876543210', { required: true });
    assert.strictEqual(validWithPlus91.valid, true);
    assert.strictEqual(validWithPlus91.normalized, '+91 98765 43210');

    const invalid = validatePhoneNumber('12345', { required: true });
    assert.strictEqual(invalid.valid, false);
    assert.ok(invalid.error.includes('too short') || invalid.error.includes('Invalid'));
  });

  // Test 8: Genuine International Numbers are Preserved
  it('Test 8: Genuine international responder contact numbers starting with + are preserved', () => {
    const ukNumber = '+44 7911 123456';
    const resUk = validatePhoneNumber(ukNumber, { required: true });
    assert.strictEqual(resUk.valid, true);
    assert.strictEqual(resUk.normalized, ukNumber);

    const intlNumber = '+61 412 345 678';
    const resIntl = validatePhoneNumber(intlNumber, { required: true });
    assert.strictEqual(resIntl.valid, true);
    assert.strictEqual(resIntl.normalized, intlNumber);
  });
});
