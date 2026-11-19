import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const firstAidJsxPath = path.resolve(__dirname, '../src/components/FirstAidAssistant.jsx');
const apiJsPath = path.resolve(__dirname, '../src/services/api.js');
const indexCssPath = path.resolve(__dirname, '../src/index.css');

describe('ChatGPT-Style Conversational First Aid Assistant Tests', () => {

  test('Test 1: Full-height conversational chat container & compact header exist', () => {
    assert.ok(fs.existsSync(firstAidJsxPath), 'FirstAidAssistant.jsx must exist');
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('first-aid-container chat-mode'), 'Must use chat-mode container layout');
    assert.ok(source.includes('chat-header'), 'Must include compact chat header');
    assert.ok(source.includes('AI First Aid Guide'), 'Must include branding title');
    assert.ok(source.includes('Evidence-Grounded RAG'), 'Must display active RAG status pill');
    assert.ok(source.includes('first-aid-new-chat-btn'), 'Must include New Chat button');
  });

  test('Test 2: Centered welcome empty state with 4 compact emergency prompt cards', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('chat-welcome-state'), 'Must define welcome empty state');
    assert.ok(source.includes('How can I help you?'), 'Must feature centered "How can I help you?" welcome heading');
    assert.ok(source.includes('Adult CPR & AED'), 'Must include CPR suggestion card');
    assert.ok(source.includes('Choking (Heimlich)'), 'Must include Choking suggestion card');
    assert.ok(source.includes('Severe Bleeding'), 'Must include Severe Bleeding suggestion card');
    assert.ok(source.includes('Burns & Scalds'), 'Must include Burns suggestion card');
  });

  test('Test 3: Chat message bubbles with user (right) and assistant (left) separation', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('chat-message-row ${msg.role}'), 'Must separate rows by role');
    assert.ok(source.includes('chat-avatar assistant'), 'Must include assistant avatar');
    assert.ok(source.includes('chat-bubble ${msg.role}'), 'Must render role-specific bubble classes');
    assert.ok(source.includes('first-aid-followup-badge'), 'Must render follow-up badge for follow-up turns');
  });

  test('Test 4: Embedded structured guidance inside assistant message', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('embedded-protocol-card'), 'Must render embedded protocol card');
    assert.ok(source.includes('first-aid-call-guidance-box'), 'Must render emergency call guidance');
    assert.ok(source.includes('first-aid-warnings-box'), 'Must render critical safety warnings');
    assert.ok(source.includes('first-aid-steps-section'), 'Must render actionable steps');
    assert.ok(source.includes('first-aid-contraindications-box'), 'Must render what NOT to do contraindications');
    assert.ok(source.includes('first-aid-evidence-drawer'), 'Must render evidence drawer');
    assert.ok(source.includes('first-aid-source-citation-card'), 'Must render source citation card');
  });

  test('Test 5: Sticky chat composer with Enter to send and Shift+Enter for newline', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('chat-composer-footer'), 'Must define sticky composer footer');
    assert.ok(source.includes('composer-textarea'), 'Must use multiline textarea');
    assert.ok(source.includes("e.key === 'Enter' && !e.shiftKey"), 'Must intercept Enter to send');
    assert.ok(source.includes('handleSendMessage()'), 'Must trigger message transmission on Enter');
    assert.ok(source.includes('composer-send-btn'), 'Must include send button');
    assert.ok(source.includes('disabled={loading || !queryText.trim()}'), 'Must disable send when loading or empty');
  });

  test('Test 6: Compact India 112/108 access preserved in header and embedded guidance', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(source.includes('compact-emergency-access'), 'Must provide compact header emergency call buttons');
    assert.ok(source.includes('href="tel:112"'), 'Must have 112 call link');
    assert.ok(source.includes('href="tel:108"'), 'Must have 108 call link');
    assert.ok(source.includes('Call 112'), 'Must label Call 112');
    assert.ok(source.includes('Call 108'), 'Must label Call 108');
  });

  test('Test 7: Zero storage persistence (React memory only)', () => {
    const source = fs.readFileSync(firstAidJsxPath, 'utf8');

    assert.ok(!source.includes('localStorage.setItem'), 'Zero localStorage writes');
    assert.ok(!source.includes('sessionStorage.setItem'), 'Zero sessionStorage writes');
    assert.ok(!source.includes('indexedDB'), 'Zero indexedDB writes');
  });

  test('Test 8: Modern chat styles in index.css', () => {
    assert.ok(fs.existsSync(indexCssPath), 'index.css must exist');
    const css = fs.readFileSync(indexCssPath, 'utf8');

    assert.ok(css.includes('.first-aid-container.chat-mode'), 'Must define .chat-mode styles');
    assert.ok(css.includes('.chat-header'), 'Must define .chat-header styles');
    assert.ok(css.includes('.chat-composer-footer'), 'Must define .chat-composer-footer styles');
    assert.ok(css.includes('.chat-bubble.user'), 'Must define user bubble styles');
    assert.ok(css.includes('.chat-bubble.assistant'), 'Must define assistant bubble styles');
    assert.ok(css.includes('.typing-indicator'), 'Must define typing indicator styles');
  });

});
