"""
AI Helper – Groq integration for resume parsing & question answering.
Optimized for Llama-3.3-70b-versatile.
"""
import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

# Load variables directly from the .env file
load_dotenv()

def _get_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[AI FATAL ERROR] No Groq API Key found! Check your .env file.")
    return Groq(api_key=api_key)

def parse_resume_with_ai(resume_text: str) -> dict:
    prompt = f"""
You are an expert resume parser and career counsellor.
Analyse the following resume text carefully and extract the details below.
Return ONLY a valid JSON object — no markdown fences, no extra text.

EXTRACTION RULES:
1. BRANCH: Factor out the specialization (e.g. AIML, CSE, Marketing) into the "branch" field. 
2. DATES: If only "Expected Graduation: 2027" is given, calculate the start year (From: 2023, To: 2027) assuming a 4-year degree (B.Tech).
3. Always extract the College name into the "institution" field.

Schema:
{{
  "name": "<Full name>",
  "email": "<Email>",
  "phone": "<Phone>",
  "location": "<Location>",
  "education_list": [
    {{
      "degree": "<Degree>",
      "branch": "<Branch>",
      "institution": "<College>",
      "year": "<Full graduation text>",
      "year_from": "<Start Year>",
      "year_to": "<End Year>"
    }}
  ],
  "experience": [
    {{
      "company": "<Company>",
      "role": "<Title>",
      "duration": "<Duration>"
    }}
  ],
  "projects": [
    {{
      "name": "<Title>",
      "description": "<Description>"
    }}
  ],
  "certifications": ["<Cert 1>", "<Cert 2>"],
  "links": {{
    "github": "<URL>",
    "linkedin": "<URL>",
    "portfolio": "<URL>"
  }},
  "summary": "<Summary>",
  "suggested_role": "<Best fit role>",
  "total_experience_years": "<Total years as a number>"
}}

Resume Text:
\"\"\"
{resume_text[:6000]}
\"\"\"
"""
    try:
        client = _get_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a JSON-only API. You must strictly output valid JSON and nothing else."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0,
            response_format={"type": "json_object"},
        )
        
        raw = chat_completion.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match: raw = match.group(0)
            
        data = json.loads(raw)
        return {
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "location": data.get("location", ""),
            "education_list": data.get("education_list", []),
            "experience_list": data.get("experience", []),
            "projects_list": data.get("projects", []),
            "certifications_list": data.get("certifications", []),
            "links": data.get("links", {}),
            "summary": data.get("summary", ""),
            "suggested_role": data.get("suggested_role", ""),
            "total_experience_years": data.get("total_experience_years", "0"),
        }
    except Exception as e:
        print(f"[AI] parse_resume_with_ai error: {e}")
        return {
            "name": f"CRASH: {str(e)}",
            "email": "Check API Key",
            "suggested_role": "Software Engineer",
        }

def answer_screening_question(question: str, resume_text: str) -> str:
    prompt = f"""
Below is the applicant's exact resume:
\"\"\"
{resume_text[:4000]}
\"\"\"

Answer the recruiter question below based STRICTLY on the resume text provided.

CRITICAL RULES FOR DATES & STATUS:
1. "COMPANY/EMPLOYER": Respond ONLY with the organization name (e.g. "Google"). No sentences.
2. "CURRENTLY WORKING": Look at Experience. If every job has a specific start/end date (e.g. Mar 2025 - Apr 2025), answer NO. 
3. Only answer "Yes" to currently working if a job specifically says "Present" or "Current".
4. GRADUATION: Graduation 2027 is FUTURE. If asked if graduated/completed, answer NO.
5. EXPERIENCE: count ONLY duration. Internships 2025 = 0 years. Return "0".
6. SKILL ABSENT: If the question asks for experience in a skill (e.g., "Kafka", "Java") NOT mentioned in the resume or skills section, respond with "0".
7. NO units (years), NO "Based on...", NO sentences.

Question: {question}

Answer:"""
    try:
        client = _get_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a factual job application assistant. You do not assume. If a job has an end date, it is finished. If graduation is 2027, they haven't graduated."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0, 
        )
        
        answer = chat_completion.choices[0].message.content.strip().strip('"').strip("'")
        return answer
    except Exception as e:
        print(f"[AI] answer_screening_question error: {e}")
        return ""