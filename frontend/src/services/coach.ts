import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Coaching steps chain several LLM calls and may wait out Groq rate limits.
const api = axios.create({ baseURL: `${API_BASE_URL}/coach`, timeout: 300000 });

// ---------------- types (mirror src/langgraphagenticai/coach/state.py) ----------------

export interface RoleSkill { skill: string; required_level: number; jd_weight: number }

export interface RoleProfile { slug: string; title: string; description: string; skills: RoleSkill[] }

export interface RoleSuggestion {
  slug: string;
  title: string;
  description: string;
  readiness: number;
  strengths: string[];
  top_gaps: { skill: string; level: number; required_level: number }[];
}

export interface Observation { source: 'resume' | 'checkpoint' | 'interview'; value: number; note: string; cycle: number }

export interface SkillLevel extends RoleSkill {
  baseline: number;
  level: number;
  evidence: string[];
  observations: Observation[];
}

export interface Resource { title: string; url: string; type: string; source: string; meta?: string }

export interface Topic { title: string; why: string; resources: Resource[] }

export interface SkillTopics { skill: string; resources?: Resource[]; topics: Topic[] }

export interface RubricScore { correctness: number; depth: number; communication: number }

export interface InterviewTurn {
  skill: string;
  difficulty: number;
  question: string;
  is_follow_up: boolean;
  answer?: string;
  voice_metrics: Record<string, number>;
  score?: RubricScore;
  feedback: string;
  needs_follow_up: boolean;
  critic_note: string;
}

export interface ReadinessSnapshot { cycle: number; readiness: number; per_skill: Record<string, number>; at: string }

export interface CheckpointResult { skill: string; cycle: number; score: number; skipped: boolean }

export interface CoachState {
  candidate_id: string;
  target_role: string;
  role_slug?: string;
  target_readiness: number;
  max_cycles: number;
  interview_turns: number;
  skills: SkillLevel[];
  plan: SkillTopics[];
  checkpoint_queue: string[];
  checkpoints: CheckpointResult[];
  interview: InterviewTurn[];
  cycle: number;
  history: ReadinessSnapshot[];
  summary: string;
  next_steps: string[];
  status: 'diagnosing' | 'learning' | 'interviewing' | 'ready' | 'finished';
}

export interface CheckpointPrompt {
  type: 'checkpoint';
  skill: string;
  pending: string[];
  topics: Topic[];
  questions: { question: string; options: string[] }[];
}

export interface InterviewPrompt {
  type: 'interview_question';
  turn: number;
  of: number;
  skill: string;
  difficulty: number;
  is_follow_up: boolean;
  question: string;
}

export interface SessionView {
  thread_id: string;
  waiting_for: CheckpointPrompt | InterviewPrompt | null;
  done: boolean;
  readiness: number;
  state: CoachState;
  /** skill -> indexes of study topics ticked as done (current cycle) */
  topic_done: Record<string, number[]>;
}

export interface ProgressRow {
  thread_id: string;
  target_role: string;
  cycle: number;
  readiness: number;
  per_skill: Record<string, number>;
  created_at: string;
}

export interface RespondPayload {
  answers?: number[];
  action?: 'skip' | 'skip_all' | 'switch';
  skill?: string;
  answer?: string;
  voice_metrics?: Record<string, number>;
}

// ---------------- calls ----------------

export const coachApi = {
  roles: async () => (await api.get<RoleProfile[]>('/roles')).data,

  suggestRoles: async (resume: File) => {
    const form = new FormData();
    form.append('resume', resume);
    return (await api.post<RoleSuggestion[]>('/suggest-roles', form)).data;
  },

  start: async (params: {
    candidateId: string;
    resume: File;
    roleSlug?: string;
    jdText?: string;
    targetRole?: string;
    interviewTurns: number;
  }) => {
    const form = new FormData();
    form.append('candidate_id', params.candidateId);
    form.append('resume', params.resume);
    if (params.roleSlug) form.append('role_slug', params.roleSlug);
    if (params.jdText) form.append('jd_text', params.jdText);
    if (params.targetRole) form.append('target_role', params.targetRole);
    form.append('interview_turns', String(params.interviewTurns));
    return (await api.post<SessionView>('/start', form)).data;
  },

  session: async (threadId: string) => (await api.get<SessionView>(`/${threadId}`)).data,

  tickTopic: async (threadId: string, skill: string, topicIndex: number, done: boolean) =>
    (await api.post<{ topic_done: Record<string, number[]> }>(`/${threadId}/topics`, { skill, topic_index: topicIndex, done })).data,

  refreshPlan: async (threadId: string) => (await api.post<SessionView>(`/${threadId}/refresh-plan`)).data,

  respond: async (threadId: string, payload: RespondPayload) =>
    (await api.post<SessionView>(`/${threadId}/respond`, payload)).data,

  transcribe: async (audio: Blob) => {
    const form = new FormData();
    form.append('file', audio, 'answer.webm');
    return (await api.post<{ text: string; voice_metrics: Record<string, number> }>('/transcribe', form)).data;
  },

  progress: async (candidateId: string) => (await api.get<ProgressRow[]>(`/progress/${candidateId}`)).data,
};

export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (e.code === 'ECONNABORTED') return 'The coach took too long to respond. Please try again.';
    return e.message;
  }
  return String(e);
}

// ---------------- local identity ----------------
// No login: a random id in localStorage ties a browser's sessions together
// for the progress chart.

const CANDIDATE_KEY = 'talentfit-candidate-id';
const SESSIONS_KEY = 'talentfit-sessions';

export interface SavedSession { threadId: string; role: string; startedAt: string }

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function getCandidateId(): string {
  let id: string | null = null;
  try {
    id = localStorage.getItem(CANDIDATE_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(CANDIDATE_KEY, id);
    }
  } catch {
    id = id || 'anonymous';
  }
  return id;
}

export function savedSessions(): SavedSession[] {
  return read<SavedSession[]>(SESSIONS_KEY, []);
}

export function rememberSession(s: SavedSession) {
  try {
    const rest = savedSessions().filter((x) => x.threadId !== s.threadId);
    localStorage.setItem(SESSIONS_KEY, JSON.stringify([s, ...rest].slice(0, 10)));
  } catch {
    /* storage unavailable: sessions are still reachable by URL */
  }
}
