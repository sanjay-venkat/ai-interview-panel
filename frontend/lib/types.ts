export interface TopicSignal {
  score: number;
  confidence: number;
  mentions: number;
}

export interface TranscriptLine {
  speaker: string;
  text: string;
  ts: number;
}

export interface PanelMember {
  id: string;
  title: string;
}

export interface Snapshot {
  session_id: string;
  candidate_name: string;
  role_title: string;
  panel: PanelMember[];
  phase: "idle" | "active" | "deliberating" | "complete";
  current_speaker: string;
  turn_count: number;
  topics: Record<string, TopicSignal>;
  weaknesses: string[];
  claims: string[];
  transcript: TranscriptLine[];
  latency_ms: Record<string, number>;
  scorecard: Record<string, unknown> | null;
}
