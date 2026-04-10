
import os
import json
from ai_helper import parse_resume_with_ai

resume_text = """
Kande Manikanta
kandemani07@gmail.com | +91 8977280200

EXPERIENCE
Code Alpha | Machine Learning Intern
May 2025 – Jun 2025 (Remote)
• Implemented supervised and unsupervised ML algorithms on real-world datasets.
• Built predictive models and visualized insights using Python and libraries like Pandas, NumPy, and Matplotlib.

Code Alpha | Python Programming Intern
Mar 2025 – Apr 2025 (Remote)
• Developed multiple Python mini-projects focusing on automation and data processing.
• Strengthened knowledge in OOP, file handling, and debugging techniques.

PROJECTS
Job Portal App (Flutter)
• Designed and developed a cross-platform job search application using Flutter and Firebase.
• Implemented user authentication, job listings, and responsive UI for Android and Web.

Volume Control using Hand Gestures
• Created a computer vision project using OpenCV, Mediapipe, and Pycaw to adjust system volume through hand gestures.
• Integrated real-time hand landmark detection and gesture mapping.

EDUCATION
Spoorthy Engineering College, Hyderabad
Bachelor of Technology in Artificial Intelligence & Machine Learning (AIML)
Expected Graduation: 2027

POSITIONS & CERTIFICATIONS
Editor — AI Fusion Club, Spoorthy Engineering College
• Manage and edit technical content related to AI, ML, and data science initiatives.
Certifications:
• Data Analytics Job Simulation — Deloitte
• AWS Cloud Foundations — Amazon Web Services

SKILLS
Programming Languages: C, Python, Java
Frameworks & Tools: Flutter, OpenCV, Mediapipe, Firebase
Other Skills: Machine Learning, Data Analysis, Problem Solving, Git/GitHub

LINKS
GitHub: https://share.google/iPij38Kf1YsatfjYi
LinkedIn: https://www.linkedin.com/in/manikanta-kande-575a38308
Portfolio: https://lovable.dev/projects/e0b29308-6067-4966-ac41-02922c7b5bbe
"""

print("Running AI Parser Test...")
parsed = parse_resume_with_ai(resume_text)
print(json.dumps(parsed, indent=2))
