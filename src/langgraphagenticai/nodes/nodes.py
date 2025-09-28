import re
import string
import json
import numpy as np
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.exceptions import OutputParserException

from src.langgraphagenticai.state.state import CandidateState, MCQAssessment, InterviewAssessment
from src.langgraphagenticai.LLMS.groqllm import GroqLLM
from src.langgraphagenticai.tools.web_search_tool import WebSearchTool
from src.langgraphagenticai.tools.interview_search_tool import InterviewWebSearchTool


embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# ------------------ Utility functions ------------------ #

def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception:
        pass
    return text

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9+.# ]", "", text)
    return text


def tokenize_text(text: str):
    return sent_tokenize(text), word_tokenize(text)

def get_embedding(text: str) -> np.ndarray:
    return np.array(embedding_model.encode([text]))

def vectorize_texts(resume_text: str, jd_text: str):
    tfidf = TfidfVectorizer()
    tfidf_matrix = tfidf.fit_transform([resume_text, jd_text])
    tfidf_score = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])

    bow = CountVectorizer()
    bow_matrix = bow.fit_transform([resume_text, jd_text])
    bow_score = float(cosine_similarity(bow_matrix[0:1], bow_matrix[1:2])[0][0])

    emb_score = float(cosine_similarity(get_embedding(resume_text), get_embedding(jd_text))[0][0])
    return tfidf_score, bow_score, emb_score

# ------------------ Skill List ------------------ #
RAW_COMMON_SKILLS = [
    # Programming Languages
    "python", "java", "c", "c++", "c#", "javascript", "typescript", "go", "rust", "ruby", "php", "swift", "kotlin", "scala", "perl", "r", "matlab", "dart",
    
    # Web Development
    "html", "css", "bootstrap", "sass", "less",
    "react", "angular", "vue", "next.js", "nuxt", "ember.js", "jquery",
    "node", "express", "django", "flask", "fastapi", "spring", "laravel", "react native",
    
    # Databases
    "sql", "mysql", "postgresql", "sqlite", "mongodb", "cassandra", "redis", "oracle", "firebase", "dynamodb",
    
    # Data Science & Analytics
    "numpy", "pandas", "scikit-learn", "matplotlib", "seaborn", "plotly", "tensorflow", "pytorch", "keras", "opencv", "nltk", "spacy",
    "statsmodels", "mlflow", "xgboost", "lightgbm", "catboost", "shap", "lime",
    
    # ML/AI Libraries
    "transformers", "huggingface",
    
    # Mobile Development
    "android", "ios", "flutter", "xamarin",
    
    # Cloud & DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible", "ci/cd", "jenkins", "gitlab ci", "circleci", "travis ci", 
    "helm", "prometheus", "grafana", "elk stack", "splunk", "mlops",
    
    # Networking & Security
    "tcp/ip", "udp", "dns", "firewall", "vpn", "wireshark", "penetration testing", "cybersecurity", "network security", "oauth", "jwt", "ssl", "tls",
    
    # Scripting & Automation
    "bash", "shell scripting", "powershell", "automation", "robot framework", "selenium", "puppeteer",
    
    # API & Integration
    "rest api", "graphql", "soap", "postman", "grpc", "webhooks",
    
    # Operating Systems
    "linux", "windows", "macos", "unix",
    
    # General Tools
    "git", "github", "gitlab", "jira", "confluence", "trello", "slack", "notion", "excel", "power bi", "tableau"
]


COMMON_SKILLS = sorted([skill.lower() for skill in RAW_COMMON_SKILLS], key=lambda x: -len(x))

def extract_skills(text: str, skills_list: list = RAW_COMMON_SKILLS) -> list:
    """
    Extract skills from text based on a skills list.
    Handles short valid skills (C, R, Go) carefully to avoid false positives.
    """
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))  # tokenize words
    matched_skills = []

    SHORT_VALID_SKILLS = {"c", "r", "go"}  # safely allow these

    for skill in skills_list:
        skill_lower = skill.lower()
        if skill_lower in SHORT_VALID_SKILLS:
            if skill_lower in words:
                matched_skills.append(skill)
        else:
            pattern = r'\b' + re.escape(skill_lower) + r'\b'
            if re.search(pattern, text_lower):
                matched_skills.append(skill)

    return list(set(matched_skills))



def clean_json_string(s: str) -> str:
    s = re.sub(r",\s*([\]}])", r"\1", s)
    s = re.sub(r"[\x00-\x1f]+", "", s)
    return s

def safe_parse_json(response_text, parser=None):
    """
    Safely parse JSON from LLM output (string or dict).
    Handles extra text, multiple objects, or control chars.
    """
    if isinstance(response_text, dict):
        return parser.parse(json.dumps(response_text)) if parser else response_text

    response_text = clean_json_string(str(response_text))

    # Find JSON object
    obj = None
    try:
        # Try to load the whole string
        obj = json.loads(response_text)
    except json.JSONDecodeError:
        # Fallback: find first {...} or [...] block
        start_obj = response_text.find('{')
        end_obj = response_text.rfind('}')
        start_arr = response_text.find('[')
        end_arr = response_text.rfind(']')

        if start_obj != -1 and end_obj != -1 and (start_obj < start_arr or start_arr == -1):
            json_str = response_text[start_obj:end_obj + 1]
        elif start_arr != -1 and end_arr != -1:
            json_str = response_text[start_arr:end_arr + 1]
        else:
            raise OutputParserException("No JSON object or array found in response.")

        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise OutputParserException(f"Could not decode JSON: {e}")

    return parser.parse(json.dumps(obj)) if parser else obj


def extract_experience(text: str) -> str:
    """
    Extracts candidate experience requirement from job description (e.g., "3+ years", "at least 5 years").
    Returns the first match found, else empty string.
    """
    if not text:
        return ""
    match = re.search(r"(\d+\+?\s*(?:year|years|yr|yrs|experience))", text.lower())
    if match:
        return match.group(1)
    return "fresher"

# ------------------ Node Class ------------------ #

class WebSearchChatbotNode:
    """Recruitment pipeline nodes with explicit web search for MCQs & interviews."""

    def __init__(self, llm: GroqLLM):
        self.llm = llm
        self.mcq_parser = PydanticOutputParser(pydantic_object=MCQAssessment)
        self.interview_parser = PydanticOutputParser(pydantic_object=InterviewAssessment)
        self.web_search_tool = WebSearchTool()
        self.interview_search_tool = InterviewWebSearchTool()

    def resume_upload(self, state: CandidateState) -> CandidateState:
        try:
            # Extract raw text from PDF
            resume_raw = extract_text_from_pdf(state.resume_file)
            state.resume_text = resume_raw

            # Clean and tokenize
            state.resume_clean = clean_text(resume_raw)
            state.resume_sentences, state.resume_words = tokenize_text(state.resume_clean)

            # Extract skills using the enhanced skill extractor
            state.candidate_skills = extract_skills(state.resume_text)

            print(f"📄 Resume loaded - {len(state.resume_words)} words, {len(state.resume_sentences)} sentences")
            print(f"🛠 Candidate Skills: {state.candidate_skills}")
        except Exception as e:
            print(f"❌ Resume upload error: {e}")
            state.candidate_skills = []
        return state


# --------- JD Upload ---------
    def jd_upload(self, state: CandidateState) -> CandidateState:
        try:
            jd_raw = state.jd_text or ""
            state.jd_clean = clean_text(jd_raw)
            state.jd_sentences, state.jd_words = tokenize_text(state.jd_clean)

            state.jd_skills = extract_skills(jd_raw)

            state.jd_experience = extract_experience(state.jd_clean)

            print(f"📋 JD processed - {len(state.jd_words)} words, experience: {state.jd_experience or 'fresher'}")
            print(f"🛠 JD Skills: {state.jd_skills}")
        except Exception as e:
            print(f"❌ JD upload error: {e}")
            state.jd_skills = []
            state.jd_experience = "fresher"
        return state


    def match_resume_with_jd(self,state: CandidateState) -> CandidateState:
        try:
            # Vector similarities
            tfidf, bow, emb = vectorize_texts(state.resume_clean, state.jd_clean)

            state.tfidf_score = tfidf
            state.bow_score = bow
            state.embedding_score = emb

            # Extract skills
            state.matched_skills = list(set(state.candidate_skills) & set(state.jd_skills))
            state.missing_skills = list(set(state.jd_skills) - set(state.candidate_skills))

            skill_overlap = len(state.matched_skills) / max(len(state.jd_skills), 1)
            print(state.matched_skills)
            print(state.missing_skills)

            state.match_score = round(
                100 * (
                    0.5 * emb +    # embedding similarity
                    0.3 * tfidf +  # tfidf similarity
                    0.2 * skill_overlap  # skill match
                ),
                2
            )

        except Exception as e:
            state.match_score = 0
            state.matched_skills = []
            state.missing_skills = []
        return state

    def skill_gap_analysis(self, state: CandidateState) -> CandidateState:
        try:
            print(state.missing_skills)
            if not state.missing_skills:
                print("✅ No missing skills. Candidate matches all JD skills.")
                state.skill_resources = {}
                return state

            resources = {}
            for skill in state.missing_skills:
                query = f"Best resources to learn {skill} programming (docs, tutorials, courses)"
                search_results = self.web_search_tool.run(query)

                prompt = f"""
                You are tasked with providing the best learning resources for the skill: {skill}.
                - Suggest 3-5 practical resources (official docs, tutorials, free courses, YouTube).
                - Output should be a JSON list of objects: title, type, url.
                - Resources must be high-quality and relevant for job readiness.

                Web Results:
                {search_results[:800]}...
                """

                response = self.llm.llm.invoke(prompt)
                parsed = safe_parse_json(response.content)
                resources[skill] = parsed

            state.skill_resources = resources
            print(f"📚 Skill Gap Analysis generated for {len(resources)} skills")
        except Exception as e:
            print(f"❌ Skill gap analysis error: {e}")
            state.skill_resources = {}
        return state

    def generate_assessment(self, state: CandidateState) -> CandidateState:
        try:
            if not state.jd_skills:
                print("❌ No JD skills to base assessment on.")
                state.mcqs = []
                return state
            print(state.jd_skills)
            topics = ", ".join(state.jd_skills[:20]) or "general programming"
            query = f"technical MCQs for {topics} with answers and explanations"
            search_results = self.web_search_tool.run(query)

            prompt = f"""
            You are tasked with generating a technical MCQ assessment.
            - Generate exactly 25 high-quality MCQs.
            - Mix: concept checks, applied coding, debugging, optimization.
            - Each MCQ must include: question, 4 options, correct answer, and a brief explanation.
            - Context: Role requires {topics} with {state.jd_experience} experience.
            - Your output MUST be a valid JSON object and nothing else.

            Web Results:
            {search_results[:1000]}...

            {self.mcq_parser.get_format_instructions()}
            """
            response = self.llm.llm.invoke(prompt)
            parsed_data = safe_parse_json(response.content)
            parsed_object = self.mcq_parser.parse(json.dumps(parsed_data))
            state.mcqs = parsed_object.questions
        except Exception as e:
            state.mcqs = []
        return state

    def generate_interview_questions(self, state: CandidateState) -> CandidateState:
        try:
            if not state.jd_skills:
                print("❌ No JD skills to base interview questions on.")
                state.interview_questions = []
                return state
            print(state.jd_skills)
            topics = ", ".join(state.jd_skills[:20]) or "general programming"
            query = f"interview questions for {topics} with behavioral and critical thinking mix"
            search_results = self.interview_search_tool.run(query)

            prompt = f"""
            You are tasked with generating interview questions.
            - Generate exactly 15 questions.
            - Mix: 7 technical, 4 behavioral, 4 critical thinking.
            - Questions should be tailored to both the candidate’s resume and the job description.
            - Focus on practical, scenario-based, and thought-provoking questions.
            - Context: Role requires {topics} with {state.jd_experience} experience.
            - Output MUST be valid JSON and nothing else.

            Web Results:
            {search_results[:1000]}...

            Candidate Resume Snippet: {(state.resume_text or '')[:500]}
            Job Description Snippet: {(state.jd_text or '')[:500]}

            {self.interview_parser.get_format_instructions()}
            """
            response = self.llm.llm.invoke(prompt)
            parsed_data = safe_parse_json(response.content)
            parsed_object = self.interview_parser.parse(json.dumps(parsed_data))
            state.interview_questions = parsed_object.questions
        except Exception as e:
            state.interview_questions = []
        return state
    
    def evaluate_answers(self, state: CandidateState) -> CandidateState:
        try:
            if not state.interview_questions or not state.candidate_answers:
                print("❌ Cannot evaluate. Missing interview questions or candidate answers.")
                state.interview_score = 0.0
                state.feedback = "Missing data for evaluation."
                return state

            questions_with_answers = "\n".join(
                [
                    f"Q: {q.question}\nA: {a}"
                    for q, a in zip(state.interview_questions, state.candidate_answers)
                ]
            )

            prompt = f"""
            You are a senior technical interviewer. Your task is to evaluate a candidate's interview answers.
            Provide a numerical score (0-100) and detailed feedback.

            Candidate's answers to the following questions:
            ---
            {questions_with_answers}
            ---

            Please provide a JSON object with two keys:
            - "score": An integer between 0 and 100 representing the overall performance.
            - "feedback": A comprehensive string providing detailed, constructive feedback. Highlight strengths, weaknesses, and areas for improvement.
            """

            response = self.llm.llm.invoke(prompt)
            parsed_data = safe_parse_json(response.content)
            
            state.interview_score = float(parsed_data.get("score", 0))
            state.feedback = parsed_data.get("feedback", "No feedback provided.")


        except Exception as e:
            state.interview_score = 0.0
            state.feedback = f"Error during evaluation: {e}"

        return state
