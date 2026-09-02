const BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface StartSessionResponse {
  session_id: string;
  app_id: string;
  channel: string;
  candidate_uid: number;
  candidate_token: string;
  agent_uids: { technical_lead: number; hiring_manager: number };
  mock_mode: boolean;
}

export interface Scorecard {
  technical_depth: number;
  problem_solving: number;
  communication: number;
  ownership: number;
  system_design: number;
  overall: number;
  recommendation: string;
  technical_lead_comment: string;
  hiring_manager_comment: string;
}

export async function startSession(candidateName: string, role: string): Promise<StartSessionResponse> {
  const res = await fetch(`${BASE}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_name: candidateName, role }),
  });
  if (!res.ok) throw new Error(`start session failed: ${res.status}`);
  return res.json();
}

export async function endSession(sessionId: string): Promise<Scorecard> {
  const res = await fetch(`${BASE}/session/${sessionId}/end`, { method: "POST" });
  if (!res.ok) throw new Error(`end session failed: ${res.status}`);
  return res.json();
}

export function wsUrl(sessionId: string): string {
  const wsBase = BASE.replace(/^http/, "ws");
  return `${wsBase}/ws/${sessionId}`;
}
