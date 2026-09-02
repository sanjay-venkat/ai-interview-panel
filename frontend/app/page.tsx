"use client";

import { useEffect, useRef, useState } from "react";
import AgentCard from "@/components/AgentCard";
import ScoreBar from "@/components/ScoreBar";
import { endSession, Scorecard, startSession, StartSessionResponse, wsUrl } from "@/lib/api";
import { InterviewRoom } from "@/lib/agoraClient";
import { Snapshot } from "@/lib/types";

type Stage = "setup" | "connecting" | "active" | "ending" | "complete";

export default function Page() {
  const [stage, setStage] = useState<Stage>("setup");
  const [candidateName, setCandidateName] = useState("");
  const [role, setRole] = useState("AI Engineer");
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
    if (stage !== "active") return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startTsRef.current) / 1000)), 1000);
    return () => clearInterval(t);
  }, [stage]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [snapshot?.transcript?.length]);

  async function handleStart() {
    setError(null);
    setStage("connecting");
    try {
      const s = await startSession(candidateName || "Candidate", role);
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
    return (
      <div className="setup-card">
        <h1>AI Interview Panel</h1>
        <p>Three AI interviewers, one live conversation. Grant mic access when prompted.</p>
        <div className="field">
          <label>Your name</label>
          <input value={candidateName} onChange={(e) => setCandidateName(e.target.value)} placeholder="Jane Doe" />
        </div>
        <div className="field">
          <label>Role you're interviewing for</label>
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="AI Engineer" />
        </div>
        {error && <p style={{ color: "#ff8a99", fontSize: 13 }}>{error}</p>}
        <button className="btn-primary" onClick={handleStart} disabled={stage === "connecting"}>
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
            {(
              [
                "technical_depth",
                "problem_solving",
                "communication",
                "ownership",
                "system_design",
                "culture_fit",
                "overall",
              ] as const
            ).map((k) => (
              <div className="scorecard-stat" key={k}>
                <div className="val">{scorecard[k]?.toFixed?.(1) ?? scorecard[k]}</div>
                <div className="lbl">{k.replace("_", " ")}</div>
              </div>
            ))}
          </div>
          <p><b>Technical Lead:</b> {scorecard.technical_lead_comment}</p>
          <p><b>Hiring Manager:</b> {scorecard.hiring_manager_comment}</p>
          <p><b>Culture &amp; Values Partner:</b> {scorecard.culture_fit_comment}</p>
        </div>
      </div>
    );
  }

  const speaker = snapshot?.current_speaker ?? "candidate";
  const topics = snapshot?.topics ?? {};

  return (
    <div className="container">
      <div className="top-bar">
        <div>
          <h1>
            AI Interview Panel
            {session?.mock_mode && <span className="mock-badge">MOCK MODE</span>}
          </h1>
          <div className="sub">
            {candidateName || "Candidate"} · {role} · {String(Math.floor(elapsed / 60)).padStart(2, "0")}:
            {String(elapsed % 60).padStart(2, "0")}
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
        <AgentCard
          name="Technical Lead"
          role="Architecture, implementation, trade-offs"
          speaking={speaker === "technical_lead"}
          latencyMs={snapshot?.latency_ms?.technical_lead}
        />
        <AgentCard
          name="Hiring Manager"
          role="Impact, ownership, communication"
          speaking={speaker === "hiring_manager"}
          latencyMs={snapshot?.latency_ms?.hiring_manager}
        />
        <AgentCard
          name="Culture & Values"
          role="Teamwork, conflict, adaptability"
          speaking={speaker === "culture_fit"}
          latencyMs={snapshot?.latency_ms?.culture_fit}
        />
      </div>

      <div className="bottom-row">
        <div className="panel">
          <h2>Live Transcript</h2>
          <div className="transcript">
            {(snapshot?.transcript ?? []).map((line, i) => (
              <div key={i} className={`transcript-line ${line.speaker}`}>
                <span className="speaker">
                  {line.speaker === "candidate"
                    ? "You"
                    : line.speaker === "technical_lead"
                    ? "Tech Lead"
                    : line.speaker === "hiring_manager"
                    ? "Hiring Mgr"
                    : "Culture"}
                  :
                </span>
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
          <div>Tech Lead TTFA: <b>{Math.round(snapshot?.latency_ms?.technical_lead ?? 0)}ms</b></div>
          <div>Hiring Mgr TTFA: <b>{Math.round(snapshot?.latency_ms?.hiring_manager ?? 0)}ms</b></div>
          <div>Culture TTFA: <b>{Math.round(snapshot?.latency_ms?.culture_fit ?? 0)}ms</b></div>
          <div>Turn: <b>{snapshot?.turn_count ?? 0}</b></div>
        </div>
      </div>
    </div>
  );
}
