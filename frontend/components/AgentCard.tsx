interface Props {
  name: string;
  role: string;
  speaking: boolean;
  latencyMs?: number;
}

export default function AgentCard({ name, role, speaking, latencyMs }: Props) {
  return (
    <div className={`agent-card${speaking ? " speaking" : ""}`}>
      <div className="name">{name}</div>
      <div className="role">{role}</div>
      <div className="status-text">
        <span className={`status-dot${speaking ? " on" : ""}`} />
        {speaking ? "Speaking" : "Listening"}
        {typeof latencyMs === "number" && speaking === false && latencyMs > 0 && (
          <span> · last TTFA {Math.round(latencyMs)}ms</span>
        )}
      </div>
    </div>
  );
}
