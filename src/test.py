import argparse
import json
import numpy as np
from src.langgraphagenticai.graph.graph_builder import GraphBuilder
from src.langgraphagenticai.state.state import CandidateState

def run_workflow(resume_path, jd_path, save_json=False, json_output_path="output.json"):
    """
    Runs the recruitment assistant workflow (sequential flow, no thresholds).
    """
    graph_builder = GraphBuilder(model_name="qwen/qwen3-32b")
    
    # 1. Resume-JD Screening
    screening_graph = graph_builder.build_screening_graph()
    initial_state = CandidateState(resume_file=resume_path, jd_file_path=jd_path)
    screened_state = screening_graph.invoke(initial_state) or {}

    # 2. Technical MCQ Generation (always executed)
    assessment_graph = graph_builder.build_assessment_graph()
    try:
        assessment_state_update = assessment_graph.invoke(screened_state) or {}
        screened_state.update({"mcqs": assessment_state_update.get("questions", [])})
    except Exception as e:
        print(f"❌ Error in MCQ generation: {e}")
        screened_state.update({"mcqs": []})

    # 3. Interview Question Generation (always executed)
    interview_graph = graph_builder.build_interview_graph()
    try:
        interview_state_update = interview_graph.invoke(screened_state) or {}
        screened_state.update({"interview_questions": interview_state_update.get("questions", [])})
    except Exception as e:
        print(f"❌ Error in interview question generation: {e}")
        screened_state.update({"interview_questions": []})

    # Convert final state into CandidateState object safely
    final_state_pydantic = CandidateState(**screened_state)
    
    # Print results
    print_results(final_state_pydantic)

    # Save JSON if requested
    if save_json:
        state_dict = final_state_pydantic.model_dump()

        # Convert numpy arrays or non-serializable objects
        for key, value in state_dict.items():
            if isinstance(value, np.ndarray):
                state_dict[key] = value.tolist()

        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Results saved to {json_output_path}")

def print_results(state: CandidateState):
    """
    Nicely print results from CandidateState.
    """
    print("\n=== RECRUITMENT ASSISTANT RESULTS ===")

    # Resume text
    if getattr(state, "resume_text", None):
        print("\n📄 Resume Extracted Text:\n")
        print(state.resume_text[:500], "..." if len(state.resume_text) > 500 else "")

    # Job description text
    if getattr(state, "jd_text", None):
        print("\n📋 Job Description Extracted Text:\n")
        print(state.jd_text[:500], "..." if len(state.jd_text) > 500 else "")

    # Resume-JD matching results
    if getattr(state, "match_score", None) is not None:
        print("\n🤝 Resume-JD Matching Results:\n")
        print(f"Match Score: {state.match_score:.2f}%")
        print(f"TF-IDF Score: {getattr(state, 'tfidf_score', 0):.4f}")
        print(f"BoW Score: {getattr(state, 'bow_score', 0):.4f}")
        print(f"Embedding Score: {getattr(state, 'embedding_score', 0):.4f}")
        print(f"Matched Skills: {getattr(state, 'matched_skills', [])}")
        print(f"Missing Skills: {getattr(state, 'missing_skills', [])}")

    # MCQs
    if getattr(state, "mcqs", None):
        print("\n📝 TECHNICAL ASSESSMENT (MCQs):\n")
        for i, q in enumerate(state.mcqs):
            try:
                print(f"Question {i+1}: {q.question}")
                for option in q.options:
                    print(f" - {option}")
                print(f"Correct Answer: {q.answer}")
                print(f"Explanation: {q.explanation}\n")
            except Exception:
                print(f"⚠️ Malformed MCQ: {q}\n")

    # Interview questions
    if getattr(state, "interview_questions", None):
        print("\n🎤 INTERVIEW QUESTIONS:\n")
        for q in state.interview_questions:
            try:
                print(f"Type: {q.type.capitalize() if getattr(q, 'type', None) else 'General'}")
                print(f"Question: {q.question}\n")
            except Exception:
                print(f"⚠️ Malformed interview question: {q}\n")

def main():
    parser = argparse.ArgumentParser(description="Recruitment Assistant Workflow")
    parser.add_argument("resume", type=str, help="Path to resume PDF file")
    parser.add_argument("jd", type=str, help="Path to job description TXT file")
    parser.add_argument("--save-json", action="store_true", help="Save output to JSON file")
    parser.add_argument("--json-output-path", type=str, default="output.json", help="Path for saving JSON output")
    args = parser.parse_args()

    run_workflow(args.resume, args.jd, save_json=args.save_json, json_output_path=args.json_output_path)

if __name__ == "__main__":
    main()
