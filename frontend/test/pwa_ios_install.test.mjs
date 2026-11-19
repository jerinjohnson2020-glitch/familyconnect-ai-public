import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  isIosDevice,
  isIosSafari,
  isStandaloneMode,
  shouldShowIosInstallPrompt
} from '../src/utils/pwaInstall.js';

describe('Phase 7: PWA iOS Installation Logic & Accessibility Tests', () => {

  test('IOS-01 [Behavioral]: Correctly identifies iPhone and iPad Safari user agents', () => {
    const iphoneSafari = {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
      vendor: 'Apple Computer, Inc.'
    };
    assert.equal(isIosDevice(iphoneSafari), true);
    assert.equal(isIosSafari(iphoneSafari), true);

    const ipadSafari = {
      userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
      vendor: 'Apple Computer, Inc.'
    };
    assert.equal(isIosDevice(ipadSafari), true);
    assert.equal(isIosSafari(ipadSafari), true);
  });

  test('IOS-02 [Behavioral]: Identifies modern iPadOS 13+ desktop-class Safari browsing mode', () => {
    const ipadosDesktop = {
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
      platform: 'MacIntel',
      maxTouchPoints: 5,
      vendor: 'Apple Computer, Inc.'
    };
    assert.equal(isIosDevice(ipadosDesktop), true);
    assert.equal(isIosSafari(ipadosDesktop), true);
  });

  test('IOS-03 [Behavioral]: Strictly excludes third-party iOS browsers (Chrome, Firefox, Edge, Opera)', () => {
    const chromeIos = {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1'
    };
    assert.equal(isIosDevice(chromeIos), true);
    assert.equal(isIosSafari(chromeIos), false, 'CriOS must not be identified as Safari');

    const firefoxIos = {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/123.0 Mobile/15E148 Safari/605.1.15'
    };
    assert.equal(isIosSafari(firefoxIos), false, 'FxiOS must not be identified as Safari');

    const edgeIos = {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 EdgiOS/122.0.2365.67 Mobile/15E148 Safari/605.1.15'
    };
    assert.equal(isIosSafari(edgeIos), false, 'EdgiOS must not be identified as Safari');

    const operaIos = {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) OPT/3.5.2 Mobile/15E148 Safari/605.1.15'
    };
    assert.equal(isIosSafari(operaIos), false, 'OPT/Opera must not be identified as Safari');
  });

  test('IOS-04 [Behavioral]: Strictly excludes Android and desktop operating systems', () => {
    const androidChrome = {
      userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.90 Mobile Safari/537.36'
    };
    assert.equal(isIosDevice(androidChrome), false);
    assert.equal(isIosSafari(androidChrome), false);

    const macosDesktop = {
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
      platform: 'MacIntel',
      maxTouchPoints: 0 // Desktop Mac without touchscreen
    };
    assert.equal(isIosDevice(macosDesktop), false);
    assert.equal(isIosSafari(macosDesktop), false);

    const windowsDesktop = {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
      platform: 'Win32'
    };
    assert.equal(isIosDevice(windowsDesktop), false);
    assert.equal(isIosSafari(windowsDesktop), false);
  });

  test('IOS-05 [Behavioral]: Standalone / installed mode detection', () => {
    const standaloneMatchMedia = {
      matchMedia: (query) => ({ matches: query === '(display-mode: standalone)' }),
      navigator: { standalone: false }
    };
    assert.equal(isStandaloneMode(standaloneMatchMedia), true);

    const iosBookmarkStandalone = {
      matchMedia: () => ({ matches: false }),
      navigator: { standalone: true }
    };
    assert.equal(isStandaloneMode(iosBookmarkStandalone), true);

    const browserTab = {
      matchMedia: () => ({ matches: false }),
      navigator: { standalone: false }
    };
    assert.equal(isStandaloneMode(browserTab), false);
  });

  test('IOS-06 [Behavioral]: shouldShowIosInstallPrompt composite visibility rules', () => {
    const iphoneSafari = {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1'
    };

    // 1. iOS Safari in browser tab: should show
    const showInBrowser = shouldShowIosInstallPrompt({
      isIos: true,
      isStandalone: false,
      hasBeforeInstallPrompt: false
    });
    assert.equal(showInBrowser, true, 'Should show prompt in iOS Safari browser tab');

    // 2. Already installed (standalone): should NOT show
    const hideWhenInstalled = shouldShowIosInstallPrompt({
      isIos: true,
      isStandalone: true,
      hasBeforeInstallPrompt: false
    });
    assert.equal(hideWhenInstalled, false, 'Must hide prompt when app is installed in standalone mode');

    // 3. Android beforeinstallprompt active: should NOT show iOS prompt (avoids duplicate prompts)
    const hideWhenAndroidPromptActive = shouldShowIosInstallPrompt({
      isIos: false,
      isStandalone: false,
      hasBeforeInstallPrompt: true
    });
    assert.equal(hideWhenAndroidPromptActive, false, 'Must not show iOS prompt when beforeinstallprompt is active');

    // 4. Non-iOS: should NOT show
    const hideOnDesktop = shouldShowIosInstallPrompt({
      isIos: false,
      isStandalone: false,
      hasBeforeInstallPrompt: false
    });
    assert.equal(hideOnDesktop, false, 'Must not show iOS prompt on non-iOS devices');
  });

});
