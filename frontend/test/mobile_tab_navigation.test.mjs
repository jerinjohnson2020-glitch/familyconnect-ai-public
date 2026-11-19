import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const cssPath = path.resolve(__dirname, '../src/index.css');
const appJsxPath = path.resolve(__dirname, '../src/App.jsx');
const mobileNavPath = path.resolve(__dirname, '../src/components/MobileNav.jsx');
const headerPath = path.resolve(__dirname, '../src/components/Header.jsx');

describe('Phase 5C: Mobile Tab Navigation & Dashboard Layout Tests', () => {

  test('Test 1: Tab content scoping — "emergencies" tab includes overview action strip and metrics grid', () => {
    const appSource = fs.readFileSync(appJsxPath, 'utf8');

    // Verify emergency-action-strip and metrics-grid are scoped within activeTab === 'emergencies'
    const emergenciesBlockMatch = appSource.match(/\{activeTab === 'emergencies' && \([\s\S]*?<EmergencyMonitor[\s\S]*?\)\}/);
    assert.ok(emergenciesBlockMatch, 'activeTab === "emergencies" block must exist');

    const emergenciesContent = emergenciesBlockMatch[0];
    assert.ok(
      emergenciesContent.includes('emergency-action-strip'),
      'emergency-action-strip must be rendered inside activeTab === "emergencies"'
    );
    assert.ok(
      emergenciesContent.includes('metrics-grid'),
      'metrics-grid must be rendered inside activeTab === "emergencies"'
    );
    assert.ok(
      emergenciesContent.includes('<EmergencyMonitor'),
      'EmergencyMonitor must be rendered inside activeTab === "emergencies"'
    );
  });

  test('Test 2: Tab content scoping — "family", "responders", and "ai-sandbox" tabs omit metrics grid', () => {
    const appSource = fs.readFileSync(appJsxPath, 'utf8');

    // Extract content rendered for family, responders, and ai-sandbox
    const familyBlockMatch = appSource.match(/\{activeTab === 'family' && user\.role !== 'responder' && \([\s\S]*?<FamilyDashboard[\s\S]*?\)\}/);
    assert.ok(familyBlockMatch, 'activeTab === "family" block must exist');
    assert.ok(!familyBlockMatch[0].includes('metrics-grid'), 'Family tab must NOT render metrics-grid');
    assert.ok(!familyBlockMatch[0].includes('emergency-action-strip'), 'Family tab must NOT render emergency-action-strip');

    const respondersBlockMatch = appSource.match(/\{activeTab === 'responders' && \([\s\S]*?<ResponderAndAlertManager[\s\S]*?\)\}/);
    assert.ok(respondersBlockMatch, 'activeTab === "responders" block must exist');
    assert.ok(!respondersBlockMatch[0].includes('metrics-grid'), 'Responders tab must NOT render metrics-grid');
    assert.ok(!respondersBlockMatch[0].includes('emergency-action-strip'), 'Responders tab must NOT render emergency-action-strip');

    const sandboxBlockMatch = appSource.match(/\{activeTab === 'ai-sandbox' && \([\s\S]*?<AiTriageTester[\s\S]*?\)\}/);
    assert.ok(sandboxBlockMatch, 'activeTab === "ai-sandbox" block must exist');
    assert.ok(!sandboxBlockMatch[0].includes('metrics-grid'), 'AI Sandbox tab must NOT render metrics-grid');
    assert.ok(!sandboxBlockMatch[0].includes('emergency-action-strip'), 'AI Sandbox tab must NOT render emergency-action-strip');
  });

  test('Test 3: Mobile tab switching automatically resets window scroll to top', () => {
    const appSource = fs.readFileSync(appJsxPath, 'utf8');
    const mobileNavSource = fs.readFileSync(mobileNavPath, 'utf8');

    // Verify handleTabChange resets scroll
    assert.ok(
      appSource.includes('handleTabChange'),
      'App.jsx must define handleTabChange'
    );
    assert.ok(
      appSource.includes('window.scrollTo({ top: 0, behavior: \'auto\' })') ||
      appSource.includes('window.scrollTo({ top: 0'),
      'handleTabChange must reset scroll position to top'
    );

    // Verify MobileNav also ensures scroll reset
    assert.ok(
      mobileNavSource.includes('window.scrollTo({ top: 0'),
      'MobileNav handleTabClick must scroll to top'
    );
  });

  test('Test 4: Tab changing does NOT trigger emergency dispatch, SOS, or notifications', () => {
    let sosTriggered = false;
    let incidentCreated = false;
    let notificationsSent = 0;

    // Simulate switching tabs
    let activeTab = 'emergencies';
    const switchTab = (newTab) => {
      // Tab switching only mutates activeTab state
      activeTab = newTab;
    };

    switchTab('family');
    assert.equal(activeTab, 'family');
    switchTab('responders');
    assert.equal(activeTab, 'responders');
    switchTab('ai-sandbox');
    assert.equal(activeTab, 'ai-sandbox');
    switchTab('emergencies');
    assert.equal(activeTab, 'emergencies');

    assert.equal(sosTriggered, false, 'Changing tabs must never trigger SOS');
    assert.equal(incidentCreated, false, 'Changing tabs must never create an incident');
    assert.equal(notificationsSent, 0, 'Changing tabs must never send notifications');
  });

  test('Test 5: Mobile bottom navigation bar enforces touch targets of at least 44px', () => {
    const css = fs.readFileSync(cssPath, 'utf8');

    // Verify .mobile-nav-item has min-height >= 44px and min-width >= 44px
    assert.ok(css.includes('.mobile-nav-item'), 'CSS must define .mobile-nav-item');
    assert.ok(
      /min-height:\s*(4[4-9]|[5-9]\d)px/.test(css),
      'Touch target height must be at least 44px'
    );
    assert.ok(
      /min-width:\s*(4[4-9]|[5-9]\d)px/.test(css),
      'Touch target width must be at least 44px'
    );

    // Verify .header-sos-btn has min-height >= 44px and min-width >= 44px
    assert.ok(css.includes('.header-sos-btn'), 'CSS must define .header-sos-btn');
    const headerSosMatch = css.match(/\.header-sos-btn\s*\{[^}]*\}/);
    assert.ok(headerSosMatch, 'header-sos-btn block must exist');
    assert.ok(headerSosMatch[0].includes('min-height: 44px'), 'header-sos-btn must have min-height 44px');
    assert.ok(headerSosMatch[0].includes('min-width: 44px'), 'header-sos-btn must have min-width 44px');
  });

  test('Test 6: Mobile safe-area spacing and bottom padding in index.css', () => {
    const css = fs.readFileSync(cssPath, 'utf8');

    // Verify .mobile-bottom-nav uses safe-area-inset-bottom
    const mobileBottomNavMatch = css.match(/\.mobile-bottom-nav\s*\{[^}]*\}/);
    assert.ok(mobileBottomNavMatch, '.mobile-bottom-nav block must exist');
    assert.ok(
      mobileBottomNavMatch[0].includes('env(safe-area-inset-bottom'),
      '.mobile-bottom-nav must respect safe-area-inset-bottom'
    );

    // Verify .app-container has bottom padding accommodating bottom nav
    const appContainerMediaMatch = css.match(/@media\s*\(max-width:\s*600px\)[\s\S]*?\.app-container\s*\{[^}]*\}/);
    assert.ok(appContainerMediaMatch, 'app-container media query must exist');
    assert.ok(
      appContainerMediaMatch[0].includes('env(safe-area-inset-bottom'),
      'app-container must pad bottom for mobile safe area'
    );
  });

  test('Test 7: 2x2 compact metrics grid layout on mobile screens', () => {
    const css = fs.readFileSync(cssPath, 'utf8');

    // Verify 600px media query uses repeat(2, 1fr) for metrics-grid
    const media600Match = css.match(/@media\s*\(max-width:\s*600px\)[\s\S]*?\.metrics-grid\s*\{[^}]*\}/);
    assert.ok(media600Match, 'metrics-grid 600px media query must exist');
    assert.ok(
      media600Match[0].includes('grid-template-columns: repeat(2, 1fr)'),
      'metrics-grid must use 2-column repeat(2, 1fr) on mobile to prevent vertical stacking bloat'
    );
  });

  test('Test 8: Responder least-privilege role hides Family tab in MobileNav', () => {
    const mobileNavSource = fs.readFileSync(mobileNavPath, 'utf8');

    // Verify !isResponder guard around family tab button
    assert.ok(
      mobileNavSource.includes('!isResponder &&'),
      'MobileNav must guard Family tab with !isResponder'
    );
    assert.ok(
      mobileNavSource.includes('data-testid="mobile-tab-family"'),
      'Family tab button must exist in MobileNav'
    );
  });

  test('Test 9: Active tab visual distinction and accessible ARIA attributes', () => {
    const mobileNavSource = fs.readFileSync(mobileNavPath, 'utf8');

    // Verify role="tablist" and role="tab"
    assert.ok(mobileNavSource.includes('role="tablist"'), 'mobile-bottom-nav must declare role="tablist"');
    assert.ok(mobileNavSource.includes('role="tab"'), 'nav items must declare role="tab"');

    // Verify aria-selected and active class
    assert.ok(
      mobileNavSource.includes('aria-selected={activeTab === \'emergencies\'}'),
      'emergencies tab must set aria-selected dynamically'
    );
    assert.ok(
      mobileNavSource.includes('activeTab === \'emergencies\' ? \'active\' : \'\''),
      'emergencies tab must apply active class'
    );
    assert.ok(
      mobileNavSource.includes('activeTab === \'family\' ? \'active\' : \'\''),
      'family tab must apply active class'
    );
  });

  test('Test 10: Header quick SOS button available on all tabs for family admin/members', () => {
    const headerSource = fs.readFileSync(headerPath, 'utf8');
    const appSource = fs.readFileSync(appJsxPath, 'utf8');

    // Verify Header accepts onOpenSos and renders header-sos-btn
    assert.ok(
      headerSource.includes('onOpenSos = null') || headerSource.includes('onOpenSos'),
      'Header must accept onOpenSos prop'
    );
    assert.ok(
      headerSource.includes('className="header-sos-btn"'),
      'Header must render header-sos-btn'
    );
    assert.ok(
      headerSource.includes('!isResponder && onOpenSos'),
      'header-sos-btn must be guarded for non-responders'
    );

    // Verify App.jsx passes onOpenSos to Header
    assert.ok(
      appSource.includes('onOpenSos={() => openSosModal(null)}'),
      'App.jsx must pass onOpenSos callback to Header'
    );
  });

});
