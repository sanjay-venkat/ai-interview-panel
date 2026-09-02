import { PanelMember } from "./types";

const BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface RoleInfo {
  key: string;
  label: string;
  panel_titles: string[];
}

export interface StartSessionResponse {
  session_id: string;
  app_id: string;
  channel: string;
  candidate_uid: number;
  candidate_token: string;
  role_title: string;
  panel: (PanelMember & { uid: number })[];
  mock_mode: boolean;
}

export interface Scorecard {
  domain_depth: number;
  problem_solving: number;
  communication: number;
  ownership: number;
  collaboration: number;
  overall: number;
  recommendation: string;
  panelist_comments: Record<string, string>;
}

export async function getRoles(): Promise<RoleInfo[]> {
  const res = await fetch(`${BASE}/roles`);
  if (!res.ok) throw new Error(`fetch roles failed: ${res.status}`);
  return res.json();
}

export async function parseResume(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/resume/parse`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `resume parse failed: ${res.status}`);
  }
  const data = await res.json();
  return data.text as string;
}

export async function startSession(
  candidateName: string,
  roleKey: string,
  resumeText: string
): Promise<StartSessionResponse> {
  const res = await fetch(`${BASE}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_name: candidateName, role_key: roleKey, resume_text: resumeText }),
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
