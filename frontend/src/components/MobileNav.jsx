import React from 'react';
import { Radio, Users, UserCheck, Cpu, BookOpen } from 'lucide-react';

export default function MobileNav({
  activeTab,
  setActiveTab,
  activeIncidentsCount = 0,
  membersCount = 0,
  respondersCount = 0,
  user
}) {
  const isResponder = user?.role === 'responder';

  const handleTabClick = (tabId) => {
    setActiveTab(tabId);
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }
  };

  return (
    <nav className="mobile-bottom-nav" aria-label="Mobile Navigation" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'emergencies'}
        className={`mobile-nav-item ${activeTab === 'emergencies' ? 'active' : ''}`}
        onClick={() => handleTabClick('emergencies')}
        title="Incident Feed"
        data-testid="mobile-tab-emergencies"
      >
        <div className="mobile-nav-icon-wrap">
          <Radio size={19} />
          {activeIncidentsCount > 0 && (
            <span className="mobile-nav-badge" aria-label={`${activeIncidentsCount} active emergencies`}>
              {activeIncidentsCount}
            </span>
          )}
        </div>
        <span className="mobile-nav-label">Incidents</span>
      </button>

      {!isResponder && (
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'family'}
          className={`mobile-nav-item ${activeTab === 'family' ? 'active' : ''}`}
          onClick={() => handleTabClick('family')}
          title="Family Dashboard"
          data-testid="mobile-tab-family"
        >
          <div className="mobile-nav-icon-wrap">
            <Users size={19} />
            {membersCount > 0 && (
              <span className="mobile-nav-count-pill" aria-label={`${membersCount} family members`}>
                {membersCount}
              </span>
            )}
          </div>
          <span className="mobile-nav-label">Family</span>
        </button>
      )}

      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'responders'}
        className={`mobile-nav-item ${activeTab === 'responders' ? 'active' : ''}`}
        onClick={() => handleTabClick('responders')}
        title="Responders & Alerts"
        data-testid="mobile-tab-responders"
      >
        <div className="mobile-nav-icon-wrap">
          <UserCheck size={19} />
          {respondersCount > 0 && (
            <span className="mobile-nav-count-pill" aria-label={`${respondersCount} responders`}>
              {respondersCount}
            </span>
          )}
        </div>
        <span className="mobile-nav-label">Responders</span>
      </button>

      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'first-aid'}
        className={`mobile-nav-item ${activeTab === 'first-aid' ? 'active' : ''}`}
        onClick={() => handleTabClick('first-aid')}
        title="First Aid Guide"
        data-testid="mobile-tab-first-aid"
      >
        <div className="mobile-nav-icon-wrap">
          <BookOpen size={19} />
        </div>
        <span className="mobile-nav-label">First Aid</span>
      </button>

      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'ai-sandbox'}
        className={`mobile-nav-item ${activeTab === 'ai-sandbox' ? 'active' : ''}`}
        onClick={() => handleTabClick('ai-sandbox')}
        title="AI Triage Sandbox"
        data-testid="mobile-tab-ai-sandbox"
      >
        <div className="mobile-nav-icon-wrap">
          <Cpu size={19} />
        </div>
        <span className="mobile-nav-label">AI Sandbox</span>
      </button>
    </nav>
  );
}
