from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class MCQQuestion(BaseModel):
    question: str = Field(..., description="The multiple-choice question text.")
    options: List[str] = Field(..., description="A list of four possible answer options.")
    answer: str = Field(..., description="The correct answer, which must be one of the options.")
    explanation: str = Field(..., description="A brief explanation for the correct answer.")

class InterviewQuestion(BaseModel):
    type: str = Field(..., description="The type of question, e.g., 'technical', 'behavioral'.")
    question: str = Field(..., description="The question text itself.")

class MCQAssessment(BaseModel):
    questions: List[MCQQuestion] = Field(..., description="A list of multiple-choice questions for the assessment.")

class InterviewAssessment(BaseModel):
    questions: List[InterviewQuestion] = Field(..., description="A list of interview questions.")

class CandidateState(BaseModel):
    # === Resume Info ===
    resume_file: Optional[str] = None
    resume_text: Optional[str] = None
    resume_clean: Optional[str] = None
    resume_sentences: List[str] = Field(default_factory=list)
    resume_words: List[str] = Field(default_factory=list)
    candidate_skills: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    candidate_experience: Optional[str] = None

    # === Job Description Info ===
    jd_file_path: Optional[str] = None
    jd_text: Optional[str] = None
    jd_clean: Optional[str] = None
    jd_sentences: List[str] = Field(default_factory=list)
    jd_words: List[str] = Field(default_factory=list)
    jd_skills: List[str] = Field(default_factory=list)
    jd_experience: Optional[str] = None

    # === Resume-JD Matching ===
    tfidf_score: float = 0.0
    bow_score: float = 0.0
    embedding_score: float = 0.0
    match_score: float = 0.0
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)

    # === Skill Gap Analysis ===
    skill_resources: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)
    priority_skills: List[str] = Field(default_factory=list)

    # === MCQ Test ===
    mcqs: List[MCQQuestion] = Field(default_factory=list)
    mcq_score: Optional[float] = None
    based_on_skills: List[str] = Field(default_factory=list)

    # === Interview ===
    interview_questions: List[InterviewQuestion] = Field(default_factory=list)
    candidate_answers: List[str] = Field(default_factory=list)
    interview_score: Optional[float] = None
    feedback: Optional[str] = None

    # === Final Feedback ===
    final_score: Optional[float] = None
    resume_feedback: Optional[str] = None
    skill_feedback: Optional[str] = None
    study_resources: Dict[str, str] = Field(default_factory=dict)
    next_steps: List[str] = Field(default_factory=list)