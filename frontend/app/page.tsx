"use client";

import { useEffect, useRef, useState } from "react";
import AgentCard from "@/components/AgentCard";
import ScoreBar from "@/components/ScoreBar";
import {
  endSession,
  getRoles,
  parseResume,
  RoleInfo,
  Scorecard,
  startSession,
  StartSessionResponse,
  wsUrl,
} from "@/lib/api";
import { InterviewRoom } from "@/lib/agoraClient";
import { Snapshot } from "@/lib/types";

type Stage = "setup" | "connecting" | "active" | "ending" | "complete";

const SCORECARD_METRICS = [
  "domain_depth",
  "problem_solving",
  "communication",
  "ownership",
  "collaboration",
  "overall",
] as const;

export default function Page() {
  const [stage, setStage] = useState<Stage>("setup");
  const [candidateName, setCandidateName] = useState("");
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [roleKey, setRoleKey] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [resumeFileName, setResumeFileName] = useState<string | null>(null);
  const [resumeUploading, setResumeUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<StartSessionResponse | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [muted, setMuted] = useState(false);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const roomRef = useRef<InterviewRoom | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const startTsRef = useRef<number>(0);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getRoles()
      .then((r) => {
        setRoles(r);
        if (r.length > 0) setRoleKey(r[0].key);
      })
      .catch(() => setError("Couldn't load role list from the backend — is it running?"));
  }, []);

  useEffect(() => {
    if (stage !== "active") return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startTsRef.current) / 1000)), 1000);
    return () => clearInterval(t);
  }, [stage]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [snapshot?.transcript?.length]);

  async function handleResumeFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    setResumeUploading(true);
    setResumeFileName(file.name);
    try {
      const text = await parseResume(file);
      setResumeText(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to read resume file");
      setResumeFileName(null);
    } finally {
      setResumeUploading(false);
    }
  }

  async function handleStart() {
    setError(null);
    setStage("connecting");
    try {
      const s = await startSession(candidateName || "Candidate", roleKey, resumeText);
      setSession(s);

      const room = new InterviewRoom();
      roomRef.current = room;
      await room.join(s.app_id, s.channel, s.candidate_token, s.candidate_uid);

      const ws = new WebSocket(wsUrl(s.session_id));
      ws.onmessage = (evt) => setSnapshot(JSON.parse(evt.data));
      ws.onerror = () => setError("Lost connection to the panel backend (WebSocket).");
      wsRef.current = ws;

      startTsRef.current = Date.now();
      setStage("active");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start interview");
      setStage("setup");
    }
  }

  async function handleEnd() {
    if (!session) return;
    setStage("ending");
    try {
      const card = await endSession(session.session_id);
      setScorecard(card);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to end interview");
    } finally {
      await roomRef.current?.leave();
      wsRef.current?.close();
      setStage("complete");
    }
  }

  function toggleMute() {
    const next = !muted;
    setMuted(next);
    roomRef.current?.setMuted(next);
  }

  if (stage === "setup" || stage === "connecting") {
    const selectedRole = roles.find((r) => r.key === roleKey);
    return (
      <div className="setup-card">
        <h1>AI Interview Panel</h1>
        <p>Interviewers adapt to the role you pick. Grant mic access when prompted.</p>
        <div className="field">
          <label>Your name</label>
          <input value={candidateName} onChange={(e) => setCandidateName(e.target.value)} placeholder="Jane Doe" />
        </div>
        <div className="field">
          <label>Role you're interviewing for</label>
          <select value={roleKey} onChange={(e) => setRoleKey(e.target.value)}>
            {roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
          {selectedRole && <div className="panel-preview">Panel: {selectedRole.panel_titles.join(" · ")}</div>}
        </div>
        <div className="field">
          <label>Resume (optional)</label>
          <input type="file" accept=".pdf,.docx" onChange={(e) => handleResumeFile(e.target.files?.[0])} />
          {resumeUploading && <div className="hint">Reading {resumeFileName}…</div>}
          {!resumeUploading && resumeFileName && <div className="hint">Loaded {resumeFileName} — edit below if needed</div>}
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            placeholder="…or paste your resume text here"
            rows={5}
          />
        </div>
        {error && <p style={{ color: "#e0365a", fontSize: 13, fontWeight: 600 }}>{error}</p>}
        <button className="btn-primary" onClick={handleStart} disabled={stage === "connecting" || !roleKey}>
          {stage === "connecting" ? "Connecting…" : "Start Interview"}
        </button>
      </div>
    );
  }

  if (stage === "complete" && scorecard) {
    return (
      <div className="container">
        <div className="panel" style={{ maxWidth: 640, margin: "40px auto" }}>
          <h2>Final Scorecard</h2>
          <div className="recommendation">{scorecard.recommendation}</div>
          <div className="scorecard-grid">
            {SCORECARD_METRICS.map((k) => (
              <div className="scorecard-stat" key={k}>
                <div className="val">{scorecard[k]?.toFixed?.(1) ?? scorecard[k]}</div>
                <div className="lbl">{k.replace("_", " ")}</div>
              </div>
            ))}
          </div>
          {Object.entries(scorecard.panelist_comments ?? {}).map(([title, comment]) => (
            <p key={title}>
              <b>{title}:</b> {comment}
            </p>
          ))}
        </div>
      </div>
    );
  }

  const speaker = snapshot?.current_speaker ?? "candidate";
  const topics = snapshot?.topics ?? {};
  const panel = snapshot?.panel ?? session?.panel ?? [];

  function speakerLabel(id: string): string {
    if (id === "candidate") return "You";
    return panel.find((p) => p.id === id)?.title ?? id;
  }

  return (
    <div className="container">
      <div className="top-bar">
        <div>
          <h1>
            AI Interview Panel
            {session?.mock_mode && <span className="mock-badge">MOCK MODE</span>}
          </h1>
          <div className="sub">
            {candidateName || "Candidate"} · {snapshot?.role_title ?? session?.role_title} ·{" "}
            {String(Math.floor(elapsed / 60)).padStart(2, "0")}:{String(elapsed % 60).padStart(2, "0")}
          </div>
        </div>
        <div className="controls-row" style={{ marginTop: 0 }}>
          <button className="btn-secondary" onClick={toggleMute}>
            {muted ? "Unmute" : "Mute"}
          </button>
          <button className="btn-danger" onClick={handleEnd} disabled={stage === "ending"}>
            {stage === "ending" ? "Ending…" : "End Interview"}
          </button>
        </div>
      </div>

      <div className="agent-row">
        {panel.map((p) => (
          <AgentCard
            key={p.id}
            name={p.title}
            speaking={speaker === p.id}
            latencyMs={snapshot?.latency_ms?.[p.id]}
          />
        ))}
      </div>

      <div className="bottom-row">
        <div className="panel">
          <h2>Live Transcript</h2>
          <div className="transcript">
            {(snapshot?.transcript ?? []).map((line, i) => (
              <div key={i} className={`transcript-line ${line.speaker === "candidate" ? "candidate" : "panelist"}`}>
                <span className="speaker">{speakerLabel(line.speaker)}:</span>
                {line.text}
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>
        </div>

        <div className="panel">
          <h2>Topics Covered</h2>
          {Object.keys(topics).length === 0 && <p style={{ color: "var(--muted)", fontSize: 13 }}>Nothing detected yet.</p>}
          {Object.entries(topics).map(([topic, sig]) => (
            <ScoreBar key={topic} label={topic} value={sig.confidence} />
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Latency HUD</h2>
        <div className="latency-grid">
          {panel.map((p) => (
            <div key={p.id}>
              {p.title} TTFA: <b>{Math.round(snapshot?.latency_ms?.[p.id] ?? 0)}ms</b>
            </div>
          ))}
          <div>
            Turn: <b>{snapshot?.turn_count ?? 0}</b>
          </div>
        </div>
      </div>
    </div>
  );
}
