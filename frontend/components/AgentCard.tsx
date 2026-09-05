interface Props {
  name: string;
  role?: string;
  speaking: boolean;
}

export default function AgentCard({ name, role, speaking }: Props) {
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <div className={`agent-card${speaking ? " speaking" : ""}`}>
      <div className="agent-card-avatar">{initial}</div>
      <div>
        <div className="name">{name}</div>
        {role && <div className="role">{role}</div>}
      </div>
      <div className="status-text">
        <span className={`status-dot${speaking ? " on" : ""}`} />
        {speaking ? "Speaking" : "Listening"}
      </div>
    </div>
  );
}
