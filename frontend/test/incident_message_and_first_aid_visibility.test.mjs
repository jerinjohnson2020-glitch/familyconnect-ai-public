import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getIncidentDisplayMessage } from '../src/utils/incidentMessage.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendSrcDir = path.resolve(__dirname, '../src');

describe('Emergency Incident Messages, Test Notification, & First Aid Visibility Tests', () => {

  // -------------------------------------------------------------
  // 1. Emergency Incident Message Visibility & Safe Fallback
  // -------------------------------------------------------------
  describe('1. Incident Message Visibility & Fallback Logic', () => {
    it('returns existing description verbatim when available', () => {
      const incident = {
        id: 53,
        reporter_name: 'Synthetic Patient Alpha',
        incident_type: 'Severe Bleeding',
        description: 'Emergency SOS incident reported for Synthetic Patient Alpha'
      };
      assert.equal(
        getIncidentDisplayMessage(incident),
        'Emergency SOS incident reported for Synthetic Patient Alpha'
      );
    });

    it('returns custom bystander or triage descriptions without modification', () => {
      const incident = {
        id: 3,
        reporter_name: 'Eleanor Vance',
        incident_type: 'Fall with Injury',
        description: 'Slipped in garden, severe hip pain, unable to stand'
      };
      assert.equal(
        getIncidentDisplayMessage(incident),
        'Slipped in garden, severe hip pain, unable to stand'
      );
    });

    it('provides safe fallback for SOS-triggered incidents when description is null or empty', () => {
      const incidentNullDesc = {
        id: 101,
        reporter_name: 'Synthetic Patient Alpha',
        incident_type: 'General SOS / Panic',
        description: null,
        location_source: 'browser_gps'
      };
      assert.equal(
        getIncidentDisplayMessage(incidentNullDesc),
        'Emergency SOS incident reported for Synthetic Patient Alpha'
      );

      const incidentEmptyDesc = {
        id: 102,
        reporter_name: 'Synthetic Patient Beta',
        incident_type: 'Cardiac / Chest Pain',
        description: '   ',
        location_source: 'one_tap_sos'
      };
      assert.equal(
        getIncidentDisplayMessage(incidentEmptyDesc),
        'Emergency SOS incident reported for Synthetic Patient Beta'
      );

      const incidentTimelineSos = {
        id: 103,
        reporter_name: 'Synthetic Patient Gamma',
        incident_type: 'Breathing Difficulty',
        description: '',
        location_source: 'manual_coordinates',
        timeline_events: [{ description: 'Emergency SOS alert registered for Synthetic Patient Gamma' }]
      };
      assert.equal(
        getIncidentDisplayMessage(incidentTimelineSos),
        'Emergency SOS incident reported for Synthetic Patient Gamma'
      );
    });

    it('provides accurate source/type fallback for non-SOS incidents when description is absent', () => {
      const nonSosIncident = {
        id: 104,
        reporter_name: 'Marcus Vance',
        incident_type: 'Fall with Injury',
        description: null,
        location_source: 'manual_coordinates',
        timeline_events: []
      };
      assert.equal(
        getIncidentDisplayMessage(nonSosIncident),
        'Fall with Injury incident reported for Marcus Vance'
      );
    });

    it('EmergencyMonitor source audit: incident message uses accessible theme tokens instead of #cbd5e1', () => {
      const source = fs.readFileSync(path.join(frontendSrcDir, 'components/EmergencyMonitor.jsx'), 'utf8');
      assert.ok(!source.includes("fontSize: '0.825rem', color: '#cbd5e1'"), 'Incident message container must NOT use hardcoded #cbd5e1');
      assert.ok(source.includes('getIncidentDisplayMessage(incident)'), 'EmergencyMonitor must invoke getIncidentDisplayMessage');
      assert.ok(source.includes("color: 'var(--text-secondary)'"), 'Must use theme-adaptive var(--text-secondary) for message contrast');
    });
  });

  // -------------------------------------------------------------
  // 2. Test Notification Confirmation Visibility & Handling
  // -------------------------------------------------------------
  describe('2. Test Notification Confirmation Visibility & Handling', () => {
    it('ResponderAndAlertManager source audit: confirmation checkbox and label are accessible and visible', () => {
      const source = fs.readFileSync(path.join(frontendSrcDir, 'components/ResponderAndAlertManager.jsx'), 'utf8');

      // Confirmation text must be present
      assert.ok(
        source.includes('I explicitly confirm sending a test notification to the destination entered above.'),
        'Must contain exact confirmation sentence'
      );

      // Label & input accessibility association
      assert.ok(source.includes('htmlFor="confirm-test-send"'), 'Confirmation label must have htmlFor="confirm-test-send"');
      assert.ok(source.includes('id="confirm-test-send"'), 'Confirmation input must have id="confirm-test-send"');

      // High contrast color (no #cbd5e1)
      assert.ok(!source.includes("color: '#cbd5e1', cursor: 'pointer'"), 'Must NOT use faint #cbd5e1 on white background');
      assert.ok(source.includes("color: 'var(--text-secondary)'"), 'Must use var(--text-secondary) for label contrast');

      // State handling & form validation
      assert.ok(source.includes('disabled={sendingTest || !confirmTestSend}'), 'Submit button must require confirmTestSend');
      assert.ok(source.includes('if (!confirmTestSend)'), 'Form submission must enforce confirmTestSend check');
    });
  });

  // -------------------------------------------------------------
  // 3. AI First Aid Guide — Emergency Call Instruction "Call 108"
  // -------------------------------------------------------------
  describe('3. AI First Aid Guide — Emergency Call Guidance (112 & 108)', () => {
    it('FirstAidAssistant source audit: Call 108 is explicitly rendered under Evidence-Grounded RAG protocol results', () => {
      const source = fs.readFileSync(path.join(frontendSrcDir, 'components/FirstAidAssistant.jsx'), 'utf8');

      // Evidence-Grounded RAG badge exists
      assert.ok(source.includes('Evidence-Grounded RAG'), 'Must have Evidence-Grounded RAG section');

      // Result article contains explicit Call 108 button and text
      assert.ok(source.includes('Call 108 (Ambulance Service)'), 'Protocol result must explicitly display "Call 108 (Ambulance Service)"');
      assert.ok(source.includes('href="tel:108"'), 'Must have clickable href="tel:108" link');

      // Call 112 is also prominently displayed
      assert.ok(source.includes('Call 112 (National Emergency Number)'), 'Protocol result must display "Call 112 (National Emergency Number)"');
      assert.ok(source.includes('href="tel:112"'), 'Must have clickable href="tel:112" link');

      // Reliable explicit UI rule: rendered inside first-aid-call-guidance-box without conditional hiding
      assert.ok(
        source.includes('Emergency Safety Directive — When to Call Emergency Services'),
        'Must render explicit Emergency Safety Directive header'
      );

      // Contrast: no invisible #fecaca on pink/yellow background
      assert.ok(!source.includes("color: '#fecaca', lineHeight: 1.45"), 'Must NOT use faint #fecaca text in call guidance box');
      assert.ok(source.includes("color: 'var(--text-primary)'"), 'Must use var(--text-primary) for high contrast in Light & Dark modes');

      // Top banner also has accessible Call 108 styling
      assert.ok(source.includes("background: '#b45309'"), 'Amber 108 button must use accessible #b45309');
    });

    it('Fallback state also includes both Call 112 and Call 108 actions', () => {
      const source = fs.readFileSync(path.join(frontendSrcDir, 'components/FirstAidAssistant.jsx'), 'utf8');
      const fallbackSection = source.slice(source.indexOf('first-aid-fallback-card'));
      assert.ok(fallbackSection.includes('href="tel:112"'), 'Fallback card must have Call 112');
      assert.ok(fallbackSection.includes('href="tel:108"'), 'Fallback card must have Call 108');
    });
  });
});
