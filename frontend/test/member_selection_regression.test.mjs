import test from 'node:test';
import assert from 'node:assert/strict';
import { syncMemberSelection } from '../src/utils/memberSelection.js';

// Sample Household 1 Members roster matching familyconnect.db
const HOUSEHOLD_1_MEMBERS = [
  { id: 1, name: 'Eleanor Vance (Grandmother)', relationship: 'Grandmother', is_demo: true, is_active: true, address: 'Kochi Residence' },
  { id: 2, name: 'Marcus Jenkins', relationship: 'Family Member', is_demo: true, is_active: true, address: 'Marine Drive Flat' },
  { id: 3, name: 'Sarah Vance', relationship: 'Mother', is_demo: true, is_active: true, address: 'Kaloor' },
  { id: 4, name: 'Leo Vance', relationship: 'Son', is_demo: true, is_active: true, address: 'Kaloor' },
  { id: 5, name: 'Test Cousin Sam', relationship: 'Cousin', is_demo: false, is_active: true, address: 'MG Road' },
  { id: 6, name: 'Rita Manoj', relationship: 'Aunt', is_demo: false, is_active: true, address: 'Vyttila' }
];

test('Regression Test 1: User selection of Eleanor Vance is preserved across WebSocket updates and data refreshes', () => {
  let selectedMemberId = '';
  let reporterName = '';
  let manualLabel = '';
  const prevIsOpenRef = { current: false };
  const prevPreselectedIdRef = { current: null };

  const setSelectedMemberId = (id) => { selectedMemberId = id; };
  const setReporterName = (name) => { reporterName = name; };
  const setManualLabel = (label) => { manualLabel = label; };

  // Step 1: User opens the SOS Trigger Modal from dashboard
  syncMemberSelection({
    isOpen: true,
    members: HOUSEHOLD_1_MEMBERS,
    preselectedMember: null,
    selectedMemberId,
    reporterName,
    manualLabel,
    prevIsOpenRef,
    prevPreselectedIdRef,
    setSelectedMemberId,
    setReporterName,
    setManualLabel
  });

  // Initial default: non-demo member preferred if available
  assert.equal(selectedMemberId, '5', 'Initial default selects non-demo member Test Cousin Sam');

  // Step 2: User explicitly changes dropdown selection to Eleanor Vance (ID 1)
  selectedMemberId = '1';
  reporterName = 'Eleanor Vance (Grandmother)';
  manualLabel = 'Kochi Residence';

  // Step 3: 3-4 seconds later, a live WebSocket event arrives (e.g. INCIDENT_STATUS_UPDATED)
  // which causes App.jsx loadData() to refresh the members array with a new reference
  const refreshedMembersAfterWebSocket = JSON.parse(JSON.stringify(HOUSEHOLD_1_MEMBERS));

  syncMemberSelection({
    isOpen: true,
    members: refreshedMembersAfterWebSocket,
    preselectedMember: null,
    selectedMemberId,
    reporterName,
    manualLabel,
    prevIsOpenRef,
    prevPreselectedIdRef,
    setSelectedMemberId,
    setReporterName,
    setManualLabel
  });

  // Verify that the user's explicit selection was NOT clobbered or reset to "Test Cousin Sam"
  assert.equal(
    selectedMemberId,
    '1',
    'CRITICAL: User selection must remain Eleanor Vance (ID 1) after WebSocket event and data refresh'
  );
  assert.equal(reporterName, 'Eleanor Vance (Grandmother)');
  assert.notEqual(
    selectedMemberId,
    '5',
    'BUG REGRESSION: Selection must NOT automatically revert to Test Cousin Sam (ID 5)'
  );
});

test('Regression Test 2: User selection is preserved across repeated 10-second polling refreshes', () => {
  let selectedMemberId = '2'; // User picked Marcus Jenkins (ID 2)
  let reporterName = 'Marcus Jenkins';
  let manualLabel = 'Marine Drive Flat';
  const prevIsOpenRef = { current: true };
  const prevPreselectedIdRef = { current: null };

  const setSelectedMemberId = (id) => { selectedMemberId = id; };
  const setReporterName = (name) => { reporterName = name; };
  const setManualLabel = (label) => { manualLabel = label; };

  // Simulate 5 consecutive background polling data refreshes
  for (let poll = 1; poll <= 5; poll++) {
    const polledMembers = HOUSEHOLD_1_MEMBERS.map(m => ({ ...m }));
    syncMemberSelection({
      isOpen: true,
      members: polledMembers,
      preselectedMember: null,
      selectedMemberId,
      reporterName,
      manualLabel,
      prevIsOpenRef,
      prevPreselectedIdRef,
      setSelectedMemberId,
      setReporterName,
      setManualLabel
    });

    assert.equal(
      selectedMemberId,
      '2',
      `Poll #${poll}: Marcus Jenkins (ID 2) must remain selected`
    );
  }
});

test('Regression Test 3: Explicit fallback when selected member is deactivated or removed', () => {
  let selectedMemberId = '1'; // User currently has Eleanor Vance (ID 1) selected
  let reporterName = 'Eleanor Vance (Grandmother)';
  let manualLabel = 'Kochi Residence';
  const prevIsOpenRef = { current: true };
  const prevPreselectedIdRef = { current: null };

  const setSelectedMemberId = (id) => { selectedMemberId = id; };
  const setReporterName = (name) => { reporterName = name; };
  const setManualLabel = (label) => { manualLabel = label; };

  // Simulate Eleanor Vance being deactivated by administrator in another session
  const membersWithEleanorDeactivated = HOUSEHOLD_1_MEMBERS.map(m =>
    m.id === 1 ? { ...m, is_active: false } : { ...m }
  );

  syncMemberSelection({
    isOpen: true,
    members: membersWithEleanorDeactivated,
    preselectedMember: null,
    selectedMemberId,
    reporterName,
    manualLabel,
    prevIsOpenRef,
    prevPreselectedIdRef,
    setSelectedMemberId,
    setReporterName,
    setManualLabel
  });

  // When selected member is deactivated, explicitly fall back to next active member
  assert.equal(
    selectedMemberId,
    '5',
    'Must fall back to active non-demo member Test Cousin Sam when Eleanor is deactivated'
  );
  assert.equal(reporterName, 'Test Cousin Sam');
});

test('Regression Test 4: Preselected member from member card SOS button is honored and preserved', () => {
  let selectedMemberId = '';
  let reporterName = '';
  let manualLabel = '';
  const prevIsOpenRef = { current: false };
  const prevPreselectedIdRef = { current: null };

  const setSelectedMemberId = (id) => { selectedMemberId = id; };
  const setReporterName = (name) => { reporterName = name; };
  const setManualLabel = (label) => { manualLabel = label; };

  // User clicked "Trigger SOS for Marcus" on Marcus's card (ID 2)
  const marcusMember = HOUSEHOLD_1_MEMBERS.find(m => m.id === 2);

  syncMemberSelection({
    isOpen: true,
    members: HOUSEHOLD_1_MEMBERS,
    preselectedMember: marcusMember,
    selectedMemberId,
    reporterName,
    manualLabel,
    prevIsOpenRef,
    prevPreselectedIdRef,
    setSelectedMemberId,
    setReporterName,
    setManualLabel
  });

  assert.equal(selectedMemberId, '2', 'Preselected member Marcus Jenkins must be selected');

  // Background refresh occurs
  const refreshed = JSON.parse(JSON.stringify(HOUSEHOLD_1_MEMBERS));
  syncMemberSelection({
    isOpen: true,
    members: refreshed,
    preselectedMember: marcusMember,
    selectedMemberId,
    reporterName,
    manualLabel,
    prevIsOpenRef,
    prevPreselectedIdRef,
    setSelectedMemberId,
    setReporterName,
    setManualLabel
  });

  assert.equal(selectedMemberId, '2', 'Marcus Jenkins must remain selected after refresh');
});

test('Regression Test 5: Fallback to demo member when NO non-demo members exist in household', () => {
  let selectedMemberId = '';
  let reporterName = '';
  const prevIsOpenRef = { current: false };
  const prevPreselectedIdRef = { current: null };

  const setSelectedMemberId = (id) => { selectedMemberId = id; };
  const setReporterName = (name) => { reporterName = name; };

  // Household with only demo members
  const onlyDemoMembers = [
    { id: 101, name: 'Demo Grandparent', is_demo: true, is_active: true },
    { id: 102, name: 'Demo Child', is_demo: true, is_active: true }
  ];

  syncMemberSelection({
    isOpen: true,
    members: onlyDemoMembers,
    preselectedMember: null,
    selectedMemberId,
    reporterName,
    manualLabel: '',
    prevIsOpenRef,
    prevPreselectedIdRef,
    setSelectedMemberId,
    setReporterName,
    setManualLabel: () => {}
  });

  assert.equal(selectedMemberId, '101', 'Falls back to first active member when all members are demo');
});
