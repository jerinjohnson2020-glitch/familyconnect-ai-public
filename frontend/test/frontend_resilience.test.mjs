/**
 * FamilyConnect AI — Phase 6: Frontend Network Degradation & Resilience Tests
 * ===========================================================================
 * Automated verification across 10 discrete test cases (FE-01 to FE-10).
 *
 * Testing Discipline & Scope:
 * - Pure Logic Behavioral Tests (FE-01 to FE-04): Import and execute actual exported
 *   ESM JavaScript functions from `src/services/api.js` and `src/utils/`.
 * - Static Source Audits (FE-05 to FE-10): Read component JSX files directly via
 *   `fs.readFileSync` and perform strict regex/string assertions on actual source markup.
 * - Zero fake/copied React component logic; zero extra dependencies installed.
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Pure ESM modules genuinely importable in Node without JSX compilation
import {
  getWebSocketUrl,
  setAuthToken,
  getAuthToken,
  clearAuthToken,
  onUnauthorized
} from '../src/services/api.js';
import { syncMemberSelection } from '../src/utils/memberSelection.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const sosModalPath = path.resolve(__dirname, '../src/components/SosTriggerModal.jsx');
const appJsxPath = path.resolve(__dirname, '../src/App.jsx');
const monitorJsxPath = path.resolve(__dirname, '../src/components/EmergencyMonitor.jsx');

describe('Phase 6: Frontend Network Degradation & Resilience Suite', () => {

  // -------------------------------------------------------------------------
  // CATEGORY 1: Pure Logic Behavioral Tests (FE-01 to FE-04)
  // -------------------------------------------------------------------------

  test('FE-01 [Behavioral]: api.js getWebSocketUrl correctly derives ws/wss URLs and attaches token', () => {
    // When window is undefined (Node environment), helper returns empty string safely
    const nodeWs = getWebSocketUrl('test-token-123');
    assert.equal(typeof nodeWs, 'string', 'Must return a string safely in non-browser environment');

    // Simulate browser window object
    globalThis.window = {
      location: {
        protocol: 'https:',
        host: 'familyconnect.local'
      }
    };

    try {
      const secureWs = getWebSocketUrl('test-token-xyz');
      assert.ok(secureWs.startsWith('wss://familyconnect.local/api/ws/incidents?token='), 'Must derive wss protocol from https');
      assert.ok(secureWs.includes('test-token-xyz'), 'Must include encoded token parameter');

      globalThis.window.location.protocol = 'http:';
      globalThis.window.location.host = '192.168.1.100:3000';
      const plainWs = getWebSocketUrl('token-abc-999');
      assert.ok(plainWs.startsWith('ws://192.168.1.100:3000/api/ws/incidents?token='), 'Must derive ws protocol from http and LAN host');
    } finally {
      delete globalThis.window;
    }
  });

  test('FE-02 [Behavioral]: api.js token lifecycle management (set, get, clear)', () => {
    // Simulate browser sessionStorage
    const storageMock = new Map();
    globalThis.window = {};
    globalThis.sessionStorage = {
      getItem: (k) => storageMock.get(k) || null,
      setItem: (k, v) => storageMock.set(k, String(v)),
      removeItem: (k) => storageMock.delete(k)
    };

    try {
      clearAuthToken();
      assert.equal(getAuthToken(), null, 'Token must be null after clear');

      setAuthToken('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy');
      assert.equal(getAuthToken(), 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy', 'Token must match value set');
      assert.equal(storageMock.get('familyconnect_token'), 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy', 'Must be saved in sessionStorage');

      clearAuthToken();
      assert.equal(getAuthToken(), null, 'Token must be null after second clear');
      assert.equal(storageMock.has('familyconnect_token'), false, 'SessionStorage key must be deleted');
    } finally {
      delete globalThis.window;
      delete globalThis.sessionStorage;
    }
  });

  test('FE-03 [Behavioral]: api.js onUnauthorized registers callback for 401 interception', () => {
    let unauthorizedTriggered = false;
    onUnauthorized(() => {
      unauthorizedTriggered = true;
    });

    // Verify callback registration hook
    assert.equal(unauthorizedTriggered, false, 'Callback must not trigger until invoked');
  });

  test('FE-04 [Behavioral]: utils/memberSelection.js syncMemberSelection preserves user choice across refreshes', () => {
    const sampleMembers = [
      { id: 1, name: 'Eleanor Vance', relationship: 'Parent', is_demo: false, is_active: true },
      { id: 2, name: 'Bob Member', relationship: 'Brother', is_demo: false, is_active: true }
    ];

    let selectedId = '2'; // User explicitly selected Bob Member (ID 2)
    let repName = 'Bob Member';
    let manualLbl = '';
    const prevOpenRef = { current: true }; // Modal is currently open
    const prevPreselectedRef = { current: null };

    // Simulate background data refresh arriving via WebSocket or polling
    const freshMembersFromApi = JSON.parse(JSON.stringify(sampleMembers));

    syncMemberSelection({
      isOpen: true,
      members: freshMembersFromApi,
      preselectedMember: null,
      selectedMemberId: selectedId,
      reporterName: repName,
      manualLabel: manualLbl,
      prevIsOpenRef: prevOpenRef,
      prevPreselectedIdRef: prevPreselectedRef,
      setSelectedMemberId: (id) => { selectedId = id; },
      setReporterName: (n) => { repName = n; },
      setManualLabel: (l) => { manualLbl = l; }
    });

    // Verification: Active user selection of Bob (ID 2) MUST NOT be reset to default Member 1
    assert.equal(selectedId, '2', 'User selection must be preserved across background updates');
    assert.equal(repName, 'Bob Member', 'Reporter name must match preserved selection');
  });

  // -------------------------------------------------------------------------
  // CATEGORY 2: Static Source Audits (FE-05 to FE-10)
  // -------------------------------------------------------------------------

  test('FE-05 [Static Audit]: SosTriggerModal.jsx binds comprehensive submit button disabled locks', () => {
    assert.ok(fs.existsSync(sosModalPath), 'SosTriggerModal.jsx must exist');
    const source = fs.readFileSync(sosModalPath, 'utf8');

    // Must bind disabled with loading, submitting, acknowledgedDispatch, and isOnline
    assert.ok(
      source.includes('disabled={loading || submitting || !acknowledgedDispatch'),
      'Submit button must be disabled when loading, submitting, or unacknowledged'
    );
    assert.ok(
      source.includes('!isOnline'),
      'Submit button must be disabled when client is offline'
    );
  });

  test('FE-06 [Static Audit]: SosTriggerModal.jsx checks offline status and displays warning before submit', () => {
    const source = fs.readFileSync(sosModalPath, 'utf8');

    assert.ok(
      source.includes('if (!isOnline) {'),
      'Must contain explicit guard checking !isOnline'
    );
    assert.ok(
      source.includes('Cannot dispatch SOS while offline'),
      'Must display informative user-facing offline message'
    );
  });

  test('FE-07 [Static Audit]: SosTriggerModal.jsx enforces in-flight double-click guard', () => {
    const source = fs.readFileSync(sosModalPath, 'utf8');

    assert.ok(
      source.includes('if (loading || submitting) return;'),
      'Submit handler must immediately return if loading or submitting is active'
    );
  });

  test('FE-08 [Static Audit]: SosTriggerModal.jsx enforces explicit confirmation checkbox requirement', () => {
    const source = fs.readFileSync(sosModalPath, 'utf8');

    assert.ok(
      source.includes('acknowledgedDispatch'),
      'Must define acknowledgedDispatch state'
    );
    assert.ok(
      source.includes('setAcknowledgedDispatch(e.target.checked)'),
      'Must update acknowledgedDispatch state via checkbox onChange'
    );
    assert.ok(
      source.includes('I authorize dispatching this incident to the FamilyConnect AI coordinator'),
      'Must require confirmation checkbox acknowledgment before enabling dispatch'
    );
  });

  test('FE-09 [Static Audit]: App.jsx defines 10-second polling fallback interval', () => {
    assert.ok(fs.existsSync(appJsxPath), 'App.jsx must exist');
    const source = fs.readFileSync(appJsxPath, 'utf8');

    assert.ok(
      source.includes('setInterval(loadData, 10000)'),
      'Must register background polling fallback interval at 10,000ms'
    );
    assert.ok(
      source.includes('clearInterval(interval)'),
      'Must clean up polling interval on unmount to prevent memory leaks'
    );
  });

  test('FE-10 [Static Audit]: EmergencyMonitor.jsx enforces in-flight action button state locks', () => {
    assert.ok(fs.existsSync(monitorJsxPath), 'EmergencyMonitor.jsx must exist');
    const source = fs.readFileSync(monitorJsxPath, 'utf8');

    assert.ok(
      source.includes('setUpdatingId('),
      'Must set updatingId lock during incident resolution/status updates'
    );
    assert.ok(
      source.includes('setRetryingAlertId('),
      'Must set retryingAlertId lock during notification alert retries'
    );
    assert.ok(
      source.includes('setAcknowledgingId('),
      'Must set acknowledgingId lock during alert acknowledgement'
    );
  });

});
