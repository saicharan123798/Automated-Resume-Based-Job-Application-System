import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "autojob-super-secret-key-change-in-prod")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "autojob.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Google Gemini API Key — set via environment variable
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

    # LinkedIn credentials stored per-user (entered on preferences page)
    # Not stored globally here; stored encrypted in DB per user.

    # Bot thresholds
    COSINE_THRESHOLD = 0.15
    MAX_JOBS_SCAN = 100
    MAX_JOBS_APPLY = 20
