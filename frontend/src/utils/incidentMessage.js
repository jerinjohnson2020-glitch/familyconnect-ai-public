/**
 * FamilyConnect AI - Emergency Incident Message & Fallback Utilities
 *
 * Resolves appropriate incident messages for display across the Emergency Monitor,
 * notifications, and dispatch cards.
 *
 * Rules:
 * - If incident has a non-empty description, returns it verbatim.
 * - If description is missing/empty and incident was triggered via SOS, returns:
 *   "Emergency SOS incident reported for [member name]"
 * - If description is missing/empty and incident was NOT triggered via SOS, returns:
 *   "[incident_type] incident reported for [member name]"
 * - Does not overwrite existing incident records or database fields.
 */

export function getIncidentDisplayMessage(incident) {
  if (!incident) return '';
  const desc = (incident.description || '').trim();
  if (desc) return desc;

  const person = (incident.reporter_name || 'Family Member').trim();
  const type = (incident.incident_type || 'Emergency').trim();

  // Determine whether this incident was initiated as an SOS workflow
  const isSos =
    type.toUpperCase().includes('SOS') ||
    (incident.location_source && incident.location_source.toLowerCase().includes('sos')) ||
    (incident.timeline_events && incident.timeline_events.some((e) => (e.description || '').toUpperCase().includes('SOS')));

  if (isSos) {
    return `Emergency SOS incident reported for ${person}`;
  }
  return `${type} incident reported for ${person}`;
}
