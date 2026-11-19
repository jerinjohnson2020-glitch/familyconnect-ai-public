/**
 * FamilyConnect AI - Member Selection Synchronization Helper
 * 
 * Ensures that the active household member selected by the user remains
 * stable and is NEVER unexpectedly reset by WebSocket broadcasts, background
 * data refreshes, polling intervals, or component re-renders.
 */

/**
 * Synchronize and preserve member selection across background data updates.
 *
 * @param {Object} params
 * @param {boolean} params.isOpen - Whether the SOS trigger modal is open.
 * @param {Array} params.members - Full array of household members from API.
 * @param {Object|null} params.preselectedMember - Explicitly preselected member (e.g. from card button).
 * @param {string} params.selectedMemberId - Current member ID selected in state.
 * @param {string} params.reporterName - Current reporter name in state.
 * @param {string} params.manualLabel - Current manual location label in state.
 * @param {Object} params.prevIsOpenRef - React ref tracking whether the modal was open previously.
 * @param {Object} params.prevPreselectedIdRef - React ref tracking the previous preselected member ID.
 * @param {Function} params.setSelectedMemberId - State setter for selectedMemberId.
 * @param {Function} params.setReporterName - State setter for reporterName.
 * @param {Function} [params.setManualLabel] - Optional state setter for manualLabel.
 * @returns {string} The effective selectedMemberId after synchronization.
 */
export function syncMemberSelection({
  isOpen,
  members,
  preselectedMember,
  selectedMemberId,
  reporterName,
  manualLabel,
  prevIsOpenRef,
  prevPreselectedIdRef,
  setSelectedMemberId,
  setReporterName,
  setManualLabel
}) {
  const activeMembers = (members || []).filter((m) => m && m.is_active !== false);

  if (!isOpen) {
    if (prevIsOpenRef) prevIsOpenRef.current = false;
    if (prevPreselectedIdRef) prevPreselectedIdRef.current = null;
    return selectedMemberId || '';
  }

  const justOpened = prevIsOpenRef ? !prevIsOpenRef.current : false;
  if (prevIsOpenRef) prevIsOpenRef.current = true;

  const preselectedChanged = Boolean(
    preselectedMember &&
    prevPreselectedIdRef &&
    preselectedMember.id !== prevPreselectedIdRef.current
  );
  if (prevPreselectedIdRef) prevPreselectedIdRef.current = preselectedMember?.id || null;

  if (justOpened || preselectedChanged) {
    // 1. Fresh open or explicit member preselection from parent
    if (preselectedMember && preselectedMember.is_active !== false) {
      const nextId = preselectedMember.id.toString();
      setSelectedMemberId(nextId);
      setReporterName(preselectedMember.name);
      if (setManualLabel && preselectedMember.address && !manualLabel) {
        setManualLabel(preselectedMember.address);
      }
      return nextId;
    } else if (activeMembers.length > 0) {
      // Requirement 6: Prefer non-demo active member first if available, else first member
      const preferred = activeMembers.find((m) => !m.is_demo) || activeMembers[0];
      const nextId = preferred.id.toString();
      setSelectedMemberId(nextId);
      setReporterName(preferred.name);
      if (setManualLabel && preferred.address && !manualLabel) {
        setManualLabel(preferred.address);
      }
      return nextId;
    } else {
      setSelectedMemberId('');
      setReporterName('');
      return '';
    }
  } else {
    // 2. Modal was already open: background refresh, WebSocket event, or polling update
    // Requirement 5: Preserve the current selection if that member still exists and is active.
    const currentSelected = activeMembers.find((m) => m.id.toString() === (selectedMemberId || '').toString());
    if (currentSelected) {
      // Member still exists and is active -> PRESERVE CURRENT USER SELECTION
      if (!reporterName) {
        setReporterName(currentSelected.name);
      }
      return selectedMemberId;
    } else if (activeMembers.length > 0) {
      // Current selected member was removed or deactivated: explicitly fallback to next valid member
      const fallback = activeMembers.find((m) => !m.is_demo) || activeMembers[0];
      const nextId = fallback.id.toString();
      setSelectedMemberId(nextId);
      setReporterName(fallback.name);
      if (setManualLabel && fallback.address && !manualLabel) {
        setManualLabel(fallback.address);
      }
      return nextId;
    } else {
      setSelectedMemberId('');
      setReporterName('');
      return '';
    }
  }
}
