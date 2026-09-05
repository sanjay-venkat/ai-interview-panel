interface Props {
  name: string;
  role?: string;
  speaking: boolean;
}

export default function AgentCard({ name, role, speaking }: Props) {
  return (
    <div className={`agent-card${speaking ? " speaking" : ""}`}>
      <div className="name">{name}</div>
      {role && <div className="role">{role}</div>}
      <div className="status-text">
        <span className={`status-dot${speaking ? " on" : ""}`} />
        {speaking ? "Speaking" : "Listening"}
      </div>
    </div>
  );
}
