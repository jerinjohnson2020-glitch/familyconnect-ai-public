import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const firstAidJsxPath = path.resolve(__dirname, '../src/components/FirstAidAssistant.jsx');
const indexCssPath = path.resolve(__dirname, '../src/index.css');

describe('Stage 3: Local LLM AI Grounded Summary Frontend Integration Tests', () => {

  test('Test 1: FirstAidAssistant.jsx includes AI Grounded Summary container with data-testid', () => {
    assert.ok(fs.existsSync(firstAidJsxPath), 'FirstAidAssistant.jsx must exist');
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(
      source.includes('data-testid="first-aid-llm-summary"'),
      'Must contain data-testid="first-aid-llm-summary"'
    );
    assert.ok(
      source.includes('AI Grounded Summary'),
      'Must contain heading "AI Grounded Summary"'
    );
    assert.ok(
      source.includes('first-aid-llm-summary-box'),
      'Must contain container class first-aid-llm-summary-box'
    );
  });

  test('Test 2: Displays model badge and latency pill when synthesized_explanation is present', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(
      source.includes('first-aid-llm-badge'),
      'Must render model badge class first-aid-llm-badge'
    );
    assert.ok(
      source.includes('llama3.2:3b') || source.includes('result.llm_model'),
      'Must reference local model llama3.2:3b or dynamic llm_model field'
    );
    assert.ok(
      source.includes('result.llm_latency_ms'),
      'Must conditionally render llm_latency_ms when available'
    );
  });

  test('Test 3: Clearly distinguishes generated explanation from verified protocol steps', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(
      source.includes('first-aid-llm-summary-footer'),
      'Must contain summary footer with explicit provenance disclaimer'
    );
    assert.ok(
      source.includes('Synthesized locally') || source.includes('retrieved guideline evidence'),
      'Must inform user that summary is synthesized locally from retrieved guideline evidence'
    );
    assert.ok(
      source.includes('Never overrides emergency instructions') || source.includes('follow the verified'),
      'Must instruct user to follow verified clinical procedures below'
    );
  });

  test('Test 4: Displays safe fallback notice when synthesized_explanation is unavailable or null', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(
      source.includes('first-aid-llm-fallback-note'),
      'Must include fallback note class first-aid-llm-fallback-note'
    );
    assert.ok(
      source.includes('authoritative clinical instructions') || source.includes('verified health guidelines'),
      'Fallback note must explain that authoritative instructions from verified guidelines are displayed'
    );
  });

  test('Test 5: Preserves emergency dialing directives (112 & 108) and does not falsely claim call placed', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('href="tel:112"'), 'Must preserve tel:112 call button');
    assert.ok(source.includes('href="tel:108"'), 'Must preserve tel:108 call button');
    assert.ok(!source.includes('call has been placed'), 'Must not claim an emergency call has been automatically placed');
    assert.ok(!source.includes('dispatching ambulance now'), 'Must not claim emergency dispatch has been triggered');
  });

  test('Test 6: Preserves existing protocol steps, warnings, contraindications, and citations', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-warnings-box'), 'Must preserve critical warnings box');
    assert.ok(source.includes('first-aid-steps-section'), 'Must preserve actionable steps section');
    assert.ok(source.includes('first-aid-contraindications-box'), 'Must preserve contraindications box');
    assert.ok(source.includes('first-aid-evidence-drawer'), 'Must preserve evidence excerpts drawer');
    assert.ok(source.includes('first-aid-source-citation-card'), 'Must preserve verifiable source citation card');
    assert.ok(source.includes('first-aid-result-disclaimer'), 'Must preserve mandatory disclaimer footer');
  });

  test('Test 7: index.css defines accessible styles for AI Grounded Summary in both themes', () => {
    assert.ok(fs.existsSync(indexCssPath), 'index.css must exist');
    const css = fs.readFileSync(indexCssPath, 'utf8');

    assert.ok(css.includes('.first-aid-llm-summary-box'), 'CSS must define .first-aid-llm-summary-box');
    assert.ok(css.includes('.first-aid-llm-summary-header'), 'CSS must define .first-aid-llm-summary-header');
    assert.ok(css.includes('.first-aid-llm-badge'), 'CSS must define .first-aid-llm-badge');
    assert.ok(css.includes('.first-aid-llm-summary-text'), 'CSS must define .first-aid-llm-summary-text');
    assert.ok(css.includes('.first-aid-llm-summary-footer'), 'CSS must define .first-aid-llm-summary-footer');
    assert.ok(css.includes('.first-aid-llm-fallback-note'), 'CSS must define .first-aid-llm-fallback-note');
    assert.ok(css.includes('.first-aid-ai-status-badge'), 'CSS must define .first-aid-ai-status-badge');
  });

  test('Test 8: Protocol header renders Local AI status label based on actual response status', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-ai-status-badge'), 'Must include first-aid-ai-status-badge class');
    assert.ok(source.includes('Local AI explanation available'), 'Must display "Local AI explanation available" when synthesized explanation exists');
    assert.ok(source.includes('Using verified guidance only'), 'Must display "Using verified guidance only" fallback label');
    assert.ok(source.includes('AI Timeout'), 'Must display AI Timeout indicator when llm_status is TIMEOUT');
  });

  test('Test 9: Loading state displays informative progress for retrieval and local AI synthesis', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-loading-state'), 'Must contain loading state container');
    assert.ok(source.includes('Searching medical protocols...'), 'Must display clear loading heading');
    assert.ok(source.includes('llama3.2:3b') || source.includes('local AI'), 'Must communicate local AI synthesis in progress');
  });

  test('Test 10: Fallback notice provides contextual explanations for timeout and offline states', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-llm-timeout-note'), 'Must include data-testid="first-aid-llm-timeout-note"');
    assert.ok(source.includes('Local AI synthesis timed out'), 'Must inform user when local AI synthesis timed out');
    assert.ok(source.includes('first-aid-llm-offline-note'), 'Must include data-testid="first-aid-llm-offline-note"');
  });

});
