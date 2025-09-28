import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60000, // 60 second timeout for long-running operations
});

// Types based on the backend models
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
  
  tfidf_score: number;
  bow_score: number;
  embedding_score: number;
  match_score: number;
  matched_skills: string[];
  missing_skills: string[];
  
  skill_resources: Record<string, Array<{name: string; url: string; type: string}>>;
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

export interface ApiResponse<T = Record<string, any>> {
  thread_id: string;
  state: CandidateState;
}

// API Service Functions
export const apiService = {
  // Resume upload and analysis
  async uploadResume(file: File): Promise<{thread_id: string; state: CandidateState; resume_skills: string[]}> {
    const formData = new FormData();
    formData.append('resume', file);
    
    const response = await api.post('/resume-upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Job description upload and analysis
  async uploadJobDescription(payload: {state: CandidateState; thread_id: string}): Promise<{thread_id: string; state: CandidateState; jd_skills: string[]}> {
    const response = await api.post('/jd-upload', payload);
    return response.data;
  },

  // Match resume with job description
  async matchResumeWithJD(payload: {state: CandidateState; thread_id: string}): Promise<{thread_id: string; state: CandidateState; match_score: number; matched_skills: string[]; missing_skills: string[]}> {
    const response = await api.post('/match', payload);
    return response.data;
  },

  // Skill gap analysis
  async analyzeSkillGap(payload: {state: CandidateState; thread_id: string}): Promise<{thread_id: string; state: CandidateState; skill_resources: Record<string, any>; priority_skills: string[]}> {
    const response = await api.post('/skill-gap', payload);
    return response.data;
  },

  // Generate assessment (MCQs)
  async generateAssessment(payload: {state: CandidateState; thread_id: string}): Promise<{thread_id: string; state: CandidateState; mcqs: MCQQuestion[]}> {
    const response = await api.post('/assessment', payload);
    return response.data;
  },

  // Generate interview questions
  async generateInterview(payload: {state: CandidateState; thread_id: string}): Promise<{thread_id: string; state: CandidateState; interview_questions: InterviewQuestion[]}> {
    const response = await api.post('/interview', payload);
    return response.data;
  },

  // Evaluate interview answers
  async evaluateInterview(payload: {state: CandidateState; thread_id: string}): Promise<{thread_id: string; state: CandidateState; interview_score: number; feedback: string}> {
    const response = await api.post('/evaluate-interview', payload);
    return response.data;
  },
};

export default apiService;