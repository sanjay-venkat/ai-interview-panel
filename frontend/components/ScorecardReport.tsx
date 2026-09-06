"use client";

import { useState } from "react";
import { Scorecard } from "@/lib/api";
import { downloadScorecardPdf } from "@/lib/pdfReport";
import RadarChart from "./RadarChart";

const METRIC_ORDER = [
  { key: "domain_depth", label: "Domain depth" },
  { key: "problem_solving", label: "Problem solving" },
  { key: "communication", label: "Communication" },
  { key: "ownership", label: "Ownership" },
  { key: "collaboration", label: "Collaboration" },
  { key: "overall", label: "Overall" },
] as const;

// "overall" is a derived aggregate of the other five, so it's a click-button
// (with its own why/improve) but not its own radar spoke — see RadarChart.
const RADAR_KEYS = ["domain_depth", "problem_solving", "communication", "ownership", "collaboration"] as const;

interface Props {
  scorecard: Scorecard;
  candidateName: string;
  roleTitle: string;
}

export default function ScorecardReport({ scorecard, candidateName, roleTitle }: Props) {
  const [openMetric, setOpenMetric] = useState<string | null>(null);
  const [chartExpanded, setChartExpanded] = useState(false);

  const radarMetrics = RADAR_KEYS.map((key) => ({
    key,
    label: METRIC_ORDER.find((m) => m.key === key)!.label,
    value: Number(scorecard[key]) || 0,
  }));

  const activeMetric = METRIC_ORDER.find((m) => m.key === openMetric) ?? null;
  const activeFeedback = openMetric ? scorecard.metric_feedback?.[openMetric] : undefined;
  const activeValue = openMetric ? Number(scorecard[openMetric as keyof Scorecard]) : null;

  return (
    <div className="panel scorecard-report">
      <h2>Final Scorecard</h2>
      <div className="recommendation">{scorecard.recommendation}</div>

      <div className="scorecard-grid">
        {METRIC_ORDER.map(({ key, label }) => (
          <button key={key} type="button" className="scorecard-stat score-btn" onClick={() => setOpenMetric(key)}>
            <div className="val">{scorecard[key].toFixed(1)}</div>
            <div className="lbl">{label}</div>
            <div className="click-cta">Click to see why →</div>
          </button>
        ))}
      </div>

      <div className="radar-section">
        <button
          type="button"
          className="radar-thumb-btn"
          onClick={() => setChartExpanded(true)}
          aria-label="Expand the score radar chart"
        >
          <RadarChart metrics={radarMetrics} size={140} />
        </button>
        <div className="radar-caption">
          <div>Your strengths at a glance</div>
          <div className="click-cta">Click chart to expand →</div>
        </div>
      </div>

      {Object.keys(scorecard.panelist_comments ?? {}).length > 0 && (
        <div className="panelist-comments">
          {Object.entries(scorecard.panelist_comments).map(([title, comment]) => (
            <p key={title}>
              <b>{title}:</b> {comment}
            </p>
          ))}
        </div>
      )}

      {scorecard.integrity && (
        <div className="integrity-summary">
          <span
            style={{
              display: "inline-block",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              fontSize: 12,
              color: "var(--muted)",
            }}
          >
            Proctoring
          </span>
          <p style={{ margin: "6px 0 0", fontSize: 13.5 }}>
            {scorecard.integrity.tilt_events} head-tilt event(s) &middot; {scorecard.integrity.away_events}{" "}
            away-from-camera event(s) detected during the session.
          </p>
        </div>
      )}

      <div className="download-row">
        <button
          type="button"
          className="btn-primary download-btn"
          onClick={() => downloadScorecardPdf(candidateName, roleTitle, scorecard)}
        >
          Download report (PDF)
        </button>
      </div>

      {activeMetric && (
        <div className="modal-overlay" onClick={() => setOpenMetric(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal-close" onClick={() => setOpenMetric(null)} aria-label="Close">
              &times;
            </button>
            <div className="modal-score">{activeValue !== null ? activeValue.toFixed(1) : "—"}/10</div>
            <h3>{activeMetric.label}</h3>
            {activeFeedback ? (
              <>
                <p>
                  <b>Why this score:</b> {activeFeedback.why}
                </p>
                <p>
                  <b>To score higher:</b> {activeFeedback.improve}
                </p>
              </>
            ) : (
              <p>No detailed feedback was recorded for this metric.</p>
            )}
          </div>
        </div>
      )}

      {chartExpanded && (
        <div className="modal-overlay" onClick={() => setChartExpanded(false)}>
          <div className="modal-card modal-card-wide" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal-close" onClick={() => setChartExpanded(false)} aria-label="Close">
              &times;
            </button>
            <h3>Score radar</h3>
            <RadarChart metrics={radarMetrics} size={360} showLabels />
            <p className="radar-hint">
              A bigger shape on an axis means a stronger performance there — the shortest spokes are where to focus
              next.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
