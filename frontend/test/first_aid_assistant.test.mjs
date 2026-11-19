import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const firstAidJsxPath = path.resolve(__dirname, '../src/components/FirstAidAssistant.jsx');
const headerJsxPath = path.resolve(__dirname, '../src/components/Header.jsx');
const mobileNavJsxPath = path.resolve(__dirname, '../src/components/MobileNav.jsx');
const appJsxPath = path.resolve(__dirname, '../src/App.jsx');
const apiJsPath = path.resolve(__dirname, '../src/services/api.js');
const indexCssPath = path.resolve(__dirname, '../src/index.css');
const protocolsDir = path.resolve(__dirname, '../../backend/app/knowledge/protocols');

describe('Day 3 & India Localization: First Aid Assistant Tests', () => {

  test('Test 1: Component exists, exports default, and displays required title and Indian authority sources', () => {
    assert.ok(fs.existsSync(firstAidJsxPath), 'FirstAidAssistant.jsx must exist');
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(
      source.includes('export default function FirstAidAssistant'),
      'FirstAidAssistant must export a default React component'
    );
    assert.ok(
      source.includes('AI First Aid Guide'),
      'Must contain title "AI First Aid Guide"'
    );
    assert.ok(
      source.includes('MoHFW') || source.includes('ICMR') || source.includes('Indian Red Cross'),
      'Must cite verified Indian health authorities (MoHFW, ICMR, Indian Red Cross)'
    );
  });

  test('Test 2: Primary emergency number is 112 with primary tel:112 call link', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('112'), 'Must display 112 as emergency response number');
    assert.ok(source.includes('href="tel:112"'), 'Primary call link must use href="tel:112"');
    assert.ok(
      source.includes('Call 112 (Primary)') || source.includes('Call 112'),
      'Primary call button must display 112'
    );
  });

  test('Test 3: Ambulance 108 is described accurately with locality context (e.g. KANIV 108 in Kerala)', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('108'), 'Must include 108 ambulance number');
    assert.ok(source.includes('href="tel:108"'), 'Must include clickable tel:108 link');
    assert.ok(
      source.includes('KANIV 108 in Kerala') || source.includes('Kerala'),
      'Must reference Kerala ambulance context (KANIV 108) where appropriate'
    );
    assert.ok(
      source.includes('availability') || source.includes('varies') || source.includes('depends'),
      'Must accurately inform user that 108 ambulance availability depends on state/locality'
    );
  });

  test('Test 4: Strict localization — zero UK emergency numbers (999, 111, 999 UK) in UI text', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(!source.includes('999'), 'FirstAidAssistant must NOT display 999');
    assert.ok(!source.includes('111 UK'), 'FirstAidAssistant must NOT display 111 UK');
    assert.ok(!source.includes('999 UK'), 'FirstAidAssistant must NOT display 999 UK');
    assert.ok(!source.includes('St John Ambulance'), 'FirstAidAssistant must NOT display UK St John Ambulance');
    assert.ok(!source.includes('NHS,'), 'FirstAidAssistant must NOT list UK NHS in intro description');
  });

  test('Test 5: Contains search input, submit button, and all 10 curated suggested topic buttons', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-search-input'), 'Must contain search input with dedicated CSS class');
    assert.ok(source.includes('first-aid-submit-btn'), 'Must contain submit button with dedicated CSS class');
    assert.ok(source.includes('type="submit"'), 'Submit button must have type="submit"');

    const expectedTopics = [
      'Adult CPR & AED',
      'Choking (Heimlich)',
      'Severe Bleeding',
      'Burns & Scalds',
      'Stroke (F.A.S.T.)',
      'Active Seizure',
      'Anaphylaxis (EpiPen)',
      'Heart Attack Signs',
      'Fractures & Splints',
      'Heatstroke vs Exhaustion'
    ];

    for (const topic of expectedTopics) {
      assert.ok(
        source.includes(topic),
        `Must include suggested topic button for "${topic}"`
      );
    }
  });

  test('Test 6: Renders step-by-step instructions, call guidance, red flags, and contraindications', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-steps-section'), 'Must contain steps section');
    assert.ok(source.includes('first-aid-step-num'), 'Must display step numbering');
    assert.ok(source.includes('first-aid-step-body'), 'Must display step text');
    assert.ok(source.includes('first-aid-call-guidance-box'), 'Must render emergency call guidance box');
    assert.ok(source.includes('first-aid-warnings-box'), 'Must render red flag warnings box');
    assert.ok(source.includes('first-aid-contraindications-box'), 'Must render what NOT to do box');
  });

  test('Test 7: Source citation container renders organization, title, URL link, and evidence drawer', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-source-citation-card'), 'Must contain source citation card');
    assert.ok(source.includes('first-aid-org-tag'), 'Must render organization tag');
    assert.ok(source.includes('first-aid-source-body'), 'Must render source title');
    assert.ok(source.includes('first-aid-source-link'), 'Must render clickable source URL');
    assert.ok(source.includes('target="_blank"'), 'Source URL must open in a new tab');
    assert.ok(source.includes('rel="noopener noreferrer"'), 'External link must use safe rel attributes');
    assert.ok(source.includes('first-aid-evidence-drawer'), 'Must contain evidence drawer');
    assert.ok(source.includes('<details'), 'Must use expandable <details> element for evidence excerpt');
  });

  test('Test 8: Loading, empty, error, and insufficient-evidence fallback states', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-loading-state'), 'Must define loading state UI');
    assert.ok(source.includes('Searching medical protocols...'), 'Loading state must show informative progress message');
    assert.ok(source.includes('first-aid-empty-state'), 'Must define initial empty state UI');
    assert.ok(source.includes('first-aid-error-banner'), 'Must define error banner');
    assert.ok(source.includes('first-aid-retry-btn'), 'Must provide retry button on error');
    assert.ok(source.includes('first-aid-fallback-card'), 'Must render fallback card when evidence is insufficient');
    assert.ok(source.includes('No verified protocol found matching that exact query'), 'Fallback card must state lack of match');
  });

  test('Test 9: Clinical disclaimer is explicitly present on the guide screen', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-result-disclaimer'), 'Must contain first-aid-result-disclaimer container');
    assert.ok(source.includes('Clinical Disclaimer:'), 'Must contain explicit clinical disclaimer label');
    assert.ok(
      source.includes('does not constitute professional medical diagnosis or care') ||
      source.includes('does not replace professional medical advice'),
      'Must advise that retrieved guidance does not replace professional care'
    );
  });

  test('Test 10: Strict isolation — zero SOS triggers, incident creation, or mutations', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(!source.includes('createEmergency'), 'FirstAidAssistant must NOT call createEmergency');
    assert.ok(!source.includes('triggerSos'), 'FirstAidAssistant must NOT trigger SOS');
    assert.ok(!source.includes('createIncident'), 'FirstAidAssistant must NOT create incidents');
    assert.ok(!source.includes('localStorage.setItem'), 'Must NOT store sensitive health queries in localStorage');
  });

  test('Test 11: Navigation tabs in Header and MobileNav', () => {
    const headerSource = fs.readFileSync(headerJsxPath, 'utf8');
    const mobileNavSource = fs.readFileSync(mobileNavJsxPath, 'utf8');
    const appSource = fs.readFileSync(appJsxPath, 'utf8');

    assert.ok(headerSource.includes('First Aid Guide'), 'Header must render tab label "First Aid Guide"');
    assert.ok(mobileNavSource.includes('data-testid="mobile-tab-first-aid"'), 'MobileNav must provide data-testid');
    assert.ok(appSource.includes("activeTab === 'first-aid'") && appSource.includes('<FirstAidAssistant />'), 'App must render tab');
  });

  test('Test 12: All 10 protocol files exist and are verified with India 112/108 guidance', () => {
    const protocolFiles = fs.readdirSync(protocolsDir).filter(f => f.endsWith('.json'));
    assert.strictEqual(protocolFiles.length, 10, 'Must have exactly 10 protocol files');

    for (const pf of protocolFiles) {
      const content = fs.readFileSync(path.join(protocolsDir, pf), 'utf8');
      const data = JSON.parse(content);

      // Verify structure
      assert.ok(data.protocol_id, `Missing protocol_id in ${pf}`);
      assert.ok(data.topic, `Missing topic in ${pf}`);
      assert.ok(data.actionable_steps && data.actionable_steps.length >= 3, `Steps missing in ${pf}`);
      assert.ok(data.critical_warnings && data.critical_warnings.length >= 1, `Warnings missing in ${pf}`);
      assert.ok(data.source_metadata, `Source metadata missing in ${pf}`);
      assert.ok(data.source_metadata.url.startsWith('https://'), `Invalid URL in ${pf}`);

      // Verify India emergency numbers present and UK absent
      assert.ok(data.emergency_call_guidance.includes('112'), `112 missing from ${pf}`);
      assert.ok(data.emergency_call_guidance.includes('108'), `108 missing from ${pf}`);
      assert.ok(!content.includes('999'), `Disallowed 999 found in ${pf}`);
      assert.ok(!content.includes('911'), `Disallowed 911 found in ${pf}`);
      assert.ok(!content.includes('NHS'), `Disallowed NHS found in ${pf}`);
      assert.ok(!content.includes('St John Ambulance'), `Disallowed St John Ambulance in ${pf}`);
    }
  });

});
