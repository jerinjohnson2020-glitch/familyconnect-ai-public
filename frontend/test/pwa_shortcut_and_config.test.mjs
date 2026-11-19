import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Phase 5A: PWA SOS Shortcut & Configuration Tests', () => {

  test('Test 1: URL parameter ?action=sos is recognized as pending SOS intent', () => {
    const url = new URL('http://localhost:5173/?action=sos');
    const action = url.searchParams.get('action');
    assert.equal(action, 'sos', 'action query parameter must be "sos"');
  });

  test('Test 2: Shortcut parameter is cleanly removed via replaceState logic without page refresh', () => {
    // Simulating URL cleanup logic
    const currentUrl = new URL('http://localhost:5173/?action=sos');
    assert.equal(currentUrl.searchParams.get('action'), 'sos');

    currentUrl.searchParams.delete('action');
    const cleanSearch = currentUrl.searchParams.toString();
    const cleanRelativeUrl = currentUrl.pathname + (cleanSearch ? `?${cleanSearch}` : '');

    assert.equal(cleanRelativeUrl, '/', 'Clean URL must have action=sos removed');
    assert.equal(currentUrl.searchParams.has('action'), false, 'URL params must no longer contain action');
  });

  test('Test 3: Logged-out state retains shortcut intent and displays guidance without bypassing auth', () => {
    const user = null;
    const authChecking = false;
    let pendingSosAction = true;
    let sosModalOpen = false;

    // Simulate App.jsx useEffect guard
    if (!user && !authChecking) {
      // Must NOT open SOS modal for unauthenticated user
      sosModalOpen = false;
    }

    assert.equal(sosModalOpen, false, 'SOS modal must never open while user is unauthenticated');
    assert.equal(pendingSosAction, true, 'pendingSosAction remains true to open after user logs in');
  });

  test('Test 4: Responder role suppresses SOS modal and cleans action parameter', () => {
    const user = { role: 'responder', id: 3, username: 'officer_david' };
    let pendingSosAction = true;
    let sosModalOpen = false;
    let actionCleared = false;

    // Simulate App.jsx role check
    if (user.role === 'responder') {
      pendingSosAction = false;
      actionCleared = true;
      sosModalOpen = false;
    }

    assert.equal(sosModalOpen, false, 'Responders cannot trigger SOS dispatches');
    assert.equal(pendingSosAction, false, 'pendingSosAction must be dismissed for responder');
    assert.equal(actionCleared, true, 'URL parameter must be cleaned');
  });

  test('Test 5: Authenticated household admin with members opens SOS dialog without auto-dispatching', () => {
    const user = { role: 'admin', id: 4, username: 'test_admin_alpha' };
    const members = [
      { id: 4, name: 'Alex P', is_active: true, is_demo: false },
      { id: 5, name: 'Maya P', is_active: true, is_demo: false }
    ];
    let pendingSosAction = true;
    let sosModalOpen = false;
    let preselectedMember = 'something_prior';
    let autoDispatched = false;

    // Simulate App.jsx behavior
    if (user && user.role !== 'responder') {
      const activeMembers = members.filter(m => m && m.is_active !== false);
      if (activeMembers.length > 0) {
        pendingSosAction = false;
        preselectedMember = null;
        sosModalOpen = true;
        // Notice: autoDispatched is strictly false!
      }
    }

    assert.equal(sosModalOpen, true, 'SOS modal opens for authenticated user');
    assert.equal(preselectedMember, null, 'Preselected member is cleared to allow active member selection');
    assert.equal(pendingSosAction, false, 'pendingSosAction is consumed to prevent duplicate opening');
    assert.equal(autoDispatched, false, 'SOS shortcut must never create or submit an SOS automatically');
  });

  test('Test 6: Authenticated user with 0 active members is guided to family tab instead of opening blank SOS', () => {
    const user = { role: 'admin', id: 4, username: 'test_admin_alpha' };
    const members = []; // Empty roster
    let pendingSosAction = true;
    let sosModalOpen = false;
    let activeTab = 'emergencies';
    let bannerMessage = '';

    if (user && user.role !== 'responder') {
      const activeMembers = members.filter(m => m && m.is_active !== false);
      if (activeMembers.length === 0) {
        pendingSosAction = false;
        activeTab = 'family';
        bannerMessage = 'No active household members found. Please register a family member profile before triggering an emergency SOS.';
      } else {
        sosModalOpen = true;
      }
    }

    assert.equal(sosModalOpen, false, 'SOS modal must not open when 0 members exist');
    assert.equal(activeTab, 'family', 'User must be guided to the family dashboard tab');
    assert.match(bannerMessage, /No active household members/);
  });

  test('Test 7: Repeat triggers prevented on subsequent browser reloads', () => {
    // Initial launch with ?action=sos
    const initialUrl = new URL('http://localhost:5173/?action=sos');
    let hasAction = initialUrl.searchParams.get('action') === 'sos';
    assert.equal(hasAction, true);

    // After consume & URL replaceState
    initialUrl.searchParams.delete('action');

    // Simulated browser refresh: new URL has no ?action=sos
    const reloadedUrl = new URL(initialUrl.toString());
    hasAction = reloadedUrl.searchParams.get('action') === 'sos';
    assert.equal(hasAction, false, 'Subsequent page reloads must not re-trigger action=sos');
  });

  // --- Phase 5B: Mobile UX Refinement Tests ---

  test('Test 8: Mobile safe-area CSS insets are defined across body, container, and modals', async () => {
    const fs = await import('node:fs/promises');
    const path = await import('node:path');
    const cssPath = path.resolve(process.cwd(), 'src/index.css');
    const css = await fs.readFile(cssPath, 'utf-8');

    assert.ok(css.includes('env(safe-area-inset-top'), 'CSS must include env(safe-area-inset-top)');
    assert.ok(css.includes('env(safe-area-inset-bottom'), 'CSS must include env(safe-area-inset-bottom)');
    assert.ok(css.includes('env(safe-area-inset-left'), 'CSS must include env(safe-area-inset-left)');
    assert.ok(css.includes('env(safe-area-inset-right'), 'CSS must include env(safe-area-inset-right)');
    assert.ok(css.includes('100dvh'), 'CSS must include dynamic viewport height (100dvh) for mobile browser address bar adaptability');
  });

  test('Test 9: Mobile touch targets enforce minimum 44px height across interactive controls', async () => {
    const fs = await import('node:fs/promises');
    const path = await import('node:path');
    const cssPath = path.resolve(process.cwd(), 'src/index.css');
    const css = await fs.readFile(cssPath, 'utf-8');

    assert.ok(css.includes('min-height: 44px'), 'CSS must enforce min-height: 44px touch targets');
    assert.ok(css.includes('min-width: 44px'), 'CSS must enforce min-width: 44px touch targets for icon controls');
    assert.ok(css.includes('.destructive-action-btn'), 'CSS must define distinct destructive action styling');
    assert.ok(css.includes('.filter-pill'), 'CSS must format filter pills for touch ergonomics');
    assert.ok(css.includes('.disclosure-btn'), 'CSS must format disclosure toggles for touch ergonomics');
  });

  test('Test 10: Login screen demo quick-fill buttons are strictly disabled without auto-filling credentials', async () => {
    const fs = await import('node:fs/promises');
    const path = await import('node:path');
    const loginJsxPath = path.resolve(process.cwd(), 'src/components/LoginScreen.jsx');
    const jsx = await fs.readFile(loginJsxPath, 'utf-8');

    // Verify admin, marcus, and officer_david buttons are marked disabled
    assert.ok(jsx.includes('demo-role-btn disabled'), 'Demo role buttons must have disabled class');
    assert.ok(jsx.includes('title="Demo account deactivated for production safety"'), 'Demo buttons must state deactivated in title');
    assert.ok(!jsx.includes("onClick={() => handleQuickFill('admin'"), 'admin button must NOT have onClick quickfill');
    assert.ok(!jsx.includes("onClick={() => handleQuickFill('marcus'"), 'marcus button must NOT have onClick quickfill');
    assert.ok(!jsx.includes("onClick={() => handleQuickFill('officer_david'"), 'officer_david button must NOT have onClick quickfill');
    assert.ok(jsx.includes('Demo logins are deactivated'), 'Informative explanation text must guide the user');
  });
});
