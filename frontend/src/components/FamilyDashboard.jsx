import React, { useState, useEffect } from 'react';
import {
  Phone,
  Mail,
  MapPin,
  HeartPulse,
  ShieldAlert,
  Plus,
  Users,
  UserPlus,
  Trash2,
  Edit2,
  Power,
  Database,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  Clock,
  X,
  Eye,
  EyeOff,
  ShieldCheck
} from 'lucide-react';
import {
  createMember,
  updateMember,
  deleteOrDeactivateMember,
  manageDemoRecords,
  createTrustedContact,
  updateTrustedContact,
  deleteTrustedContact,
  createInvitation,
  getHouseholdInvitations,
  revokeInvitation
} from '../services/api';
import { validatePhoneNumber, DEFAULT_PHONE_PLACEHOLDER } from '../utils/phone';
import {
  isDemoEntity,
  maskPhoneNumber,
  maskEmail,
  maskAddress
} from '../utils/privacyMask';

const EMPTY_MEMBER_FORM = {
  name: '',
  relationship: 'Family Member',
  age: '',
  phone: '',
  email: '',
  address: '',
  blood_group: 'O+',
  medical_notes: '',
  emergency_contact_name: '',
  emergency_contact_phone: '',
  is_active: true
};

export default function FamilyDashboard({
  members,
  onRefresh,
  onTriggerSosForMember,
  loading,
  user = null
}) {
  const [showMemberModal, setShowMemberModal] = useState(false);
  const [editingMemberId, setEditingMemberId] = useState(null);
  const [formData, setFormData] = useState(EMPTY_MEMBER_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [dashboardNotice, setDashboardNotice] = useState(null);

  // Filter & Demo Control State
  const [showInactive, setShowInactive] = useState(true);
  const [hideDemoRecords, setHideDemoRecords] = useState(false);
  const [demoActionLoading, setDemoActionLoading] = useState(false);
  const [demoPrivacyMode, setDemoPrivacyMode] = useState(true);

  // Trusted Contacts Management State
  const [managingContactsMember, setManagingContactsMember] = useState(null);
  const [contactForm, setContactForm] = useState({
    name: '',
    phone: '',
    email: '',
    relationship: 'Family Member',
    priority: 1,
    notification_preferences: 'EMAIL',
    is_active: true
  });
  const [editingContactId, setEditingContactId] = useState(null);
  const [contactActionLoading, setContactActionLoading] = useState(false);
  const [contactActionError, setContactActionError] = useState('');
  const [contactActionSuccess, setContactActionSuccess] = useState('');

  // Household Invitations State (Phase 3B)
  const [invitations, setInvitations] = useState([]);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviteMemberId, setInviteMemberId] = useState('');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [lastCreatedInvite, setLastCreatedInvite] = useState(null);
  const [copiedLink, setCopiedLink] = useState(false);

  const loadInvitations = async () => {
    if (!user || user.role !== 'admin') return;
    try {
      const data = await getHouseholdInvitations();
      setInvitations(data || []);
    } catch (err) {
      console.warn('Failed to load household invitations:', err);
    }
  };

  useEffect(() => {
    loadInvitations();
  }, [user]);

  const handleOpenInviteModal = () => {
    setInviteEmail('');
    setInviteRole('member');
    setInviteMemberId('');
    setInviteError('');
    setLastCreatedInvite(null);
    setCopiedLink(false);
    setShowInviteModal(true);
  };

  const handleSendInvitation = async (e) => {
    e.preventDefault();
    if (!inviteEmail.trim()) {
      setInviteError('Please provide a valid recipient email address.');
      return;
    }

    try {
      setInviteLoading(true);
      setInviteError('');
      const res = await createInvitation({
        email: inviteEmail.trim(),
        role: inviteRole,
        member_id: inviteMemberId ? Number(inviteMemberId) : undefined
      });
      setLastCreatedInvite(res);
      await loadInvitations();
    } catch (err) {
      setInviteError(err.message || 'Failed to dispatch household invitation.');
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRevokeInvitation = async (id) => {
    if (!window.confirm('Are you sure you want to revoke this pending invitation?')) return;
    try {
      await revokeInvitation(id);
      setDashboardNotice({ type: 'success', text: 'Household invitation revoked successfully.' });
      await loadInvitations();
    } catch (err) {
      setDashboardNotice({ type: 'error', text: err.message || 'Failed to revoke invitation.' });
    }
  };

  const handleCopyInviteLink = (link) => {
    if (!link) return;
    navigator.clipboard.writeText(link);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 3000);
  };

  const canManageMember = (memberId) => {
    if (!user) return false;
    if (user.role === 'admin') return true;
    if (user.role === 'member' && user.member_id === memberId) return true;
    return false;
  };

  const handleOpenAddMember = () => {
    setEditingMemberId(null);
    setFormData(EMPTY_MEMBER_FORM);
    setError('');
    setShowMemberModal(true);
  };

  const handleOpenEditMember = (member) => {
    setEditingMemberId(member.id);
    setFormData({
      name: member.name || '',
      relationship: member.relationship || 'Family Member',
      age: member.age != null ? String(member.age) : '',
      phone: member.phone || '',
      email: member.email || '',
      address: member.address || '',
      blood_group: member.blood_group || '',
      medical_notes: member.medical_notes || '',
      emergency_contact_name: member.emergency_contact_name || '',
      emergency_contact_phone: member.emergency_contact_phone || '',
      is_active: member.is_active !== false
    });
    setError('');
    setShowMemberModal(true);
  };

  const handleToggleMemberActive = async (member) => {
    setDashboardNotice(null);
    try {
      const nextActive = member.is_active === false;
      await updateMember(member.id, { is_active: nextActive });
      setDashboardNotice({
        type: 'success',
        text: `${member.name} has been marked ${nextActive ? 'Active' : 'Inactive'}.`
      });
      await onRefresh();
    } catch (err) {
      setDashboardNotice({
        type: 'error',
        text: err.message || 'Failed to update member active status.'
      });
    }
  };

  const handleDeleteOrDeactivateMember = async (member) => {
    const confirmMsg = `Remove or deactivate ${member.name}? Records with historical SOS incidents are safely deactivated to preserve audit history; unreferenced records are permanently removed.`;
    if (!window.confirm(confirmMsg)) return;
    setDashboardNotice(null);
    try {
      const res = await deleteOrDeactivateMember(member.id, true);
      setDashboardNotice({
        type: 'success',
        text: res.detail || `${member.name} updated.`
      });
      await onRefresh();
    } catch (err) {
      setDashboardNotice({
        type: 'error',
        text: err.message || 'Failed to remove/deactivate member.'
      });
    }
  };

  const handleDemoControl = async (action) => {
    setDemoActionLoading(true);
    setDashboardNotice(null);
    try {
      const res = await manageDemoRecords(action);
      setDashboardNotice({
        type: 'success',
        text: `${res.detail} (Members: ${res.members_updated}, Contacts: ${res.contacts_updated}, Responders: ${res.responders_updated})`
      });
      await onRefresh();
    } catch (err) {
      setDashboardNotice({
        type: 'error',
        text: err.message || 'Failed to update demo records.'
      });
    } finally {
      setDemoActionLoading(false);
    }
  };

  const handleOpenContactManager = (member) => {
    setManagingContactsMember(member);
    setEditingContactId(null);
    setContactForm({
      name: '',
      phone: '',
      email: '',
      relationship: 'Family Member',
      priority: (member.trusted_contacts?.length || 0) + 1,
      notification_preferences: 'EMAIL',
      is_active: true
    });
    setContactActionError('');
    setContactActionSuccess('');
  };

  const handleStartEditContact = (c) => {
    setEditingContactId(c.id);
    setContactForm({
      name: c.name,
      phone: c.phone,
      email: c.email || '',
      relationship: c.relationship,
      priority: c.priority,
      notification_preferences: c.notification_preferences || 'EMAIL',
      is_active: c.is_active
    });
    setContactActionError('');
    setContactActionSuccess('');
  };

  const handleCancelEditContact = () => {
    setEditingContactId(null);
    setContactForm({
      name: '',
      phone: '',
      email: '',
      relationship: 'Family Member',
      priority: (managingContactsMember?.trusted_contacts?.length || 0) + 1,
      notification_preferences: 'EMAIL',
      is_active: true
    });
  };

  const handleSaveContact = async (e) => {
    e.preventDefault();
    if (!managingContactsMember) return;
    if (!contactForm.name.trim() || !contactForm.phone.trim()) {
      setContactActionError('Name and phone number are required.');
      return;
    }

    const phoneCheck = validatePhoneNumber(contactForm.phone, { required: true });
    if (!phoneCheck.valid) {
      setContactActionError(phoneCheck.error);
      return;
    }

    if (
      contactForm.notification_preferences.includes('EMAIL') &&
      !contactForm.email.trim()
    ) {
      setContactActionError('An email address is required when EMAIL notification channel is selected.');
      return;
    }

    setContactActionLoading(true);
    setContactActionError('');
    setContactActionSuccess('');

    try {
      const payload = {
        ...contactForm,
        phone: phoneCheck.normalized,
        email: contactForm.email.trim() || null
      };
      if (editingContactId) {
        await updateTrustedContact(managingContactsMember.id, editingContactId, payload);
        setContactActionSuccess('Contact updated successfully.');
      } else {
        await createTrustedContact(managingContactsMember.id, payload);
        setContactActionSuccess('Trusted contact added successfully.');
      }
      handleCancelEditContact();
      await onRefresh();
    } catch (err) {
      setContactActionError(err.message || 'Operation failed');
    } finally {
      setContactActionLoading(false);
    }
  };

  const handleDeleteContact = async (contactId) => {
    if (!window.confirm('Are you sure you want to remove this trusted contact?')) return;
    setContactActionLoading(true);
    setContactActionError('');
    try {
      await deleteTrustedContact(managingContactsMember.id, contactId);
      setContactActionSuccess('Contact removed successfully.');
      await onRefresh();
    } catch (err) {
      setContactActionError(err.message || 'Failed to delete contact');
    } finally {
      setContactActionLoading(false);
    }
  };

  const handleToggleActive = async (contact) => {
    setContactActionLoading(true);
    setContactActionError('');
    try {
      await updateTrustedContact(managingContactsMember.id, contact.id, {
        is_active: !contact.is_active
      });
      await onRefresh();
    } catch (err) {
      setContactActionError(err.message || 'Failed to toggle status');
    } finally {
      setContactActionLoading(false);
    }
  };

  const handleSubmitMember = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');

    const phoneCheck = validatePhoneNumber(formData.phone, { required: true });
    if (!phoneCheck.valid) {
      setError(phoneCheck.error);
      setSubmitting(false);
      return;
    }

    let normalizedEcPhone = null;
    if (formData.emergency_contact_phone && formData.emergency_contact_phone.trim()) {
      const ecCheck = validatePhoneNumber(formData.emergency_contact_phone, { required: false });
      if (!ecCheck.valid) {
        setError(ecCheck.error);
        setSubmitting(false);
        return;
      }
      normalizedEcPhone = ecCheck.normalized;
    }

    try {
      const payload = {
        name: formData.name.trim(),
        relationship: formData.relationship.trim() || 'Family Member',
        age: formData.age !== '' ? parseInt(formData.age, 10) : null,
        phone: phoneCheck.normalized,
        email: formData.email.trim() || null,
        address: formData.address.trim() || null,
        blood_group: formData.blood_group || null,
        medical_notes: formData.medical_notes.trim() || '',
        emergency_contact_name: formData.emergency_contact_name.trim() || null,
        emergency_contact_phone: normalizedEcPhone,
        is_active: Boolean(formData.is_active)
      };

      if (editingMemberId) {
        await updateMember(editingMemberId, payload);
        setDashboardNotice({
          type: 'success',
          text: `Updated profile for ${payload.name}.`
        });
      } else {
        await createMember(payload);
        setDashboardNotice({
          type: 'success',
          text: `Created profile for ${payload.name}.`
        });
      }

      setShowMemberModal(false);
      setEditingMemberId(null);
      setFormData(EMPTY_MEMBER_FORM);
      await onRefresh();
    } catch (err) {
      setError(err.message || 'Error saving member profile');
    } finally {
      setSubmitting(false);
    }
  };

  // Keep modal's managingContactsMember synchronized with refreshed members array
  const currentModalMember = managingContactsMember
    ? members.find((m) => m.id === managingContactsMember.id) || managingContactsMember
    : null;

  const visibleMembers = members.filter((m) => {
    if (!showInactive && m.is_active === false) return false;
    if (hideDemoRecords && m.is_demo) return false;
    return true;
  });

  const demoCount = members.filter((m) => m.is_demo).length;
  const activeDemoCount = members.filter((m) => m.is_demo && m.is_active !== false).length;

  return (
    <div>
      {/* Dashboard Toolbar */}
      <div className="toolbar-strip" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Registered Household Profiles
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.15rem' }}>
            User-managed family profiles, multi-tier trusted contacts, and clinical health alerts
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            <span>Show Inactive</span>
          </label>

          {demoCount > 0 && (
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer', marginLeft: '0.35rem' }}>
              <input
                type="checkbox"
                checked={hideDemoRecords}
                onChange={(e) => setHideDemoRecords(e.target.checked)}
              />
              <span>Hide Seeded Demo Profiles ({demoCount})</span>
            </label>
          )}

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setDemoPrivacyMode(!demoPrivacyMode)}
            style={{
              fontSize: '0.74rem',
              padding: '0.35rem 0.65rem',
              borderColor: demoPrivacyMode ? 'var(--color-primary)' : 'var(--border-subtle)',
              color: demoPrivacyMode ? 'var(--color-primary)' : 'var(--text-secondary)',
              background: demoPrivacyMode ? 'var(--color-primary-soft)' : 'transparent',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              cursor: 'pointer'
            }}
            title={demoPrivacyMode ? "Demo Privacy Active: Contact details masked and safe placeholders shown" : "Demo Privacy Off: Displaying unmasked contacts"}
          >
            {demoPrivacyMode ? <EyeOff size={13} /> : <Eye size={13} />}
            {demoPrivacyMode ? 'Privacy Mask: Active' : 'Privacy Mask: Off'}
          </button>

          {user?.role === 'admin' && demoCount > 0 && (
            <button
              type="button"
              className="btn-secondary"
              style={{ fontSize: '0.74rem', padding: '0.35rem 0.65rem', borderColor: 'rgba(245, 158, 11, 0.35)', color: '#fbbf24' }}
              disabled={demoActionLoading}
              onClick={() => handleDemoControl(activeDemoCount > 0 ? 'deactivate' : 'activate')}
              title="Safely deactivate or restore initial seeded demo profiles without deleting historical incidents"
            >
              <Database size={13} />
              {demoActionLoading
                ? 'Updating...'
                : activeDemoCount > 0
                ? 'Deactivate Demo Records'
                : 'Restore Demo Records'}
            </button>
          )}

          {user?.role === 'admin' && (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleOpenInviteModal}
                style={{ borderColor: 'rgba(2, 132, 199, 0.4)', color: '#38bdf8' }}
              >
                <UserPlus size={15} /> Invite Member
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleOpenAddMember}
              >
                <Plus size={15} /> Add Family Member
              </button>
            </>
          )}
        </div>
      </div>

      {/* Feedback Banner */}
      {dashboardNotice && (
        <div
          style={{
            background: dashboardNotice.type === 'error' ? 'var(--color-danger-soft)' : 'var(--color-success-soft)',
            border: `1px solid ${dashboardNotice.type === 'error' ? 'var(--color-danger)' : 'var(--color-success)'}`,
            color: dashboardNotice.type === 'error' ? 'var(--color-danger)' : 'var(--color-success)',
            padding: '0.6rem 0.85rem',
            borderRadius: '8px',
            marginBottom: '1rem',
            fontSize: '0.8rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            {dashboardNotice.type === 'error' ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
            <span>{dashboardNotice.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setDashboardNotice(null)}
            style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Pending Household Invitations List (Phase 3B) */}
      {user?.role === 'admin' && invitations.length > 0 && (
        <div className="fc-panel" style={{ marginBottom: '1.25rem', padding: '1rem 1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <UserPlus size={16} color="var(--color-primary)" />
              <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--color-text)' }}>
                Pending Household Invitations
              </h3>
              <span style={{
                background: 'var(--color-primary-soft)',
                color: 'var(--color-primary)',
                border: '1px solid var(--color-primary)',
                borderRadius: '9999px',
                padding: '0.1rem 0.5rem',
                fontSize: '0.7rem',
                fontWeight: 700
              }}>
                {invitations.filter(i => i.status === 'PENDING').length} active
              </span>
            </div>
            <button
              type="button"
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
              onClick={handleOpenInviteModal}
            >
              + Send Another Invite
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
            {invitations.map((inv) => {
              const isPending = inv.status === 'PENDING';
              const isAccepted = inv.status === 'ACCEPTED';
              const statusColor = isPending ? 'var(--color-warning)' : isAccepted ? 'var(--color-success)' : 'var(--color-text-muted)';
              const statusBg = isPending ? 'var(--color-warning-soft)' : isAccepted ? 'var(--color-success-soft)' : 'var(--color-surface-elevated)';

              return (
                <div
                  key={inv.id}
                  style={{
                    background: 'var(--color-surface-elevated)',
                    border: '1px solid var(--color-border)',
                    borderRadius: '8px',
                    padding: '0.75rem 0.9rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: '0.5rem'
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--color-text)', wordBreak: 'break-all' }}>
                        {inv.invited_email}
                      </span>
                      <span style={{
                        background: statusBg,
                        color: statusColor,
                        padding: '0.15rem 0.45rem',
                        borderRadius: '4px',
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        textTransform: 'uppercase'
                      }}>
                        {inv.status}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Clock size={12} />
                      <span>Expires {new Date(inv.expires_at).toLocaleDateString()}</span>
                      <span>• Role: {inv.role}</span>
                    </div>
                  </div>

                  {isPending && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.25rem' }}>
                      <button
                        type="button"
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(239, 68, 68, 0.35)',
                          color: '#f87171',
                          borderRadius: '4px',
                          padding: '0.2rem 0.5rem',
                          fontSize: '0.72rem',
                          cursor: 'pointer'
                        }}
                        onClick={() => handleRevokeInvitation(inv.id)}
                      >
                        Revoke
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Member Cards Grid */}
      {visibleMembers.length === 0 ? (
        <div className="fc-panel" style={{ textAlign: 'center', padding: '3.5rem 1.5rem', margin: '1rem 0' }}>
          <Users size={44} color="#60a5fa" style={{ marginBottom: '0.75rem', opacity: 0.8 }} />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
            No Family Members in Household Roster
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', maxWidth: '480px', margin: '0 auto 1.25rem' }}>
            Build your family safety network by adding your first household member with their medical profile and trusted emergency contacts.
          </p>
          {user?.role === 'admin' && (
            <button
              type="button"
              className="btn-primary"
              onClick={handleOpenAddMember}
              style={{ padding: '0.65rem 1.25rem' }}
            >
              <Plus size={16} /> Add First Family Member
            </button>
          )}
        </div>
      ) : (
        <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))' }}>
          {visibleMembers.map((member) => {
          const contacts = member.trusted_contacts || [];
          const canManage = canManageMember(member.id);
          const isInactive = member.is_active === false;

          return (
            <div
              key={member.id}
              className="fc-panel"
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                opacity: isInactive ? 0.68 : 1,
                border: isInactive ? '1px dashed rgba(148, 163, 184, 0.3)' : undefined
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem', gap: '0.5rem' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {member.name}
                      </h3>
                      {member.is_demo && (
                        <span style={{
                          fontSize: '0.62rem',
                          padding: '0.08rem 0.38rem',
                          borderRadius: '4px',
                          background: 'rgba(245, 158, 11, 0.15)',
                          color: '#fbbf24',
                          border: '1px solid rgba(245, 158, 11, 0.35)',
                          fontWeight: 700
                        }}>
                          DEMO SEED
                        </span>
                      )}
                      {isInactive && (
                        <span style={{
                          fontSize: '0.62rem',
                          padding: '0.08rem 0.38rem',
                          borderRadius: '4px',
                          background: 'rgba(239, 68, 68, 0.15)',
                          color: '#f87171',
                          border: '1px solid rgba(239, 68, 68, 0.35)',
                          fontWeight: 700
                        }}>
                          INACTIVE
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                      {member.relationship} {member.age ? `• ${member.age} yrs` : ''}
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    {member.blood_group && (
                      <span style={{
                        background: 'var(--red-500-bg)',
                        color: '#f87171',
                        border: '1px solid var(--red-border)',
                        padding: '0.2rem 0.55rem',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: 800
                      }}>
                        {member.blood_group}
                      </span>
                    )}
                  </div>
                </div>

                {/* Phone, Email, Address, Primary Contact */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginBottom: '0.65rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    <Phone size={13} color="var(--color-primary)" />
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                      {maskPhoneNumber(member.phone, { isDemo: member.is_demo, demoSeed: member.id, enabled: demoPrivacyMode })}
                    </span>
                    {member.is_demo && (
                      <span style={{
                        fontSize: '0.62rem',
                        padding: '0.05rem 0.3rem',
                        borderRadius: '3px',
                        background: 'var(--amber-500-bg)',
                        color: 'var(--amber-500)',
                        border: '1px solid var(--amber-border)',
                        fontWeight: 700
                      }}>
                        DEMO PLACEHOLDER
                      </span>
                    )}
                  </div>
                  {member.email && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      <Mail size={13} color="var(--color-primary)" />
                      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {maskEmail(member.email, { isDemo: member.is_demo, demoSeed: member.name, enabled: demoPrivacyMode })}
                      </span>
                    </div>
                  )}
                  {member.address && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      <MapPin size={13} color="#059669" />
                      <span>{maskAddress(member.address, { isDemo: member.is_demo, enabled: demoPrivacyMode })}</span>
                    </div>
                  )}
                  {member.emergency_contact_phone && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.1rem', flexWrap: 'wrap' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Primary Contact:</span>
                      <strong style={{ color: 'var(--text-primary)' }}>{member.emergency_contact_name || 'Emergency Contact'}</strong>
                      <span>
                        ({maskPhoneNumber(member.emergency_contact_phone, { isDemo: member.is_demo, demoSeed: (member.id || 1) + 100, enabled: demoPrivacyMode })})
                      </span>
                    </div>
                  )}
                </div>

                {/* Medical notes */}
                {member.medical_notes && (
                  <div style={{
                    background: 'var(--bg-primary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '6px',
                    padding: '0.55rem 0.75rem',
                    marginBottom: '0.65rem',
                    fontSize: '0.78rem',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.45rem'
                  }}>
                    <HeartPulse size={13} color="#ef4444" style={{ marginTop: '2px', flexShrink: 0 }} />
                    <div>
                      <strong style={{ color: 'var(--text-primary)' }}>Medical Alert: </strong>
                      <span style={{ color: 'var(--text-secondary)' }}>{member.medical_notes}</span>
                    </div>
                  </div>
                )}

                {/* Trusted Contacts Section (Phase 4A & 6) */}
                <div style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '0.65rem 0.75rem',
                  fontSize: '0.78rem',
                  marginBottom: '0.85rem'
                }}>
                  <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center', marginBottom: '0.4rem', justifyContent: 'space-between' }}>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Users size={12} color="var(--color-primary)" />
                      Trusted Contact Network ({contacts.length})
                    </div>
                    {canManage && (
                      <button
                        type="button"
                        onClick={() => handleOpenContactManager(member)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--color-primary)',
                          cursor: 'pointer',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          padding: '0.1rem 0.3rem'
                        }}
                      >
                        Manage Contacts
                      </button>
                    )}
                  </div>

                  {contacts.length === 0 ? (
                    <div style={{ color: 'var(--amber-500)', fontSize: '0.74rem', fontStyle: 'italic' }}>
                      No trusted contacts configured yet. Add a contact so emergency alerts have a verified destination.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {contacts.map((c) => (
                        <div
                          key={c.id}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            background: 'var(--bg-primary)',
                            padding: '0.4rem 0.55rem',
                            borderRadius: '4px',
                            border: '1px solid var(--border-subtle)',
                            opacity: c.is_active ? 1 : 0.6
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
                              <span style={{
                                fontSize: '0.65rem',
                                padding: '0.08rem 0.35rem',
                                borderRadius: '3px',
                                background: c.priority === 1 ? 'var(--blue-500-bg)' : 'rgba(148, 163, 184, 0.15)',
                                color: c.priority === 1 ? 'var(--blue-500)' : 'var(--text-secondary)',
                                border: `1px solid ${c.priority === 1 ? 'var(--blue-border)' : 'var(--border-subtle)'}`,
                                fontWeight: 700
                              }}>
                                {c.priority === 1 ? 'PRIORITY 1' : `TIER ${c.priority}`}
                              </span>
                              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{c.name}</span>
                              <span style={{ color: 'var(--text-secondary)', fontSize: '0.7rem' }}>({c.relationship})</span>
                              {(c.is_demo || member.is_demo) && (
                                <span style={{
                                  fontSize: '0.62rem',
                                  color: 'var(--amber-500)',
                                  background: 'var(--amber-500-bg)',
                                  padding: '0.05rem 0.3rem',
                                  borderRadius: '3px',
                                  border: '1px solid var(--amber-border)',
                                  fontWeight: 700
                                }}>
                                  DEMO
                                </span>
                              )}
                            </div>
                            <div style={{ color: 'var(--text-secondary)', fontSize: '0.72rem', marginTop: '0.15rem' }}>
                              {maskPhoneNumber(c.phone, { isDemo: c.is_demo || member.is_demo, demoSeed: c.id, enabled: demoPrivacyMode })}
                              {c.email ? ` • ${maskEmail(c.email, { isDemo: c.is_demo || member.is_demo, demoSeed: c.name, enabled: demoPrivacyMode })}` : ''} • <span style={{ color: 'var(--purple-500)', fontWeight: 600 }}>{c.notification_preferences}</span>
                            </div>
                          </div>
                          {!c.is_active && (
                            <span style={{ fontSize: '0.65rem', color: 'var(--red-500)', border: '1px solid var(--red-border)', background: 'var(--red-500-bg)', padding: '0.05rem 0.25rem', borderRadius: '3px' }}>
                              Inactive
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Member Actions Footer */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', marginTop: '0.25rem' }}>
                {canManage && (
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn-secondary member-action-btn"
                      style={{ flex: 1, minWidth: '110px', justifyContent: 'center', fontSize: '0.74rem', padding: '0.32rem 0.5rem' }}
                      onClick={() => handleOpenEditMember(member)}
                    >
                      <Edit2 size={13} /> Edit Profile
                    </button>
                    {user?.role === 'admin' && (
                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                        <button
                          type="button"
                          className="btn-secondary member-action-btn"
                          style={{ fontSize: '0.74rem', padding: '0.32rem 0.55rem' }}
                          onClick={() => handleToggleMemberActive(member)}
                          title={isInactive ? 'Reactivate Member' : 'Deactivate Member'}
                        >
                          <Power size={13} /> {isInactive ? 'Activate' : 'Deactivate'}
                        </button>
                        <button
                          type="button"
                          className="btn-danger-outline member-action-icon-btn destructive-action-btn"
                          style={{ fontSize: '0.74rem', padding: '0.32rem 0.55rem' }}
                          onClick={() => handleDeleteOrDeactivateMember(member)}
                          title="Delete or deactivate member"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <button
                  type="button"
                  className="btn-danger-outline touch-target"
                  style={{ width: '100%', justifyContent: 'center', minHeight: '44px', fontWeight: 700 }}
                  disabled={isInactive}
                  onClick={() => onTriggerSosForMember(member)}
                >
                  <ShieldAlert size={15} />{' '}
                  {isInactive
                    ? 'Profile Inactive (Activate to Trigger SOS)'
                    : `Trigger SOS for ${member.name.split(' ')[0]}`}
                </button>
              </div>
            </div>
          );
        })}
      </div>
      )}

      {/* Trusted Contacts Management Modal */}
      {currentModalMember && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="manage-contacts-title">
          <div className="modal-content" style={{ maxWidth: '640px' }}>
            <div className="modal-header">
              <div>
                <h3 id="manage-contacts-title" style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Users size={18} color="var(--color-primary)" /> Trusted Contacts for {currentModalMember.name}
                </h3>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  Enter real phone numbers and email addresses. Demo privacy masking protects contact details during presentations.
                </p>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setManagingContactsMember(null)}
              >
                ✕
              </button>
            </div>

            {contactActionError && (
              <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', padding: '0.65rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.8rem' }}>
                {contactActionError}
              </div>
            )}
            {contactActionSuccess && (
              <div style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '0.65rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.8rem' }}>
                {contactActionSuccess}
              </div>
            )}

            {/* List of Current Contacts */}
            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                Configured Contacts (Sorted by Priority)
              </div>
              {(!currentModalMember.trusted_contacts || currentModalMember.trusted_contacts.length === 0) ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', padding: '0.75rem', background: 'var(--bg-primary)', borderRadius: '6px' }}>
                  No contacts found. Add one below.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {currentModalMember.trusted_contacts.map((c) => (
                    <div
                      key={c.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: 'var(--bg-primary)',
                        padding: '0.6rem 0.8rem',
                        borderRadius: '6px',
                        border: '1px solid var(--border-subtle)'
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <span style={{
                            fontSize: '0.68rem',
                            fontWeight: 800,
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                            background: c.priority === 1 ? 'var(--blue-500-bg)' : 'rgba(148, 163, 184, 0.15)',
                            color: c.priority === 1 ? 'var(--blue-500)' : 'var(--text-secondary)',
                            border: `1px solid ${c.priority === 1 ? 'var(--blue-border)' : 'var(--border-subtle)'}`
                          }}>
                            {c.priority === 1 ? 'PRIORITY 1 (PRIMARY)' : `TIER ${c.priority}`}
                          </span>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>{c.name}</span>
                          <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>({c.relationship})</span>
                          {(c.is_demo || currentModalMember.is_demo) && (
                            <span style={{
                              fontSize: '0.65rem',
                              color: 'var(--amber-500)',
                              background: 'var(--amber-500-bg)',
                              padding: '0.05rem 0.35rem',
                              borderRadius: '3px',
                              border: '1px solid var(--amber-border)',
                              fontWeight: 700
                            }}>
                              DEMO CONTACT
                            </span>
                          )}
                          {!c.is_active && (
                            <span style={{ fontSize: '0.65rem', color: 'var(--red-500)', border: '1px solid var(--red-border)', background: 'var(--red-500-bg)', padding: '0.05rem 0.3rem', borderRadius: '3px' }}>
                              Inactive
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          {maskPhoneNumber(c.phone, { isDemo: c.is_demo || currentModalMember.is_demo, demoSeed: c.id, enabled: demoPrivacyMode })}
                          {c.email ? ` • ${maskEmail(c.email, { isDemo: c.is_demo || currentModalMember.is_demo, demoSeed: c.name, enabled: demoPrivacyMode })}` : ''} • Channel: <span style={{ color: 'var(--purple-500)', fontWeight: 600 }}>{c.notification_preferences}</span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="btn-secondary contact-action-btn"
                          style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem' }}
                          onClick={() => handleToggleActive(c)}
                          disabled={contactActionLoading}
                        >
                          {c.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary contact-action-btn"
                          style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem' }}
                          onClick={() => handleStartEditContact(c)}
                          disabled={contactActionLoading}
                        >
                          <Edit2 size={12} /> Edit
                        </button>
                        <button
                          type="button"
                          className="btn-danger-outline contact-action-icon-btn destructive-action-btn"
                          style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem' }}
                          onClick={() => handleDeleteContact(c.id)}
                          disabled={contactActionLoading}
                          title="Delete trusted contact"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add / Edit Contact Form */}
            <form onSubmit={handleSaveContact} style={{ background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                {editingContactId ? <Edit2 size={14} color="#60a5fa" /> : <UserPlus size={14} color="#34d399" />}
                {editingContactId ? 'Edit Trusted Contact' : 'Add New Trusted Contact'}
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="tc-name">Full Name *</label>
                  <input
                    id="tc-name"
                    type="text"
                    required
                    className="form-input"
                    placeholder="Enter contact full name"
                    value={contactForm.name}
                    onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="tc-phone">Phone Number (+91) *</label>
                  <input
                    id="tc-phone"
                    type="text"
                    required
                    className="form-input"
                    placeholder="+91 98765 43210"
                    value={contactForm.phone}
                    onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })}
                  />
                  <span style={{ fontSize: '0.7rem', color: '#64748b', display: 'block', marginTop: '0.2rem' }}>
                    Default: India (+91). Accepts 10 digits or with country code.
                  </span>
                </div>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="tc-email">
                    Email Address {contactForm.notification_preferences.includes('EMAIL') ? '*' : '(Optional)'}
                  </label>
                  <input
                    id="tc-email"
                    type="email"
                    className="form-input"
                    placeholder="real.recipient@domain.com"
                    value={contactForm.email || ''}
                    onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="tc-rel">Relationship</label>
                  <input
                    id="tc-rel"
                    type="text"
                    className="form-input"
                    placeholder="Mother, Spouse, Guardian"
                    value={contactForm.relationship}
                    onChange={(e) => setContactForm({ ...contactForm, relationship: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="tc-priority">Escalation Priority Tier</label>
                  <select
                    id="tc-priority"
                    className="form-select"
                    value={contactForm.priority}
                    onChange={(e) => setContactForm({ ...contactForm, priority: parseInt(e.target.value, 10) })}
                  >
                    <option value={1}>1 (Primary Contact - Immediate Dispatch)</option>
                    <option value={2}>2 (Secondary Tier - Rapid Escalation)</option>
                    <option value={3}>3 (Tertiary Tier - Backup)</option>
                    <option value={4}>4 (Extended Safety Network)</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="tc-channel">Notification Channel</label>
                  <select
                    id="tc-channel"
                    className="form-select"
                    value={contactForm.notification_preferences}
                    onChange={(e) => setContactForm({ ...contactForm, notification_preferences: e.target.value })}
                  >
                    <option value="EMAIL">EMAIL (SMTP / Resend API)</option>
                    <option value="SMS">SMS (Twilio API)</option>
                    <option value="SMS,EMAIL">BOTH (SMS + EMAIL)</option>
                  </select>
                </div>
              </div>

              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.4rem' }}>
                <input
                  id="tc-active"
                  type="checkbox"
                  checked={contactForm.is_active}
                  onChange={(e) => setContactForm({ ...contactForm, is_active: e.target.checked })}
                />
                <label htmlFor="tc-active" style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  Active (Eligible for emergency alerts)
                </label>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', justifyContent: 'flex-end' }}>
                {editingContactId && (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleCancelEditContact}
                    disabled={contactActionLoading}
                  >
                    Cancel Edit
                  </button>
                )}
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={contactActionLoading}
                >
                  {contactActionLoading ? 'Saving...' : editingContactId ? 'Update Contact' : 'Add Contact'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add / Edit Member Modal */}
      {showMemberModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="member-modal-title">
          <div className="modal-content" style={{ maxWidth: '580px' }}>
            <div className="modal-header">
              <h3 id="member-modal-title" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {editingMemberId ? 'Edit Family Member Profile' : 'Register Family Member Profile'}
              </h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setShowMemberModal(false)}
              >
                ✕
              </button>
            </div>

            {error && (
              <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', padding: '0.65rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.8rem' }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmitMember}>
              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="new-name">Full Name *</label>
                  <input
                    id="new-name"
                    type="text"
                    required
                    className="form-input"
                    placeholder="Enter full name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-rel">Relationship *</label>
                  <input
                    id="new-rel"
                    type="text"
                    required
                    className="form-input"
                    placeholder="Mother, Son, Grandfather"
                    value={formData.relationship}
                    onChange={(e) => setFormData({ ...formData, relationship: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '0.75rem' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-phone">Phone Number (+91) *</label>
                  <input
                    id="new-phone"
                    type="text"
                    required
                    className="form-input"
                    placeholder="+91 98765 43210"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  />
                  <span style={{ fontSize: '0.7rem', color: '#64748b', display: 'block', marginTop: '0.2rem' }}>
                    Default: India (+91). Accepts 10 digits or with country code.
                  </span>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-age">Age</label>
                  <input
                    id="new-age"
                    type="number"
                    min="0"
                    max="130"
                    className="form-input"
                    placeholder="Age"
                    value={formData.age}
                    onChange={(e) => setFormData({ ...formData, age: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-blood">Blood Group</label>
                  <select
                    id="new-blood"
                    className="form-select"
                    value={formData.blood_group}
                    onChange={(e) => setFormData({ ...formData, blood_group: e.target.value })}
                  >
                    <option value="">Unknown / None</option>
                    <option value="A+">A+</option>
                    <option value="A-">A-</option>
                    <option value="B+">B+</option>
                    <option value="B-">B-</option>
                    <option value="AB+">AB+</option>
                    <option value="AB-">AB-</option>
                    <option value="O+">O+</option>
                    <option value="O-">O-</option>
                  </select>
                </div>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="new-email">Email Address (Optional)</label>
                  <input
                    id="new-email"
                    type="email"
                    className="form-input"
                    placeholder="member@domain.com"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-address">Home / Residential Address (Optional)</label>
                  <input
                    id="new-address"
                    type="text"
                    className="form-input"
                    placeholder="Street, City, State"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="new-notes">Medical Conditions / Allergies / Medications</label>
                <textarea
                  id="new-notes"
                  className="form-textarea"
                  rows={2}
                  placeholder="Pacemaker, Type 1 Diabetes, Penicillin allergy, etc."
                  value={formData.medical_notes}
                  onChange={(e) => setFormData({ ...formData, medical_notes: e.target.value })}
                />
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label className="form-label" htmlFor="new-contact-name">Primary Emergency Contact Name</label>
                  <input
                    id="new-contact-name"
                    type="text"
                    className="form-input"
                    placeholder="Primary contact name"
                    value={formData.emergency_contact_name}
                    onChange={(e) => setFormData({ ...formData, emergency_contact_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="new-contact-phone">Primary Emergency Contact Phone (+91)</label>
                  <input
                    id="new-contact-phone"
                    type="text"
                    className="form-input"
                    placeholder="+91 98765 43210"
                    value={formData.emergency_contact_phone}
                    onChange={(e) => setFormData({ ...formData, emergency_contact_phone: e.target.value })}
                  />
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.2rem' }}>
                    Optional. Accepts 10 digits or with country code.
                  </span>
                </div>
              </div>

              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
                <input
                  id="member-active"
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                />
                <label htmlFor="member-active" style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  Active Profile (Available in SOS dispatch selector)
                </label>
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.25rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowMemberModal(false)}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary"
                  style={{ flex: 1, justifyContent: 'center' }}
                >
                  {submitting ? 'Saving Profile...' : editingMemberId ? 'Update Member Profile' : 'Save Member Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Invite Family Member Modal (Phase 3B) */}
      {showInviteModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="invite-modal-title">
          <div className="modal-content" style={{ maxWidth: '480px', width: '92%' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <div style={{ background: 'rgba(2, 132, 199, 0.15)', padding: '0.45rem', borderRadius: '8px' }}>
                  <UserPlus size={22} color="#0284c7" />
                </div>
                <div>
                  <h2 id="invite-modal-title" style={{ margin: 0, fontSize: '1.15rem', color: 'var(--text-primary)' }}>
                    Invite Family Member
                  </h2>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Send secure email invitation with 72-hour validity
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setShowInviteModal(false)}
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </div>

            {lastCreatedInvite ? (
              <div style={{ padding: '1.5rem', textAlign: 'center' }}>
                <div style={{
                  display: 'inline-flex',
                  padding: '0.8rem',
                  borderRadius: '50%',
                  background: 'rgba(16, 185, 129, 0.15)',
                  color: '#10b981',
                  marginBottom: '1rem'
                }}>
                  <CheckCircle2 size={32} />
                </div>
                <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-primary)', fontSize: '1.1rem' }}>
                  Invitation Dispatched!
                </h3>
                <p style={{ margin: '0 0 1.25rem 0', color: '#94a3b8', fontSize: '0.86rem', lineHeight: 1.5 }}>
                  An email invitation has been sent to <strong>{lastCreatedInvite.invited_email}</strong>.
                  You can also copy the secure direct link below to share directly:
                </p>

                {lastCreatedInvite.invitation_link && (
                  <div style={{
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.25)',
                    borderRadius: '8px',
                    padding: '0.65rem 0.85rem',
                    marginBottom: '1.25rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    justifyContent: 'space-between'
                  }}>
                    <input
                      type="text"
                      readOnly
                      value={lastCreatedInvite.invitation_link}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#38bdf8',
                        fontSize: '0.78rem',
                        width: '100%',
                        outline: 'none'
                      }}
                    />
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem', whiteSpace: 'nowrap' }}
                      onClick={() => handleCopyInviteLink(lastCreatedInvite.invitation_link)}
                    >
                      {copiedLink ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                      <span>{copiedLink ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                )}

                <button
                  type="button"
                  className="btn-primary"
                  style={{ width: '100%' }}
                  onClick={() => setShowInviteModal(false)}
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleSendInvitation} style={{ padding: '1.25rem' }}>
                {inviteError && (
                  <div className="alert-banner alert-banner-danger" style={{ marginBottom: '1rem' }} role="alert">
                    <AlertTriangle size={16} color="#ef4444" />
                    <span>{inviteError}</span>
                  </div>
                )}

                <div className="form-group" style={{ marginBottom: '1rem' }}>
                  <label htmlFor="inv-email-field" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: '#cbd5e1' }}>
                    Invitee Email Address *
                  </label>
                  <div style={{ position: 'relative' }}>
                    <Mail size={16} color="#64748b" style={{ position: 'absolute', left: '10px', top: '12px' }} />
                    <input
                      id="inv-email-field"
                      type="email"
                      className="form-input"
                      style={{ paddingLeft: '2.2rem' }}
                      placeholder="e.g. member@example.com"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      required
                    />
                  </div>
                  <span style={{ fontSize: '0.72rem', color: '#64748b', display: 'block', marginTop: '0.25rem' }}>
                    Emergency emails are sent using the configured verified sender domain.
                  </span>
                </div>

                <div className="form-group" style={{ marginBottom: '1rem' }}>
                  <label htmlFor="inv-role-field" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: '#cbd5e1' }}>
                    Household Role
                  </label>
                  <select
                    id="inv-role-field"
                    className="form-input"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                  >
                    <option value="member">Family Member (Standard)</option>
                    <option value="admin">Co-Administrator</option>
                  </select>
                </div>

                <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                  <label htmlFor="inv-link-member" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.85rem', color: '#cbd5e1' }}>
                    Link to Existing Profile (Optional)
                  </label>
                  <select
                    id="inv-link-member"
                    className="form-input"
                    value={inviteMemberId}
                    onChange={(e) => setInviteMemberId(e.target.value)}
                  >
                    <option value="">-- Create new member profile on join --</option>
                    {members.filter(m => m.is_active !== false).map(m => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.relationship})
                      </option>
                    ))}
                  </select>
                  <span style={{ fontSize: '0.72rem', color: '#64748b', display: 'block', marginTop: '0.25rem' }}>
                    If selected, the invited user will claim and manage this existing profile upon registering.
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setShowInviteModal(false)}
                    disabled={inviteLoading}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={inviteLoading}
                    style={{ minWidth: '150px' }}
                  >
                    {inviteLoading ? 'Sending...' : 'Send Invitation'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
