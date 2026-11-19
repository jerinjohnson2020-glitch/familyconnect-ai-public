/**
 * FamilyConnect AI - Progressive Web App & iOS Installation Utilities
 *
 * Provides robust platform detection and installation state checks,
 * distinguishing iOS Safari from third-party wrappers (Chrome/Firefox for iOS)
 * and respecting standalone / installed app mode.
 */

/**
 * Detects whether the current device is running iOS (iPhone, iPad, or iPod),
 * including iPadOS 13+ desktop-class browsing mode.
 */
export function isIosDevice(nav = (typeof navigator !== 'undefined' ? navigator : null)) {
  if (!nav) return false;
  const ua = nav.userAgent || nav.vendor || '';
  const isIosUA = /iphone|ipad|ipod/i.test(ua);
  const isIpadOS = nav.platform === 'MacIntel' && typeof nav.maxTouchPoints === 'number' && nav.maxTouchPoints > 1;
  return isIosUA || isIpadOS;
}

/**
 * Detects whether the browser is iOS Safari, strictly excluding
 * third-party iOS browsers (Chrome, Firefox, Edge, Opera) that do not
 * support Apple's native Safari Share Sheet "Add to Home Screen" workflow.
 */
export function isIosSafari(nav = (typeof navigator !== 'undefined' ? navigator : null)) {
  if (!isIosDevice(nav)) return false;
  const ua = (nav.userAgent || '').toLowerCase();
  // CriOS = Chrome iOS, FxiOS = Firefox iOS, EdgiOS = Edge iOS, OPiOS/OPT = Opera iOS
  const isAlternativeBrowser = /crios|fxios|edgios|opios|opt/i.test(ua);
  return !isAlternativeBrowser;
}

/**
 * Checks whether the application is already running in an installed standalone window
 * (PWA standalone display mode or iOS full-screen home-screen bookmark).
 */
export function isStandaloneMode(win = (typeof window !== 'undefined' ? window : null)) {
  if (!win) return false;
  const matchMedia = typeof win.matchMedia === 'function' && win.matchMedia('(display-mode: standalone)').matches;
  const navStandalone = win.navigator && win.navigator.standalone === true;
  return Boolean(matchMedia || navStandalone);
}

/**
 * Determines whether the iOS installation guidance button/card should be presented to the user.
 * Returns true ONLY when:
 * 1. The device is iOS Safari.
 * 2. The app is NOT already running in standalone/installed mode.
 * 3. The native Android beforeinstallprompt is NOT active (preventing duplicate prompts).
 */
export function shouldShowIosInstallPrompt({
  isIos = null,
  isStandalone = null,
  hasBeforeInstallPrompt = false,
  nav = null,
  win = null
} = {}) {
  const activeStandalone = isStandalone !== null ? isStandalone : isStandaloneMode(win);
  if (activeStandalone) return false;
  if (hasBeforeInstallPrompt) return false;

  const activeIos = isIos !== null ? isIos : isIosSafari(nav);
  return Boolean(activeIos);
}
