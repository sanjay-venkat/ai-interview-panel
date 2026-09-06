// Each interviewer's on-screen persona is keyed by ARCHETYPE (domain_lead /
// hiring_manager / culture_fit), not by panel position or the per-role
// `title` string — the same three people play every role, they just carry a
// different designation (title) depending on which role the candidate is
// interviewing for. This keeps a panelist's avatar/name/color stable across
// roles, instead of the old behavior where a card's identity (and its color)
// depended purely on which slot (1st/2nd/3rd) it happened to render in.
const ARCHETYPE_PERSONA: Record<string, { displayName: string; initials: string }> = {
  domain_lead: { displayName: "Alex Chen", initials: "AC" },
  hiring_manager: { displayName: "Priya Sharma", initials: "PS" },
  culture_fit: { displayName: "Jordan Lee", initials: "JL" },
};

interface Props {
  /** Backend PanelMember.title, e.g. "Technical Lead" or "AI Technical Lead" — varies per role. */
  designation: string;
  /** Backend PanelMember.archetype, e.g. "domain_lead" — stable across roles. */
  archetype?: string;
  speaking: boolean;
}

function AvatarIcon() {
  // A simple, static person-bust glyph — same shape for every panelist; only
  // the surrounding circle's color (set via the archetype-N CSS class)
  // varies, so "static avatar" reads as one consistent visual identity
  // system rather than a random photo per agent.
  return (
    <svg viewBox="0 0 40 40" width="40" height="40" aria-hidden="true">
      <circle cx="20" cy="15" r="7" fill="currentColor" />
      <path d="M6 35c0-8 6.3-13 14-13s14 5 14 13" fill="currentColor" />
    </svg>
  );
}

export default function AgentCard({ designation, archetype, speaking }: Props) {
  const persona = (archetype && ARCHETYPE_PERSONA[archetype]) || null;
  const archetypeClass = archetype ? `archetype-${archetype}` : "archetype-fallback";
  const fallbackInitial = designation.trim().charAt(0).toUpperCase() || "?";

  return (
    <div className={`agent-card ${archetypeClass}${speaking ? " speaking" : ""}`}>
      <div className="agent-card-avatar">{persona ? <AvatarIcon /> : fallbackInitial}</div>
      <div>
        <div className="name">{persona?.displayName ?? designation}</div>
        <div className="role">{persona ? designation : "Interviewer"}</div>
      </div>
      <div className="status-text">
        <span className={`status-dot${speaking ? " on" : ""}`} />
        {speaking ? "Speaking" : "Listening"}
      </div>
    </div>
  );
}
