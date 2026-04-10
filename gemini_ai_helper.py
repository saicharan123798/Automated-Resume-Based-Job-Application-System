"""
AI Helper – Google Gemini integration for resume parsing & question answering.
"""
import re
import os
import google.generativeai as genai

def _get_api_key():
    # 1. Try Flask config first (Works perfectly for the Resume Upload screen)
    try:
        from flask import current_app
        if current_app:
            key = current_app.config.get("GEMINI_API_KEY")
            if key: return key
    except:
        pass
    
    # 2. Try OS Environment variables (Works perfectly for the background Bot)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass
    return os.environ.get("GEMINI_API_KEY", "")

def _get_model():
    api_key = _get_api_key()
    if not api_key:
        print("[AI FATAL ERROR] No Gemini API Key found!")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

def parse_resume_with_ai(resume_text: str) -> dict:
    prompt = f"""
You are an expert resume parser and career counsellor.
Analyse the following resume text carefully and extract the details below.
Return ONLY a valid JSON object — no markdown fences, no extra text.

Schema:
{{
  "name": "<Full name of candidate>",
  "email": "<Email address>",
  "skills": "<Comma-separated list of all technical and soft skills>",
  "education": "<Highest degree and institution>",
  "suggested_role": "<Single best-fit job role title for this candidate>"
}}

Resume Text:
\"\"\"
{resume_text[:6000]}
\"\"\"
"""
    try:
        model = _get_model()
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        raw = response.text.strip()
        
        # Aggressive JSON isolation
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match: raw = match.group(0)
            
        import json
        data = json.loads(raw)
        return {
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "skills": data.get("skills", ""),
            "education": data.get("education", ""),
            "suggested_role": data.get("suggested_role", ""),
        }
    except Exception as e:
        print(f"[AI] parse_resume_with_ai error: {e}")
        return {
            "name": f"CRASH: {str(e)}",
            "email": "Check API Key",
            "skills": "Error Parsing",
            "education": "Error Parsing",
            "suggested_role": "Software Engineer",
        }

def answer_screening_question(question: str, resume_text: str) -> str:
    prompt = f"""
You are an AI assistant filling out a job application.
Below is the applicant's exact resume:
\"\"\"
{resume_text[:4000]}
\"\"\"

Answer the recruiter question below based STRICTLY on the resume text provided.

CRITICAL RULES:
1. If the question asks for "years", "how many", or "experience", return ONLY a single digit integer (e.g., 2, 5, 0). Do not write the word 'years'.
2. If the question asks for a "city", "state", "country", or "location", find the location in the resume and return ONLY the location name.
3. If it is a Yes/No question, return ONLY Yes or No.
4. Keep the answer as short as possible. Do not explain your reasoning.

Question: {question}

Answer:"""
    try:
        model = _get_model()
        response = model.generate_content(prompt)
        answer = response.text.strip().strip('"').strip("'")
        return answer
    except Exception as e:
        print(f"[AI] answer_screening_question error: {e}")
        return ""