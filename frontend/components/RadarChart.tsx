export interface RadarMetric {
  key: string;
  label: string;
  value: number; // 0-10
}

interface Props {
  metrics: RadarMetric[];
  size: number;
  showLabels?: boolean;
}

const RINGS = [0.25, 0.5, 0.75, 1];

function pointOn(cx: number, cy: number, radius: number, angle: number): [number, number] {
  return [cx + radius * Math.sin(angle), cy - radius * Math.cos(angle)];
}

function polygonPoints(cx: number, cy: number, radius: number, n: number, fractionAt: (i: number) => number): string {
  return Array.from({ length: n }, (_, i) => {
    const angle = (i / n) * Math.PI * 2;
    const [x, y] = pointOn(cx, cy, radius * fractionAt(i), angle);
    return `${x},${y}`;
  }).join(" ");
}

/** Small, "just for attractive purposes" static shape by default (no axis
 * labels/ticks — see ScorecardReport); pass showLabels for the expanded
 * floating view where the reader actually studies which axis is weak. */
export default function RadarChart({ metrics, size, showLabels = false }: Props) {
  const n = metrics.length;
  const pad = showLabels ? size * 0.3 : size * 0.08;
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - pad;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Score radar chart">
      {RINGS.map((f) => (
        <polygon
          key={f}
          points={polygonPoints(cx, cy, radius, n, () => f)}
          fill="none"
          stroke="var(--panel-border)"
          strokeWidth={1}
        />
      ))}
      {showLabels &&
        metrics.map((m, i) => {
          const angle = (i / n) * Math.PI * 2;
          const [x, y] = pointOn(cx, cy, radius, angle);
          return <line key={m.key} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--panel-border)" strokeWidth={1} />;
        })}
      <polygon
        points={polygonPoints(cx, cy, radius, n, (i) => Math.max(0, Math.min(1, metrics[i].value / 10)))}
        fill="rgba(109, 94, 248, 0.32)"
        stroke="var(--accent)"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {metrics.map((m, i) => {
        const angle = (i / n) * Math.PI * 2;
        const frac = Math.max(0, Math.min(1, m.value / 10));
        const [x, y] = pointOn(cx, cy, radius * frac, angle);
        return <circle key={m.key} cx={x} cy={y} r={showLabels ? 3.5 : 2.5} fill="var(--accent)" />;
      })}
      {showLabels &&
        metrics.map((m, i) => {
          const angle = (i / n) * Math.PI * 2;
          // Always center-anchored: a "start"/"end" anchor lets a long label
          // extend outward from an already-near-the-edge point with no
          // bound, which clips past the viewBox for anything but the
          // shortest labels (e.g. "Problem solving" on a near-horizontal
          // axis). Centering on a point pulled in by a fixed `gap` keeps the
          // full label within the reserved `pad` margin regardless of angle.
          const gap = size * 0.03;
          const [x, y] = pointOn(cx, cy, radius + gap, angle);
          return (
            <text
              key={m.key}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={size * 0.032}
              fontWeight={600}
              fill="var(--text)"
            >
              {m.label}
            </text>
          );
        })}
    </svg>
  );
}
