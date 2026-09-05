"use client";

import { useEffect, useRef, useState } from "react";
import AgentCard from "@/components/AgentCard";
import CameraMonitor from "@/components/CameraMonitor";
import {
  endSession,
  getRoles,
  parseResume,
  reportProctorEvent,
  RoleInfo,
  Scorecard,
  startSession,
  StartSessionResponse,
  wsUrl,
} from "@/lib/api";
import { InterviewRoom } from "@/lib/agoraClient";
import { ProctorEventType } from "@/lib/faceProctor";
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

// Agora reports real audio energy per uid on a 0-100 scale; background
// noise/silence usually sits under this. Below the threshold, nobody's
// actually making sound.
const VOLUME_THRESHOLD = 5;
// Once an agent's audio crosses the threshold, keep them marked "speaking"
// for this long after the last time they did. Agora's volume-indicator
// event only fires roughly every 2 seconds (fixed by the SDK, not
// configurable), so this has to be comfortably longer than that or the
// indicator would flicker off between reports even while the agent is
// still actively talking.
const SPEAKING_HOLD_MS = 2600;

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
  const [camStream, setCamStream] = useState<MediaStream | null>(null);
  // Which panelist's audio is actually audible right now, driven by real
  // RTC volume data rather than by when the LLM finished generating text
  // (Agora's TTS keeps playing that response's audio well after the text
  // stream itself has ended, so text-generation timing alone badly
  // undercounts how long an agent is genuinely speaking).
  const [audioActiveAgentId, setAudioActiveAgentId] = useState<string | null>(null);

  const roomRef = useRef<InterviewRoom | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const startTsRef = useRef<number>(0);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const lastLoudAtRef = useRef<Record<string, number>>({});

  function stopCamera() {
    camStream?.getTracks().forEach((t) => t.stop());
    setCamStream(null);
  }

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

  // The backend can end the interview on its own — either the 45-minute
  // cap or the panel deciding it has covered enough ground — without the
  // candidate ever clicking "End Interview". Watch for that over the
  // WebSocket and follow the same wind-down the button triggers.
  useEffect(() => {
    if (snapshot?.phase !== "complete" || stage === "complete" || stage === "ending") return;
    if (snapshot.scorecard) setScorecard(snapshot.scorecard as unknown as Scorecard);
    roomRef.current?.leave();
    wsRef.current?.close();
    stopCamera();
    setStage("complete");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshot?.phase, snapshot?.scorecard, stage]);

  async function handleProctorEvent(type: ProctorEventType) {
    if (!session) return;
    try {
      await reportProctorEvent(session.session_id, type);
    } catch {
      // Best-effort — a dropped proctoring ping shouldn't interrupt the interview.
    }
  }

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
      let cam: MediaStream;
      try {
        cam = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 }, audio: false });
      } catch {
        throw new Error("Camera access is required — integrity monitoring watches for the candidate looking away or tilting out of frame. Please allow camera access and try again.");
      }
      setCamStream(cam);

      const s = await startSession(candidateName || "Candidate", roleKey, resumeText);
      setSession(s);

      const uidToAgentId: Record<number, string> = {};
      s.panel.forEach((p) => {
        uidToAgentId[p.uid] = p.id;
      });
      lastLoudAtRef.current = {};

      const room = new InterviewRoom();
      roomRef.current = room;
      room.onVolumeIndicator = (levels) => {
        const now = Date.now();
        for (const v of levels) {
          const agentId = uidToAgentId[Number(v.uid)];
          if (agentId && v.level > VOLUME_THRESHOLD) {
            lastLoudAtRef.current[agentId] = now;
          }
        }
        let activeId: string | null = null;
        let mostRecent = 0;
        for (const [id, ts] of Object.entries(lastLoudAtRef.current)) {
          if (now - ts <= SPEAKING_HOLD_MS && ts > mostRecent) {
            mostRecent = ts;
            activeId = id;
          }
        }
        setAudioActiveAgentId(activeId);
      };
      await room.join(s.app_id, s.channel, s.candidate_token, s.candidate_uid);

      const ws = new WebSocket(wsUrl(s.session_id));
      ws.onmessage = (evt) => setSnapshot(JSON.parse(evt.data));
      ws.onerror = () => setError("Lost connection to the panel backend (WebSocket).");
      wsRef.current = ws;

      startTsRef.current = Date.now();
      setStage("active");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start interview");
      stopCamera();
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
      stopCamera();
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
        <h1>Voice Verse Bot</h1>
        <p>
          Interviewers adapt to the role you pick. Grant mic and camera access when prompted — the camera is
          analyzed locally in your browser for integrity monitoring (looking away, tilting out of frame); no
          video ever leaves your device.
        </p>
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
          {scorecard.integrity && (
            <div className="integrity-summary">
              <span className="col-label" style={{ display: "inline", textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 12, color: "var(--muted)" }}>
                Proctoring
              </span>
              <p style={{ margin: "6px 0 0", fontSize: 13.5 }}>
                {scorecard.integrity.tilt_events} head-tilt event(s) &middot; {scorecard.integrity.away_events} away-from-camera event(s) detected during the session.
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Prefer the real, audio-driven signal (see onVolumeIndicator above) —
  // it's accurate for the agent's whole spoken audio, not just the brief
  // window while the LLM was still streaming text. Fall back to the
  // backend's own guess only when no one's audio has crossed the
  // threshold recently (e.g. right at the very start of a response).
  const speaker = audioActiveAgentId ?? snapshot?.current_speaker ?? "candidate";
  const topics = snapshot?.topics ?? {};
  const panel = snapshot?.panel ?? session?.panel ?? [];
  const maxDuration = session?.max_duration_seconds ?? 45 * 60;
  const remaining = Math.max(0, maxDuration - elapsed);
  const wrappingUp = snapshot?.phase === "deliberating";

  function speakerLabel(id: string): string {
    if (id === "candidate") return "You";
    return panel.find((p) => p.id === id)?.title ?? id;
  }

  function fmt(totalSeconds: number): string {
    return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
  }

  return (
    <div className="container">
      <div className="top-bar">
        <div>
          <h1>
            Voice Verse Bot
            {session?.mock_mode && <span className="mock-badge">MOCK MODE</span>}
          </h1>
          <div className="sub">
            {candidateName || "Candidate"} · {snapshot?.role_title ?? session?.role_title} · {fmt(elapsed)} elapsed ·{" "}
            <span style={{ color: remaining < 300 ? "#e0365a" : undefined, fontWeight: remaining < 300 ? 700 : undefined }}>
              {fmt(remaining)} left
            </span>
            {wrappingUp && <span className="mock-badge" style={{ background: "linear-gradient(90deg,#6d5ef8,#8b7bff)", color: "#fff" }}>WRAPPING UP</span>}
          </div>
        </div>
        <div className="controls-row" style={{ marginTop: 0 }}>
          <button className="btn-secondary" onClick={toggleMute} disabled={wrappingUp}>
            {muted ? "Unmute" : "Mute"}
          </button>
          <button className="btn-danger" onClick={handleEnd} disabled={stage === "ending" || wrappingUp}>
            {wrappingUp ? "Panel wrapping up…" : stage === "ending" ? "Ending…" : "End Interview"}
          </button>
        </div>
      </div>

      <div className="camera-monitor-row">
        <CameraMonitor
          stream={camStream}
          onEvent={handleProctorEvent}
          tiltCount={snapshot?.proctor_tilt_count ?? 0}
          awayCount={snapshot?.proctor_away_count ?? 0}
        />
      </div>

      <div className="agent-row">
        {panel.map((p) => (
          <AgentCard key={p.id} name={p.title} speaking={speaker === p.id} />
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
          <div className="topic-chip-row">
            {Object.entries(topics).map(([topic, sig]) => {
              const status = sig.confidence >= 0.75 ? "covered" : sig.confidence >= 0.45 ? "in-progress" : "mentioned";
              const label = status === "covered" ? "Covered" : status === "in-progress" ? "In Progress" : "Mentioned";
              return (
                <span key={topic} className={`topic-chip ${status}`}>
                  {topic}
                  <span className="topic-chip-status">{label}</span>
                </span>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
