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
import httpx
import asyncio


from src.langgraphagenticai.state import state
from src.langgraphagenticai.state.state import CandidateState, MCQAssessment, InterviewAssessment, MCQQuestion
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
    "python", "java", "c", "c++", "c#", "javascript", "typescript", "go", "rust", "ruby", "php", "swift", "kotlin", 
    "scala", "perl", "r", "matlab", "dart", "shell scripting", "bash", "powershell", "lua", "haskell", "elixir",
    
    # Web Development
    "html", "css", "bootstrap", "sass", "less",
    "react", "angular", "vue", "next.js", "nuxt", "ember.js", "jquery", "svelte", "solidjs",
    "node", "express", "django", "flask", "fastapi", "spring", "laravel", "react native", "tailwindcss", "graphql",
    
    # Databases
    "sql", "mysql", "postgresql", "sqlite", "mongodb", "cassandra", "redis", "oracle", "firebase", "dynamodb", 
    "cockroachdb", "timescaledb", "neo4j", "arangodb", "realm",
    
    # Data Science & Analytics
    "numpy", "pandas", "scikit-learn", "matplotlib", "seaborn", "plotly", "tensorflow", "pytorch", "keras", "opencv", 
    "nltk", "spacy", "statsmodels", "mlflow", "xgboost", "lightgbm", "catboost", "shap", "lime", "fastai",
    
    # ML/AI Libraries / LLM & Generative AI Tools
    "transformers", "huggingface", "opencv-contrib", "detectron2", "yolov5", "openai-gym", "stable-baselines3",
    "fasttext", "sentence-transformers", "pytorch lightning",
    "langchain", "langgraph", "llamaindex", "autogpt", "gpt-engineer", "openai api", "cohere", "anthropic", 
    "palm api", "mistral ai", "replit ai", "llmops", "vector databases", "chroma", "weaviate", "pinecone", "qdrant",
    
    # Mobile Development
    "android", "ios", "flutter", "xamarin", "react native", "kotlin multiplatform", "swiftui",
    
    # Cloud & DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible", "ci/cd", "jenkins", "gitlab ci", 
    "circleci", "travis ci", "helm", "prometheus", "grafana", "elk stack", "splunk", "mlops", "serverless", "cloudflare",
    
    # Networking & Security
    "tcp/ip", "udp", "dns", "firewall", "vpn", "wireshark", "penetration testing", "cybersecurity", "network security", 
    "oauth", "jwt", "ssl", "tls", "iptables", "snort", "nmap", "burp suite", "metasploit",
    
    # Scripting & Automation
    "automation", "robot framework", "selenium", "puppeteer", "uipath", "blueprism", "ansible scripts", "powershell scripts",
    
    # API & Integration
    "rest api", "graphql", "soap", "postman", "grpc", "webhooks", "api gateway", "kong", "apigee", "mulesoft",
    
    "linux", "windows", "macos", "unix", "ubuntu", "debian", "fedora", "centos", "redhat",
    
    "git", "github", "gitlab", "jira", "confluence", "trello", "slack", "notion", "excel", "power bi", "tableau", 
    "figma", "canva", "adobe photoshop", "adobe illustrator", "microsoft office", "word", "powerpoint"
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
    """Removes common LLM artifacts and control characters."""
    # 1. Remove trailing commas (common JSON error)
    s = re.sub(r",\s*([\]}])", r"\1", s)
    # 2. Remove control characters
    s = re.sub(r"[\x00-\x1f]+", "", s)
    # 3. Normalize smart quotes that break JSON
    s = (
        s.replace("\u201c", "\"")
        .replace("\u201d", "\"")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    return s

def extract_balanced_json_blocks(text: str) -> list[str]:
    """Extract balanced top-level JSON object/array blocks from text."""
    blocks = []
    stack = []
    in_string = False
    escape = False
    start = None

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "{[":
            if not stack:
                start = i
            stack.append(ch)
            continue

        if ch in "}]":
            if not stack:
                continue
            opener = stack[-1]
            if (opener == "{" and ch == "}") or (opener == "[" and ch == "]"):
                stack.pop()
                if not stack and start is not None:
                    blocks.append(text[start:i + 1])
                    start = None
            else:
                stack = []
                start = None
    return blocks

def normalize_mcq_payload(obj):
    """Normalize known MCQ key variants from LLM output."""
    if isinstance(obj, list):
        return {"questions": obj}
    if not isinstance(obj, dict):
        return obj
    questions = obj.get("questions")
    if isinstance(questions, list):
        for q in questions:
            if isinstance(q, dict) and "answer" not in q and "correct_answer" in q:
                q["answer"] = q["correct_answer"]
    return obj

def extract_llm_text(response) -> str:
    """Extract plain text from LangChain AIMessage-like responses."""
    if response is None:
        return ""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts).strip()
    return str(content).strip()

def build_fallback_mcqs(skills, total=25):
    """Guaranteed-valid fallback MCQs when LLM JSON is malformed."""
    if not skills:
        skills = ["programming"]
    skills = [s for s in skills if s] or ["programming"]

    templates = [
        (
            "Which option best describes the primary use of {skill}?",
            [
                "A. Building and maintaining software solutions",
                "B. Only designing hardware circuits",
                "C. Only managing office spreadsheets",
                "D. Only editing image files"
            ],
            "A",
            "{skill} is primarily used for software development tasks and problem-solving."
        ),
        (
            "In {skill}, what is the best first step when debugging an issue?",
            [
                "A. Remove random lines of code",
                "B. Reproduce the issue consistently and inspect inputs",
                "C. Rename all variables",
                "D. Ignore warnings and retry later"
            ],
            "B",
            "Reliable debugging starts by reproducing the issue and checking inputs/outputs."
        ),
        (
            "Which practice improves code quality in {skill} projects?",
            [
                "A. Writing tests for key logic",
                "B. Avoiding code reviews",
                "C. Keeping undocumented side effects",
                "D. Skipping error handling"
            ],
            "A",
            "Tests help catch regressions and validate behavior over time."
        ),
        (
            "What is a common optimization approach in {skill} code?",
            [
                "A. Increase nested loops without reason",
                "B. Use clearer algorithms and reduce unnecessary work",
                "C. Duplicate logic across files",
                "D. Convert all numbers to strings"
            ],
            "B",
            "Choosing better algorithms and reducing redundant operations usually improves performance."
        ),
        (
            "When handling user input in {skill}, what is recommended?",
            [
                "A. Trust all input without checks",
                "B. Validate and sanitize input before processing",
                "C. Disable error messages entirely",
                "D. Store raw input in executable code"
            ],
            "B",
            "Validation and sanitization reduce bugs and security risks."
        ),
    ]

    out = []
    for i in range(total):
        skill = skills[i % len(skills)]
        t = templates[i % len(templates)]
        out.append(
            MCQQuestion(
                question=t[0].format(skill=skill),
                options=t[1],
                answer=t[2],
                explanation=t[3].format(skill=skill),
            )
        )
    return out

# --- The core safe parsing function ---
def safe_parse_json(response_text, parser=None):
    """
    Safely parse JSON from LLM output (string or dict).
    Handles extra text, thought tags, code fences, and control chars.
    """
    if isinstance(response_text, dict):
        return parser.parse(json.dumps(response_text)) if parser else response_text

    response_text = str(response_text).strip()
    
    # Pre-cleanup: Remove thought traces and code blocks
    response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
    response_text = re.sub(r"```(?:json)?|```", "", response_text)
    
    # Apply JSON-specific cleanup
    response_text = clean_json_string(response_text)

    # 1. Try direct parse first (clean but complete)
    obj = None
    try:
        obj = json.loads(response_text)
    except json.JSONDecodeError:
        # 2. Fallback: parse any balanced JSON block found in mixed text
        blocks = extract_balanced_json_blocks(response_text)
        last_error = None
        for json_str in blocks:
            try:
                obj = json.loads(json_str)
                break
            except json.JSONDecodeError as e:
                last_error = e
        if obj is None and last_error:
            raise OutputParserException(f"Could not decode JSON: {last_error}")

    if obj is None:
        raise OutputParserException("No JSON object or array found in response.")

    obj = normalize_mcq_payload(obj)
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
                    0.5 * emb +   
                    0.3 * tfidf +  
                    0.2 * skill_overlap ,2)

        except Exception as e:
            state.match_score = 0
            state.matched_skills = []
            state.missing_skills = []
        return state




    def skill_gap_analysis(self, state: CandidateState) -> CandidateState:

        try:
            print("🧠 Missing Skills:", state.missing_skills)
            if not state.missing_skills:
                print("✅ No missing skills. Candidate matches all JD skills.")
                state.skill_resources = {}
                return state

            resources = {}

            def fix_url(url: str) -> str:
                """Fix common short links and ensure HTTPS prefix."""
                if not url:
                    return ""
                url = url.strip()
                if not re.match(r"^https?://", url):
                    url = "https://" + url
                if "youtu.be" in url and "watch?v=" not in url:
                    # Robustly handle youtu.be/xxx to full youtube.com/watch?v=xxx
                    vid = url.split("/")[-1].split("?")[0]
                    url = f"https://www.youtube.com/watch?v={vid}"
                return url

            def classify_url(url: str) -> str:
                """Classify resource type based on URL/domain."""
                url_lower = url.lower()
                if any(k in url_lower for k in ["youtube.com", "youtu.be"]):
                    return "video"
                elif any(k in url_lower for k in ["coursera.org", "edx.org", "udemy.com", "kaggle.com", "freecodecamp.org", "scrimba.com"]):
                    return "course"
                else:
                    return "article"

            def extract_link_metadata(raw_result):
                """Extract URLs, titles, and label from raw search output."""
                labeled_resources = []
                
                # Check if the raw result is a list of structured objects (assuming tool output format)
                if isinstance(raw_result, list):
                    search_items = raw_result
                else:
                    # Fallback to simple regex if tool output is raw text/HTML
                    urls = re.findall(r"https?://[^\s\"'>)]+", str(raw_result))
                    search_items = [{"url": url, "title": url.split("/")[-1].replace('-', ' ').title()} for url in urls]

                # Process the first 10 items to give the LLM enough to rank
                for item in search_items[:10]:
                    url = item.get("url")
                    title = item.get("title", "Untitled Resource")
                    if url:
                        url_fixed = fix_url(url)
                        # Filter for unique URLs after fixing
                        if url_fixed not in [r['url'] for r in labeled_resources]:
                            labeled_resources.append({
                                "title": title,
                                "url": url_fixed,
                                "type": classify_url(url_fixed)
                            })
                return labeled_resources

            for skill in state.missing_skills:
                print(f"\n🔍 Processing skill: {skill}")
                query = (
                        f"Top high-quality free learning resources for {skill} programming: "
                        f"official documentation, interactive tutorials, YouTube playlists, blogs, GitHub repositories, "
                        f"beginner-friendly courses, and learning roadmaps."
                    ) 

                search_results = self.web_search_tool.run(query)
                print(f"🌐 Raw search output for {skill} (first 300 chars):\n{str(search_results)[:300]}")

                extracted = extract_link_metadata(search_results)
                
                if not extracted:
                    print(f"⚠️ No links extracted for {skill}")
                    resources[skill] = []
                    continue

                # --- LLM Ranking and Naming ---
                ranked = extracted
                try:
                    urls_text = "\n".join([f"- Title: {r['title']} (Type: {r['type']}, URL: {r['url']})" for r in extracted])
                    prompt = f"""
                    You are an expert AI mentor.
                    From the following list of learning resources for **{skill}**, 
                    choose the top **5** that are most practical, high-quality, and beginner-friendly.
                    For each chosen resource, give it a concise and professional **title** that clearly describes the resource (e.g., "Official Keras Documentation" or "PyTorch Fundamentals Video Course").

                    Return a valid JSON array of objects, ensuring no text precedes or follows the array.
                    Each object must have three keys: "title" (your generated name), "type", and "url".

                    Resources for {skill}:
                    {urls_text}
                    """
                    
                    response = self.llm.llm.invoke(prompt)
                    raw = (response.content or "").strip()
                    
                    # Use the robust safe_parse_json utility
                    parsed_data = safe_parse_json(raw)
                    
                    # Ensure the parsed data is a list of dictionaries
                    if isinstance(parsed_data, dict):
                        ranked = [parsed_data]
                    elif isinstance(parsed_data, list):
                        ranked = parsed_data
                    else:
                        raise ValueError("LLM did not return a valid list or object.")
                        
                except Exception as e:
                    print(f"⚠️ LLM ranking/naming error for {skill}: {e}. Keeping default top 5.")
                    ranked = extracted[:5]

                # Filter the LLM output to match the expected structure and limit to top 5
                final_resources = []
                for item in ranked:
                    if isinstance(item, dict) and all(key in item for key in ["title", "type", "url"]):
                        final_resources.append({
                            "title": item["title"],
                            "type": item["type"],
                            "url": item["url"]
                        })
                
                resources[skill] = final_resources[:5]

            state.skill_resources = resources
            print(f"\n📚 Skill gap analysis completed for {len(resources)} skills")

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

            print(f"🧩 JD Skills ({len(state.jd_skills)}): {state.jd_skills}")

            # ---- Aggregate web results for all topics ----
            all_results = ""
            for skill in state.jd_skills:  # limit to 20 to avoid overload
                query = f"technical MCQs for {skill} with answers and explanations"
                print(f"🌐 Searching MCQs for: {skill}")
                try:
                    result = self.web_search_tool.run(query)
                    print(f"🔎 {skill}: {len(result)} chars")
                    all_results += f"\n### {skill}\n{result[:1000]}\n"
                except Exception as e:
                    print(f"⚠️ Error fetching for {skill}: {e}")

            prompt = f"""
            You are tasked with generating a technical MCQ assessment.

            - Generate **exactly 25** high-quality MCQs.
            - Mix: concept checks, applied coding, debugging, optimization.
            - Each MCQ must include: "question", "options" (A-D), "correct_answer", "explanation".
            - Context: Role requires skills in {', '.join(state.jd_skills[:20])}
            with {state.jd_experience} experience.
            - Output MUST be a **valid JSON object** and nothing else.

            Web Results (aggregated from all topics):
            {all_results[:4000]}...

            {self.mcq_parser.get_format_instructions()}
            """

            response = self.llm.llm.invoke(prompt)
            raw = str(getattr(response, "content", response) or "").strip()
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            print(f"🔎 MCQ raw response length: {len(raw)}")
            try:
                parsed_data = safe_parse_json(raw)
            except Exception as parse_err:
                print(f"⚠️ JSON parse failed for MCQs: {parse_err}. Using fallback MCQs.")
                state.mcqs = build_fallback_mcqs(state.jd_skills, 25)
                print(f"✅ Generated {len(state.mcqs)} fallback MCQs.")
                return state
            if isinstance(parsed_data, list):
                parsed_data = {"questions": parsed_data}

            questions_raw = parsed_data.get("questions", []) if isinstance(parsed_data, dict) else []
            valid_mcqs = []
            for i, q in enumerate(questions_raw):
                if not isinstance(q, dict):
                    continue
                if "answer" not in q and "correct_answer" in q:
                    q["answer"] = q["correct_answer"]

                options = q.get("options", [])
                if not isinstance(options, list) or len(options) < 4:
                    print(f"⚠️ Skipping malformed MCQ at index {i}: invalid options")
                    continue

                q["options"] = [str(opt).strip() for opt in options[:4]]

                try:
                    mcq = MCQQuestion(
                        question=str(q.get("question", "")).strip(),
                        options=q["options"],
                        answer=str(q.get("answer", "")).strip(),
                        explanation=str(q.get("explanation", "")).strip(),
                    )
                except Exception as ve:
                    print(f"⚠️ Skipping malformed MCQ at index {i}: {ve}")
                    continue

                if not mcq.question or not mcq.answer or not mcq.explanation:
                    print(f"⚠️ Skipping malformed MCQ at index {i}: missing text fields")
                    continue

                valid_mcqs.append(mcq)

            if not valid_mcqs:
                raise OutputParserException("No valid MCQs found in model response.")
            
            # ---- Convert correct answer text to single letter A-D ----
            for mcq in valid_mcqs:
                found = False
                
                # Normalize the expected answer text from the LLM
                llm_answer = re.sub(r"^[A-D][\.\)]\s*", "", mcq.answer.strip(), flags=re.IGNORECASE).lower()

                for idx, opt in enumerate(mcq.options):
                    # Normalize the option text
                    clean_opt = re.sub(r"^[A-D][\.\)]\s*", "", opt.strip(), flags=re.IGNORECASE).lower()

                    if llm_answer == clean_opt:
                        mcq.answer = chr(idx + 65)  # 'A'..'D'
                        found = True
                        break

                if not found:
                    # Fallback if no text match, try to check if the LLM provided the letter directly
                    llm_answer_upper = mcq.answer.strip().upper()
                    if len(llm_answer_upper) == 1 and llm_answer_upper in "ABCD":
                         mcq.answer = llm_answer_upper
                         found = True
                    else:
                         # Default to 'A' and print warning
                         mcq.answer = "A"
                         print(f"⚠️ Correct answer text/letter '{mcq.answer}' not found in options, defaulted to 'A'")

            state.mcqs = valid_mcqs[:25]
            print(f"✅ Generated {len(state.mcqs)} MCQs successfully.")

        except Exception as e:
            print(f"❌ Error generating MCQs: {e}")
            state.mcqs = []

        return state




    def generate_interview_questions(self, state: CandidateState) -> CandidateState:
        """
        Generate interview questions (technical, behavioral, critical thinking).
        Searches web for each JD skill and aggregates context.
        """
        try:
            if not state.jd_skills:
                print("❌ No JD skills to base interview questions on.")
                state.interview_questions = []
                return state

            print(f"🎯 JD Skills ({len(state.jd_skills)}): {state.jd_skills}")

            # ---- Aggregate search results ----
            all_results = ""
            for skill in state.jd_skills[:20]:
                query = f"interview questions for {skill} (technical, behavioral, critical thinking)"
                print(f"🌐 Searching Interview Questions for: {skill}")
                try:
                    result = self.interview_search_tool.run(query)
                    print(f"🔎 {skill}: {len(result)} chars")
                    all_results += f"\n### {skill}\n{result[:1000]}\n"
                except Exception as e:
                    print(f"⚠️ Error fetching for {skill}: {e}")

            prompt = f"""
            You are tasked with generating interview questions.

            - Generate **exactly 15** questions.
            - Mix: 7 technical, 4 behavioral, 4 critical thinking.
            - Questions should be tailored to both the candidate’s resume and the job description.
            - Focus on practical, scenario-based, and thought-provoking questions.
            - Context: Role requires {', '.join(state.jd_skills[:20])}
            with {state.jd_experience} experience.
            - Output MUST be valid JSON and nothing else.

            Web Results (aggregated from all topics):
            {all_results[:4000]}...

            Candidate Resume Snippet:
            {(state.resume_text or '')[:500]}

            Job Description Snippet:
            {(state.jd_text or '')[:500]}

            {self.interview_parser.get_format_instructions()}
            """

            response = self.llm.llm.invoke(prompt)
            parsed_data = safe_parse_json(response.content)
            parsed_object = self.interview_parser.parse(json.dumps(parsed_data))
            state.interview_questions = parsed_object.questions

            print(f"✅ Generated {len(state.interview_questions)} interview questions.")

        except Exception as e:
            print(f"❌ Error generating interview questions: {e}")
            state.interview_questions = []

        return state
    
    def evaluate_answers(self, state: CandidateState) -> CandidateState:
        """
        Evaluate each interview answer individually using the LLM.
        Returns structured per-question feedback (no overall score).
        """
        try:
            if not state.interview_questions or not state.candidate_answers:
                print("❌ Cannot evaluate. Missing interview questions or candidate answers.")
                state.feedback = []
                return state

            # Prepare questions and answers
            questions_data = []
            for i, question_obj in enumerate(state.interview_questions):
                answer = state.candidate_answers[i] if i < len(state.candidate_answers) else "NO_ANSWER_PROVIDED"
                questions_data.append(
                    f"Q{i+1} ({question_obj.type}): {question_obj.question}\n"
                    f"Candidate Answer: {answer}\n---"
                )

            questions_with_answers = "\n".join(questions_data)

            prompt = f"""
            You are an experienced technical interviewer. 
            Review each question and the candidate's answer.
            Provide constructive textual feedback for every question.

            Candidate's interview session:
            ---
            {questions_with_answers}
            ---

            CRITICAL INSTRUCTION: Your output MUST be ONLY the valid JSON array and nothing else.
            Return only a valid JSON array of objects, ensuring no text precedes or follows the array:
            [
            {{ "question_index": 1, "review_feedback": "Concise and correct explanation." }},
            {{ "question_index": 2, "review_feedback": "Missed mentioning time complexity." }}
            ]
            """

            response = self.llm.llm.invoke(prompt)
            raw = str(getattr(response, "content", response) or "").strip()
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            parsed_feedback = safe_parse_json(raw)

            # Normalize shapes:
            # 1) expected: [ {...}, {...} ]
            # 2) common variant: { "questions": [ {...}, {...} ] }
            if isinstance(parsed_feedback, dict) and isinstance(parsed_feedback.get("questions"), list):
                parsed_feedback = parsed_feedback["questions"]
            elif isinstance(parsed_feedback, dict) and isinstance(parsed_feedback.get("feedback"), list):
                parsed_feedback = parsed_feedback["feedback"]
            elif not isinstance(parsed_feedback, list):
                parsed_feedback = [{"question_index": 1, "review_feedback": str(parsed_feedback)}]

            # Ensure one feedback item per interview question index
            normalized_feedback = []
            by_index = {}
            for item in parsed_feedback:
                if not isinstance(item, dict):
                    continue
                idx = item.get("question_index")
                text = item.get("review_feedback")
                if isinstance(idx, int) and idx >= 1 and isinstance(text, str) and text.strip():
                    by_index[idx] = text.strip()

            total_questions = len(state.interview_questions or [])
            for idx in range(1, total_questions + 1):
                answer_text = state.candidate_answers[idx - 1] if idx - 1 < len(state.candidate_answers) else "NO_ANSWER_PROVIDED"
                default_text = "No answer provided." if answer_text in ["NO_ANSWER_PROVIDED", "", None] else "No specific AI feedback generated for this question."
                normalized_feedback.append({
                    "question_index": idx,
                    "review_feedback": by_index.get(idx, default_text)
                })

            state.feedback = json.dumps(normalized_feedback)

            return state

        except Exception as e:
            print(f"❌ Evaluation failed: {e}")
            # --- FIX: Ensure error case is also a valid string representation of the list ---
            error_feedback = [{"question_index": 0, "review_feedback": f"Error during evaluation: {e}"}]
            state.feedback = json.dumps(error_feedback)
            return state
