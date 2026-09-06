import { jsPDF } from "jspdf";
import { Scorecard } from "./api";

const METRIC_LABELS: Record<string, string> = {
  domain_depth: "Domain depth",
  problem_solving: "Problem solving",
  communication: "Communication",
  ownership: "Ownership",
  collaboration: "Collaboration",
  overall: "Overall",
};

// The five differentiating dimensions plotted on the radar — "overall" is a
// derived aggregate of these, so it's reported as text rather than as a 6th
// axis (a spoke that just mirrors the average of the others adds noise, not
// signal, to "which area do I actually lack").
const RADAR_METRIC_KEYS = ["domain_depth", "problem_solving", "communication", "ownership", "collaboration"];

const PAGE_WIDTH = 210;
const PAGE_HEIGHT = 297;
const MARGIN = 20;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;

function drawRadarChart(doc: jsPDF, cx: number, cy: number, radius: number, scorecard: Scorecard) {
  const n = RADAR_METRIC_KEYS.length;
  const angleFor = (i: number) => (i / n) * Math.PI * 2;
  const pointAt = (i: number, r: number): [number, number] => {
    const a = angleFor(i);
    return [cx + r * Math.sin(a), cy - r * Math.cos(a)];
  };

  doc.setDrawColor(224, 227, 243);
  doc.setLineWidth(0.2);
  [0.25, 0.5, 0.75, 1].forEach((f) => {
    for (let i = 0; i < n; i++) {
      const [x1, y1] = pointAt(i, radius * f);
      const [x2, y2] = pointAt((i + 1) % n, radius * f);
      doc.line(x1, y1, x2, y2);
    }
  });
  for (let i = 0; i < n; i++) {
    const [x, y] = pointAt(i, radius);
    doc.line(cx, cy, x, y);
  }

  const dataPoints = RADAR_METRIC_KEYS.map((key, i) => {
    const value = Math.max(0, Math.min(10, Number(scorecard[key as keyof Scorecard]) || 0));
    return pointAt(i, radius * (value / 10));
  });
  doc.setFillColor(236, 233, 254);
  doc.setDrawColor(109, 94, 248);
  doc.setLineWidth(0.6);
  const first = dataPoints[0];
  doc.lines(
    dataPoints.slice(1).map((p, i) => [p[0] - dataPoints[i][0], p[1] - dataPoints[i][1]]),
    first[0],
    first[1],
    [1, 1],
    "FD",
    true
  );

  doc.setFontSize(8.5);
  doc.setTextColor(35, 38, 58);
  RADAR_METRIC_KEYS.forEach((key, i) => {
    const [x, y] = pointAt(i, radius + 9);
    const align = Math.abs(Math.sin(angleFor(i))) < 0.15 ? "center" : Math.sin(angleFor(i)) > 0 ? "left" : "right";
    doc.text(`${METRIC_LABELS[key]} (${(Number(scorecard[key as keyof Scorecard]) || 0).toFixed(1)})`, x, y, { align });
  });
}

function ensureSpace(doc: jsPDF, y: number, needed: number): number {
  if (y + needed > PAGE_HEIGHT - MARGIN) {
    doc.addPage();
    return MARGIN;
  }
  return y;
}

export function downloadScorecardPdf(candidateName: string, roleTitle: string, scorecard: Scorecard) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  let y = MARGIN;

  doc.setFontSize(18);
  doc.setTextColor(35, 38, 58);
  doc.text("Interview scorecard report", MARGIN, y);
  y += 8;
  doc.setFontSize(11);
  doc.setTextColor(107, 114, 144);
  doc.text(`${candidateName} · ${roleTitle || "Interview"}`, MARGIN, y);
  y += 6;
  doc.setFontSize(12);
  doc.setTextColor(23, 178, 106);
  doc.text(`Recommendation: ${scorecard.recommendation}`, MARGIN, y);
  y += 12;

  // 1) Panelist comments, first.
  doc.setFontSize(14);
  doc.setTextColor(35, 38, 58);
  doc.text("Panelist comments", MARGIN, y);
  y += 8;
  doc.setFontSize(10.5);
  Object.entries(scorecard.panelist_comments ?? {}).forEach(([title, comment]) => {
    y = ensureSpace(doc, y, 14);
    doc.setTextColor(35, 38, 58);
    doc.text(title, MARGIN, y);
    y += 5;
    doc.setTextColor(80, 84, 110);
    const lines = doc.splitTextToSize(comment, CONTENT_WIDTH);
    doc.text(lines, MARGIN, y);
    y += lines.length * 5 + 5;
  });

  // 2) Why each score, and what raises it.
  y = ensureSpace(doc, y, 14);
  y += 4;
  doc.setFontSize(14);
  doc.setTextColor(35, 38, 58);
  doc.text("Score breakdown", MARGIN, y);
  y += 8;
  const metricFeedback = scorecard.metric_feedback ?? {};
  Object.entries(METRIC_LABELS).forEach(([key, label]) => {
    const value = scorecard[key as keyof Scorecard];
    const feedback = metricFeedback[key];
    y = ensureSpace(doc, y, 26);
    doc.setFontSize(11.5);
    doc.setTextColor(35, 38, 58);
    doc.text(`${label}: ${typeof value === "number" ? value.toFixed(1) : value}/10`, MARGIN, y);
    y += 5.5;
    doc.setFontSize(10);
    if (feedback?.why) {
      doc.setTextColor(80, 84, 110);
      const whyLines = doc.splitTextToSize(`Why: ${feedback.why}`, CONTENT_WIDTH);
      doc.text(whyLines, MARGIN, y);
      y += whyLines.length * 4.6 + 2;
    }
    if (feedback?.improve) {
      doc.setTextColor(80, 84, 110);
      const improveLines = doc.splitTextToSize(`To improve: ${feedback.improve}`, CONTENT_WIDTH);
      doc.text(improveLines, MARGIN, y);
      y += improveLines.length * 4.6 + 2;
    }
    y += 4;
  });

  // 3) Spider chart, last.
  y = ensureSpace(doc, y, 90);
  y += 4;
  doc.setFontSize(14);
  doc.setTextColor(35, 38, 58);
  doc.text("Score radar", MARGIN, y);
  y += 10;
  const chartRadius = 32;
  const chartCenterY = y + chartRadius + 6;
  y = ensureSpace(doc, y, chartRadius * 2 + 24);
  drawRadarChart(doc, PAGE_WIDTH / 2, chartCenterY, chartRadius, scorecard);
  y = chartCenterY + chartRadius + 14;

  if (scorecard.integrity) {
    y = ensureSpace(doc, y, 14);
    doc.setFontSize(9.5);
    doc.setTextColor(107, 114, 144);
    doc.text(
      `Proctoring: ${scorecard.integrity.tilt_events} head-tilt event(s), ${scorecard.integrity.away_events} away-from-camera event(s).`,
      MARGIN,
      y
    );
  }

  const safeName = candidateName.trim().replace(/[^a-z0-9]+/gi, "_").toLowerCase() || "candidate";
  doc.save(`interview-scorecard-${safeName}.pdf`);
}
