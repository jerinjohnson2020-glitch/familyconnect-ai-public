/**
 * Dynamic API Base URL resolution:
 * Supports VITE_API_BASE_URL env var, defaulting to relative '/api'
 * for dev proxy, production monolith serving, and mobile LAN access.
 */
const RAW_API_BASE = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL)
  ? String(import.meta.env.VITE_API_BASE_URL).trim().replace(/\/+$/, '')
  : '';

export const API_BASE = RAW_API_BASE ? `${RAW_API_BASE}/api` : '/api';

const TOKEN_KEY = 'familyconnect_token';
let authToken = typeof window !== 'undefined' ? sessionStorage.getItem(TOKEN_KEY) : null;
let unauthorizedCallback = null;

export function setAuthToken(token) {
  authToken = token;
  if (typeof window !== 'undefined') {
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
    }
  }
}

export function getAuthToken() {
  if (!authToken && typeof window !== 'undefined') {
    authToken = sessionStorage.getItem(TOKEN_KEY);
  }
  return authToken;
}

export function clearAuthToken() {
  authToken = null;
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function onUnauthorized(callback) {
  unauthorizedCallback = callback;
}

/**
 * Centralized authenticated fetch wrapper.
 * Automatically attaches Authorization header if token is present.
 * Intercepts HTTP 401 to clear session and trigger auth callback.
 * Intercepts HTTP 403 to surface clear role permission feedback.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    clearAuthToken();
    if (unauthorizedCallback) {
      unauthorizedCallback();
    }
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Session expired or unauthenticated. Please sign in.');
  }

  if (res.status === 403) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Access forbidden: Your role does not have permission for this resource.');
  }

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Request failed with status ${res.status}`);
  }

  const text = await res.text();
  return text ? JSON.parse(text) : {};
}

// --- Authentication Endpoints ---

export async function login(username, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Invalid username or password');
  }

  const data = await res.json();
  if (data.access_token) {
    setAuthToken(data.access_token);
  }
  return data;
}

export async function register(payload) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    let msg = 'Registration failed';
    if (typeof errData.detail === 'string') {
      msg = errData.detail;
    } else if (Array.isArray(errData.detail)) {
      msg = errData.detail.map(d => d.msg || JSON.stringify(d)).join(', ');
    } else if (errData.message) {
      msg = errData.message;
    }
    throw new Error(msg);
  }

  const data = await res.json();
  if (data.access_token) {
    setAuthToken(data.access_token);
  }
  return data;
}

export async function getMe() {
  return request('/auth/me');
}

export async function logout() {
  try {
    await request('/auth/logout', { method: 'POST' });
  } catch (err) {
    // Proceed with client session cleanup regardless of network status
  } finally {
    clearAuthToken();
  }
}

// --- Public Health & Platform Info ---

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

// --- Family Members API (Phase 6) ---

export async function getMembers(includeInactive = false, excludeDemo = false) {
  const params = new URLSearchParams();
  if (includeInactive) params.set('include_inactive', 'true');
  if (excludeDemo) params.set('exclude_demo', 'true');
  const qs = params.toString();
  return request(qs ? `/members?${qs}` : '/members');
}

export async function createMember(member) {
  return request('/members', {
    method: 'POST',
    body: JSON.stringify(member)
  });
}

export async function updateMember(memberId, member) {
  return request(`/members/${memberId}`, {
    method: 'PUT',
    body: JSON.stringify(member)
  });
}

export async function deleteOrDeactivateMember(memberId, hardDelete = false) {
  const qs = hardDelete ? '?hard_delete=true' : '';
  return request(`/members/${memberId}${qs}`, {
    method: 'DELETE'
  });
}

export async function manageDemoRecords(action = 'deactivate') {
  return request(`/members/admin/demo-records?action=${encodeURIComponent(action)}`, {
    method: 'POST'
  });
}

// --- Trusted Contacts API (Phase 4A & Phase 6) ---

export async function getTrustedContacts(memberId) {
  return request(`/members/${memberId}/trusted-contacts`);
}

export async function createTrustedContact(memberId, contact) {
  return request(`/members/${memberId}/trusted-contacts`, {
    method: 'POST',
    body: JSON.stringify(contact)
  });
}

export async function updateTrustedContact(memberId, contactId, contact) {
  return request(`/members/${memberId}/trusted-contacts/${contactId}`, {
    method: 'PUT',
    body: JSON.stringify(contact)
  });
}

export async function deleteTrustedContact(memberId, contactId) {
  return request(`/members/${memberId}/trusted-contacts/${contactId}`, {
    method: 'DELETE'
  });
}

// --- Responders API (Phase 6) ---

export async function getResponders(availableOnly = false, includeInactive = false, excludeDemo = true) {
  const params = new URLSearchParams();
  if (availableOnly) params.set('available_only', 'true');
  if (includeInactive) params.set('include_inactive', 'true');
  if (excludeDemo) params.set('exclude_demo', 'true');
  const qs = params.toString();
  return request(qs ? `/responders?${qs}` : '/responders');
}

export async function createResponder(responder) {
  return request('/responders', {
    method: 'POST',
    body: JSON.stringify(responder)
  });
}

export async function updateResponder(responderId, responder) {
  return request(`/responders/${responderId}`, {
    method: 'PUT',
    body: JSON.stringify(responder)
  });
}

export async function updateResponderLocation(responderId, locationData) {
  return request(`/responders/${responderId}/location`, {
    method: 'PATCH',
    body: JSON.stringify(locationData)
  });
}

export async function deleteOrDeactivateResponder(responderId, hardDelete = false) {
  const qs = hardDelete ? '?hard_delete=true' : '';
  return request(`/responders/${responderId}${qs}`, {
    method: 'DELETE'
  });
}

export async function getMyAssignments() {
  return request('/responders/me/assignments');
}

export async function updateAssignmentStatus(assignmentId, status) {
  return request(`/responders/me/assignments/${assignmentId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status })
  });
}

// --- Emergency Incidents & SOS API ---

export async function getEmergencies(status = null) {
  const endpoint = status ? `/emergencies?status=${status}` : '/emergencies';
  return request(endpoint);
}

export async function triggerSos(sosData) {
  return request('/emergencies/sos', {
    method: 'POST',
    body: JSON.stringify(sosData)
  });
}

export async function updateEmergencyStatus(incidentId, status, resolutionNotes = null) {
  const payload = { status };
  if (resolutionNotes) {
    payload.resolution_notes = resolutionNotes;
  }
  return request(`/emergencies/${incidentId}/status`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}

export async function getIncidentTimeline(incidentId) {
  return request(`/emergencies/${incidentId}/timeline`);
}

export async function getIncidentAlerts(incidentId) {
  return request(`/emergencies/${incidentId}/alerts`);
}

export async function acknowledgeAlert(incidentId, alertId) {
  return request(`/emergencies/${incidentId}/alerts/${alertId}/acknowledge`, {
    method: 'POST'
  });
}

export async function retryIncidentAlert(incidentId, alertId) {
  return request(`/emergencies/${incidentId}/alerts/${alertId}/retry`, {
    method: 'POST'
  });
}

export async function updateIncidentLocation(incidentId, locationData) {
  return request(`/emergencies/${incidentId}/location`, {
    method: 'PATCH',
    body: JSON.stringify(locationData)
  });
}

export async function getNotificationConfig() {
  return request('/emergencies/config/notifications');
}

export async function sendTestNotification(testPayload) {
  return request('/emergencies/config/notifications/test', {
    method: 'POST',
    body: JSON.stringify(testPayload)
  });
}

export async function getAiEvaluationBenchmark() {
  return request('/emergencies/ai-evaluation');
}

export async function testAiTriage(params) {
  const query = new URLSearchParams(params).toString();
  return request(`/emergencies/preview-ai-triage?${query}`, {
    method: 'POST'
  });
}

/**
 * Resolves the authenticated WebSocket URL dynamically.
 * Supports VITE_WS_BASE_URL, derivation from RAW_API_BASE, or
 * browser window.location protocol and host (works for localhost, LAN IPs, and HTTPS).
 */
export function getWebSocketUrl(token) {
  if (typeof window === 'undefined') return '';
  const rawWsUrl = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_WS_BASE_URL)
    ? String(import.meta.env.VITE_WS_BASE_URL).trim().replace(/\/+$/, '')
    : '';

  if (rawWsUrl) {
    const sep = rawWsUrl.includes('?') ? '&' : '?';
    return `${rawWsUrl}/api/ws/incidents${sep}token=${encodeURIComponent(token)}`;
  }

  if (RAW_API_BASE.startsWith('http://') || RAW_API_BASE.startsWith('https://')) {
    const wsProto = RAW_API_BASE.startsWith('https://') ? 'wss:' : 'ws:';
    const host = RAW_API_BASE.replace(/^https?:\/\//, '');
    return `${wsProto}//${host}/api/ws/incidents?token=${encodeURIComponent(token)}`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/ws/incidents?token=${encodeURIComponent(token)}`;
}

/**
 * Phase 5C: Authenticated Real-Time Incident Coordination WebSocket Client.
 * Automatically connects with the active authentication bearer token and dispatches live events.
 */
export function connectIncidentWebSocket(onEvent, onConnectionStateChange) {
  if (typeof window === 'undefined') return () => {};
  const token = getAuthToken();
  if (!token) return () => {};

  const wsUrl = getWebSocketUrl(token);

  let ws = null;
  let closedByClient = false;
  let reconnectTimer = null;
  let pingTimer = null;

  const connect = () => {
    if (closedByClient) return;
    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (onConnectionStateChange) onConnectionStateChange('connected');
        pingTimer = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event_type && data.event_type !== 'PONG' && onEvent) {
            onEvent(data);
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        if (pingTimer) clearInterval(pingTimer);
        if (onConnectionStateChange) onConnectionStateChange('disconnected');
        if (!closedByClient) {
          reconnectTimer = setTimeout(connect, 4000);
        }
      };

      ws.onerror = () => {
        if (onConnectionStateChange) onConnectionStateChange('error');
      };
    } catch {
      if (onConnectionStateChange) onConnectionStateChange('error');
    }
  };

  connect();

  return () => {
    closedByClient = true;
    if (pingTimer) clearInterval(pingTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.close();
    }
  };
}

// --- First-Responder Public Registration (Phase 3B) ---

export async function registerResponder(payload) {
  const res = await fetch(`${API_BASE}/auth/register-responder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    let msg = 'Responder application failed';
    if (typeof errData.detail === 'string') {
      msg = errData.detail;
    } else if (Array.isArray(errData.detail)) {
      msg = errData.detail.map(d => d.msg || JSON.stringify(d)).join(', ');
    }
    throw new Error(msg);
  }

  return res.json();
}

// --- Household Invitations API (Phase 3B) ---

export async function createInvitation(payload) {
  return request('/household/invitations', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function getHouseholdInvitations() {
  return request('/household/invitations');
}

export async function revokeInvitation(invitationId) {
  return request(`/household/invitations/${invitationId}`, {
    method: 'DELETE'
  });
}

export async function validateInvitationToken(token) {
  const res = await fetch(`${API_BASE}/household/invitations/validate?token=${encodeURIComponent(token)}`);
  return res.json();
}

export async function acceptInvitation(payload) {
  const res = await fetch(`${API_BASE}/household/invitations/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    let msg = 'Failed to accept invitation';
    if (typeof errData.detail === 'string') {
      msg = errData.detail;
    } else if (Array.isArray(errData.detail)) {
      msg = errData.detail.map(d => d.msg || JSON.stringify(d)).join(', ');
    }
    throw new Error(msg);
  }

  const data = await res.json();
  if (data.access_token) {
    setAuthToken(data.access_token);
  }
  return data;
}

// --- Platform Reviewer / Responder Onboarding API (Phase 3B) ---

export async function getResponderApplications(status = null) {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return request(`/admin/responders/applications${query}`);
}

export async function reviewResponderApplication(appId, payload) {
  return request(`/admin/responders/applications/${appId}/review`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

// --- First-Aid Evidence Assistant API (Phase 5E / Day 3 & Conversational Update) ---

export async function queryFirstAid(queryText, options = {}) {
  let topK = 2;
  let conversationHistory = null;
  let activeProtocolId = null;

  if (typeof options === 'number') {
    topK = options;
  } else if (options && typeof options === 'object') {
    topK = options.topK || options.top_k || 2;
    conversationHistory = options.conversationHistory || options.conversation_history || null;
    activeProtocolId = options.activeProtocolId || options.active_protocol_id || null;
  }

  // Client-side validation: max 6 history messages, max 4000 characters
  let payloadHistory = null;
  if (Array.isArray(conversationHistory) && conversationHistory.length > 0) {
    const trimmed = conversationHistory.slice(-6).map((m) => ({
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: String(m.content || '').slice(0, 1000)
    }));

    let totalLen = trimmed.reduce((acc, m) => acc + m.content.length, 0);
    while (totalLen > 4000 && trimmed.length > 1) {
      trimmed.shift();
      totalLen = trimmed.reduce((acc, m) => acc + m.content.length, 0);
    }
    payloadHistory = trimmed;
  }

  const payload = {
    query: String(queryText || '').trim(),
    top_k: topK
  };

  if (payloadHistory && payloadHistory.length > 0) {
    payload.conversation_history = payloadHistory;
  }
  if (activeProtocolId) {
    payload.active_protocol_id = String(activeProtocolId).trim();
  }

  return request('/first-aid/query', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function getFirstAidTopics() {
  return request('/first-aid/topics');
}

export async function getFirstAidProtocol(protocolId) {
  return request(`/first-aid/protocols/${encodeURIComponent(protocolId)}`);
}

