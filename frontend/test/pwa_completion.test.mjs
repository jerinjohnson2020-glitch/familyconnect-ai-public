import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendDir = path.resolve(__dirname, '..');

describe('PWA Completion & Verification Test Suite', () => {

  test('Test 1: Web App Manifest validity, fields, and icon file existence', () => {
    const manifestPath = path.join(frontendDir, 'public', 'manifest.webmanifest');
    assert.ok(fs.existsSync(manifestPath), 'manifest.webmanifest must exist');

    const manifestContent = fs.readFileSync(manifestPath, 'utf8');
    const manifest = JSON.parse(manifestContent);

    // Required fields
    assert.equal(manifest.name, 'FamilyConnect AI - Emergency Response Platform');
    assert.equal(manifest.short_name, 'FamilyConnect');
    assert.equal(manifest.start_url, '/');
    assert.equal(manifest.display, 'standalone');
    assert.equal(manifest.background_color, '#080c18');
    assert.equal(manifest.theme_color, '#080c18');
    assert.ok(Array.isArray(manifest.icons) && manifest.icons.length >= 4, 'Manifest must have at least 4 icon definitions');

    // Verify all icon files exist on disk
    for (const icon of manifest.icons) {
      const relPath = icon.src.replace(/^\//, '');
      const iconPath = path.join(frontendDir, 'public', relPath);
      assert.ok(fs.existsSync(iconPath), `Manifest icon file must exist on disk: ${icon.src}`);
      const stats = fs.statSync(iconPath);
      assert.ok(stats.size > 0, `Manifest icon file must not be empty: ${icon.src}`);
    }

    // Verify shortcuts
    assert.ok(Array.isArray(manifest.shortcuts), 'Manifest shortcuts must be an array');
    const sosShortcut = manifest.shortcuts.find(s => s.url === '/?action=sos');
    assert.ok(sosShortcut, 'SOS shortcut must exist with url "/?action=sos"');
    assert.equal(sosShortcut.name, 'Trigger SOS');
    assert.ok(Array.isArray(sosShortcut.icons) && sosShortcut.icons.length > 0, 'SOS shortcut must have icon defined');
  });

  test('Test 2: Service worker security rules - static whitelisting and zero API/credential caching', () => {
    const swPath = path.join(frontendDir, 'public', 'sw.js');
    assert.ok(fs.existsSync(swPath), 'sw.js must exist');

    const swContent = fs.readFileSync(swPath, 'utf8');

    // Cache name and version
    assert.ok(swContent.includes('familyconnect-static-v2'), 'sw.js must use familyconnect-static-v2');

    // Check for API bypass rules
    assert.ok(swContent.includes("url.pathname.startsWith('/api')"), 'sw.js must explicitly bypass /api requests');
    assert.ok(swContent.includes("request.headers.has('Authorization')"), 'sw.js must bypass requests with authorization headers');
    assert.ok(swContent.includes("url.protocol === 'ws:'") && swContent.includes("url.protocol === 'wss:'"), 'sw.js must bypass WebSockets');

    // Strict static asset whitelisting check
    assert.ok(swContent.includes('isStaticAsset'), 'sw.js must check isStaticAsset before caching');

    // Verify non-GET requests are ignored
    assert.ok(swContent.includes("request.method !== 'GET'"), 'sw.js must ignore non-GET requests');
  });

  test('Test 3: index.html PWA tags, safe-area viewport, and secure service worker registration', () => {
    const htmlPath = path.join(frontendDir, 'index.html');
    assert.ok(fs.existsSync(htmlPath), 'index.html must exist');

    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    // Manifest link
    assert.ok(htmlContent.includes('<link rel="manifest" href="/manifest.webmanifest"'), 'index.html must link to manifest.webmanifest');

    // Viewport meta with viewport-fit=cover
    assert.ok(htmlContent.includes('viewport-fit=cover'), 'index.html must include viewport-fit=cover for notch/gesture support');

    // Apple touch icon and theme-color
    assert.ok(htmlContent.includes('<meta name="theme-color"'), 'index.html must define theme-color');
    assert.ok(htmlContent.includes('<link rel="apple-touch-icon"'), 'index.html must define apple-touch-icon');

    // Secure service worker registration check
    assert.ok(htmlContent.includes("'serviceWorker' in navigator"), 'index.html must feature-detect serviceWorker');
    assert.ok(htmlContent.includes('window.isSecureContext'), 'index.html must verify isSecureContext before registering SW');
    assert.ok(htmlContent.includes("navigator.serviceWorker.register('/sw.js')"), 'index.html must register /sw.js');
  });

  test('Test 4: Offline warning indicators across App, Header, SOS Modal, and LoginScreen', () => {
    const appContent = fs.readFileSync(path.join(frontendDir, 'src', 'App.jsx'), 'utf8');
    const headerContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'Header.jsx'), 'utf8');
    const sosModalContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'SosTriggerModal.jsx'), 'utf8');
    const loginContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'LoginScreen.jsx'), 'utf8');

    // App.jsx offline state and banner
    assert.ok(appContent.includes('isOnline'), 'App.jsx must track isOnline state');
    assert.ok(appContent.includes("window.addEventListener('online'"), 'App.jsx must listen for online event');
    assert.ok(appContent.includes("window.addEventListener('offline'"), 'App.jsx must listen for offline event');
    assert.ok(appContent.includes('alert-banner-offline'), 'App.jsx must render alert-banner-offline when offline');
    assert.ok(appContent.includes('OFFLINE - NETWORK DISCONNECTED'), 'App.jsx must indicate offline status in emergency strip');

    // Header.jsx offline indicator
    assert.ok(headerContent.includes('offline-indicator-pill'), 'Header.jsx must include offline-indicator-pill');
    assert.ok(headerContent.includes('Offline'), 'Header.jsx must show Offline when !isOnline');

    // SosTriggerModal.jsx offline guard
    assert.ok(sosModalContent.includes('SOS Dispatch Unavailable Offline'), 'SosTriggerModal.jsx must display offline warning banner');
    assert.ok(sosModalContent.includes('Cannot dispatch SOS while offline'), 'SosTriggerModal.jsx must prevent dispatch when offline');
    assert.ok(sosModalContent.includes('OFFLINE - CONNECTIVITY REQUIRED TO DISPATCH'), 'SosTriggerModal submit button must indicate offline required');

    // LoginScreen.jsx offline warning
    assert.ok(loginContent.includes('Network Disconnected (Offline)'), 'LoginScreen.jsx must display offline warning');
  });

  test('Test 5: Real Geolocation security - secure origin check, no fake coordinates, error handling', () => {
    const sosModalContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'SosTriggerModal.jsx'), 'utf8');

    // Secure origin enforcement
    assert.ok(sosModalContent.includes('window.isSecureContext'), 'SosTriggerModal must check window.isSecureContext');

    // Zero fake coordinates guarantee
    assert.ok(!sosModalContent.includes('37.7749'), 'Must NOT have hardcoded San Francisco latitude (37.7749)');
    assert.ok(!sosModalContent.includes('-122.4194'), 'Must NOT have hardcoded San Francisco longitude (-122.4194)');

    // Explicit error states
    assert.ok(sosModalContent.includes("err.code === 1"), 'Must check code 1 (permission denied)');
    assert.ok(sosModalContent.includes("err.code === 3"), 'Must check code 3 (timeout)');
    assert.ok(sosModalContent.includes("'unavailable'"), 'Must handle position unavailable');
  });

  test('Test 6: SOS Shortcut flow safety - never auto-dispatches without explicit user confirmation', () => {
    const appContent = fs.readFileSync(path.join(frontendDir, 'src', 'App.jsx'), 'utf8');
    const sosModalContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'SosTriggerModal.jsx'), 'utf8');

    // App.jsx catches ?action=sos and only opens modal
    assert.ok(appContent.includes("params.get('action') === 'sos'"), 'App.jsx must parse action=sos');
    assert.ok(appContent.includes('setSosModalOpen(true)'), 'App.jsx opens modal on shortcut');
    assert.ok(!appContent.includes('triggerSos('), 'App.jsx must NEVER directly call triggerSos() on shortcut detection');

    // SosTriggerModal requires explicit confirmation checkbox and member selection
    assert.ok(sosModalContent.includes('acknowledgedDispatch'), 'SosTriggerModal requires explicit acknowledgedDispatch state');
    assert.ok(sosModalContent.includes('selectedMemberId'), 'SosTriggerModal requires explicit member selection');
  });

  test('Test 7: PWA install prompt wiring in Header and LoginScreen', () => {
    const appContent = fs.readFileSync(path.join(frontendDir, 'src', 'App.jsx'), 'utf8');
    const headerContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'Header.jsx'), 'utf8');
    const loginContent = fs.readFileSync(path.join(frontendDir, 'src', 'components', 'LoginScreen.jsx'), 'utf8');

    assert.ok(appContent.includes("window.addEventListener('beforeinstallprompt'"), 'App.jsx catches beforeinstallprompt event');
    assert.ok(headerContent.includes('btn-pwa-install'), 'Header.jsx has install button for eligible devices');
    assert.ok(loginContent.includes('btn-pwa-install'), 'LoginScreen.jsx has install button for eligible devices');
  });

  test('Test 8: API and WebSocket dynamic environment connectivity', () => {
    const apiContent = fs.readFileSync(path.join(frontendDir, 'src', 'services', 'api.js'), 'utf8');

    assert.ok(apiContent.includes('getWebSocketUrl'), 'api.js must export getWebSocketUrl');
    assert.ok(apiContent.includes("protocol === 'https:' ? 'wss:' : 'ws:'"), 'getWebSocketUrl must select ws or wss based on protocol');
    assert.ok(apiContent.includes('API_BASE_URL'), 'api.js must define configurable API_BASE_URL');
  });

});
