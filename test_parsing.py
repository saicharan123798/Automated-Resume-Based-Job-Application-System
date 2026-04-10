import os
import json
from ai_helper import parse_resume_with_ai
from dotenv import load_dotenv

load_dotenv()

sample_resume = """
John Doe
Email: john.doe@example.com
Phone: +1-555-010-999
Location: San Francisco, CA

Professional Summary:
Result-oriented Software Engineer with 5 years of experience in building scalable web applications.

Experience:
Senior Software Engineer | TechCorp | Jan 2021 - Present
- Led a team of 5 developers to rebuild the core API.
- Improved system performance by 40%.

Software Engineer | StartUpInc | June 2018 - Dec 2020
- Developed frontend components using React.

Projects:
- Portfolio Website: A personal showcase built with Next.js and Tailwind CSS.
- E-commerce Engine: A microservices-based platform for online retail.

Education:
Master of Science in Computer Science | Stanford University | 2018
Bachelor of Engineering in IT | MIT | 2016

Certifications:
- AWS Certified Solutions Architect
- Google Cloud Professional Developer

Links:
GitHub: https://github.com/johndoe
LinkedIn: https://linkedin.com/in/johndoe
Portfolio: https://johndoe.com
"""

print("--- Testing AI Parsing ---")
parsed = parse_resume_with_ai(sample_resume)
print(json.dumps(parsed, indent=2))

if parsed.get("phone") and parsed.get("experience_list"):
    print("\nSUCCESS: Data extracted correctly.")
else:
    print("\nFAILURE: Some fields might be missing.")
