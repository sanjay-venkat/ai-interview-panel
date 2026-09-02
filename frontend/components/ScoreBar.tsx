interface Props {
  label: string;
  value: number; // 0..1
}

export default function ScoreBar({ label, value }: Props) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="score-bar-row">
      <div className="label">{label}</div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <div>{Math.round(pct)}%</div>
    </div>
  );
}
