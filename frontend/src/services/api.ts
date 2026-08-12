import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60000, // 60 seconds timeout for long-running operations
});

// ============================================================
// 🧩 Types
// ============================================================
export interface CandidateState {
  resume_file?: string;
  resume_text?: string;
  resume_clean?: string;
  resume_sentences: string[];
  resume_words: string[];
  candidate_skills: string[];
  education: string[];
  candidate_experience?: string;

  jd_file_path?: string;
  jd_text?: string;
  jd_clean?: string;
  jd_sentences: string[];
  jd_words: string[];
  jd_skills: string[];
  jd_experience?: string;
  company?: string;          // ✅ Added
  date?: string;             // ✅ Added

  tfidf_score: number;
  bow_score: number;
  embedding_score: number;
  match_score: number;
  matched_skills: string[];
  missing_skills: string[];

  skill_resources: Record<string, Array<{ name: string; url: string; type: string }>>;
  priority_skills: string[];

  mcqs: MCQQuestion[];
  mcq_score?: number;
  based_on_skills: string[];

  interview_questions: InterviewQuestion[];
  candidate_answers: string[];
  interview_score?: number;
  feedback?: string;

  final_score?: number;
  resume_feedback?: string;
  skill_feedback?: string;
  study_resources: Record<string, string>;
  next_steps: string[];
}

export interface MCQQuestion {
  question: string;
  options: string[];
  answer: string;
  explanation: string;
}

export interface InterviewQuestion {
  type: string;
  question: string;
}

// ============================================================
// 🧩 JD Types (Admin Panel)
// ============================================================

// ✅ Updated JD Payload with company name and date fields
export interface JDCreatePayload {
  title: string;
  text: string;
  company: string;    // ✅ Added
  date: string;       // ✅ Added (store date as ISO string or yyyy-mm-dd)
}

// ✅ JDResponse includes new fields
export interface JDResponse extends JDCreatePayload {
  id: number;
}

// For dropdowns or summaries
export interface JDSummary {
  id: number;
  title: string;
  company?: string;   // ✅ Added
  date?: string;      // ✅ Added
}

export interface ApiResponse<T = Record<string, any>> {
  thread_id: string;
  state: CandidateState;
}

// ============================================================
// 🧠 API SERVICE
// ============================================================
export const apiService = {
  baseURL: API_BASE_URL,

  // ----------------------------------------------------
  // 💻 ADMIN PANEL ENDPOINTS
  // ----------------------------------------------------

  /** ➕ Adds a new Job Description to the SQLite database. */
  async createJD(payload: JDCreatePayload): Promise<JDResponse> {
    const response = await api.post('/admin/jds', payload);
    return response.data;
  },

  /** 📖 Lists ALL JDs with full details for admin view. */
  async listAllJDs(): Promise<JDResponse[]> {
    const response = await api.get('/admin/jds');
    return response.data;
  },

  /** 🗑️ Deletes a Job Description by ID. */
  async deleteJD(jdId: number): Promise<void> {
    await api.delete(`/admin/jds/${jdId}`);
  },

  // ----------------------------------------------------
  // CORE RECRUITMENT ENDPOINTS
  // ----------------------------------------------------

  /** 🧾 Upload Resume */
  async uploadResume(file: File): Promise<{ thread_id: string; state: CandidateState; resume_skills: string[] }> {
    const formData = new FormData();
    formData.append('resume', file);
    const response = await api.post('/resume-upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  /** 📋 Gets a list of available JDs (ID and Title) from the real database. */
  async getAvailableJDs(): Promise<JDSummary[]> {
    const response = await api.get('/jds');
    return response.data;
  },

 /** ⚡ Matches Resume against ALL JDs in the database and selects the best. */
  async matchAllJDs(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{
    thread_id: string;
    state: CandidateState;
    best_match_title: string;
    jd_text: string;
    match_score: number;
    matched_skills: string[];
    missing_skills: string[];
    company?: string;
    date?: string;
  }> {
    const response = await api.post('/match-all-jds', payload);
    return {
      thread_id: response.data.thread_id,
      state: response.data.state,
      best_match_title: response.data.best_match_title,
      jd_text: response.data.jd_text,
      match_score: response.data.match_score,
      matched_skills: response.data.matched_skills || [],
      missing_skills: response.data.missing_skills || [],
      company: response.data.company,
      date: response.data.date,
    };
  },
  // ----------------------------------------------------
  // Remaining Core APIs
  // ----------------------------------------------------

  /** 🧾 Upload Job Description (Deprecated by matchAllJDs) */
  async uploadJobDescription(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{ thread_id: string; state: CandidateState; jd_skills: string[] }> {
    const response = await api.post('/jd-upload', payload);
    return response.data;
  },

  /** 📊 Match Resume and JD (Deprecated by matchAllJDs) */
  async matchResumeWithJD(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{
    thread_id: string;
    state: CandidateState;
    match_score: number;
    matched_skills: string[];
    missing_skills: string[];
    company?: string;   // ✅ Added
    date?: string;      // ✅ Added
  }> {
    const response = await api.post('/match', payload);
    return response.data;
  },

  /** 🧠 Skill Gap Analysis */
  async analyzeSkillGap(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{
    thread_id: string;
    state: CandidateState;
    skill_resources: Record<string, any>;
    priority_skills: string[];
  }> {
    const response = await api.post('/skill-gap', payload);
    return response.data;
  },

  /** 🧮 Generate Assessment (MCQs) */
  async generateAssessment(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{ thread_id: string; state: CandidateState; mcqs: MCQQuestion[] }> {
    const response = await api.post('/assessment', payload);
    return response.data;
  },

  /** 🎤 Generate Interview Questions */
  async generateInterview(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{ thread_id: string; state: CandidateState; interview_questions: InterviewQuestion[] }> {
    const response = await api.post('/interview', payload);
    return response.data;
  },

  /** 🧠 Evaluate Interview Answers */
  async evaluateInterview(payload: {
    state: CandidateState;
    thread_id: string;
  }): Promise<{
    thread_id: string;
    state: CandidateState;
    interview_score: number;
    feedback: string;
  }> {
    const response = await api.post('/evaluate-interview', payload);
    return response.data;
  },

  /** 🎧 Transcribe Audio using Groq Whisper */
  async transcribeGroq(thread_id: string, question_index: number, blob: Blob): Promise<{ text: string }> {
    const formData = new FormData();
    formData.append('file', blob, 'answer.webm');
    formData.append('thread_id', thread_id);
    formData.append('question_index', question_index.toString());

    const response = await axios.post(`${API_BASE_URL}/transcribe-groq`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    return response.data;
  },
};

export default apiService;
