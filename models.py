from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    # Resume
    resume_pdf_path = db.Column(db.String(512), nullable=True)
    resume_text = db.Column(db.Text, nullable=True)

    # AI parsed data
    parsed_first_name = db.Column(db.String(100), nullable=True)
    parsed_last_name = db.Column(db.String(100), nullable=True)
    parsed_name = db.Column(db.String(200), nullable=True)
    parsed_email = db.Column(db.String(200), nullable=True)
    parsed_phone = db.Column(db.String(50), nullable=True)
    parsed_location = db.Column(db.String(200), nullable=True)
    parsed_skills = db.Column(db.Text, nullable=True)
    parsed_education = db.Column(db.Text, nullable=True)
    parsed_education_list = db.Column(db.Text, nullable=True)  # JSON array
    parsed_experience_list = db.Column(db.Text, nullable=True)   # JSON array
    parsed_projects_list = db.Column(db.Text, nullable=True)     # JSON array
    parsed_certifications_list = db.Column(db.Text, nullable=True) # JSON array
    parsed_links = db.Column(db.Text, nullable=True)           # JSON object
    parsed_summary = db.Column(db.Text, nullable=True)
    suggested_role = db.Column(db.String(200), nullable=True)

    # Job preferences
    desired_role = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    min_salary = db.Column(db.String(100), nullable=True)
    job_type = db.Column(db.String(100), nullable=True)  # Full-time, Part-time, Remote, etc.

    # LinkedIn credentials (stored plaintext for simplicity; encrypt in production)
    linkedin_email = db.Column(db.String(200), nullable=True)
    linkedin_password = db.Column(db.String(200), nullable=True)

    # Bot stats
    total_applied = db.Column(db.Integer, default=0)
    total_skipped = db.Column(db.Integer, default=0)
    total_scanned = db.Column(db.Integer, default=0)
    last_run_date = db.Column(db.DateTime, nullable=True)

    # Bot status for live tracking
    bot_running = db.Column(db.Boolean, default=False)
    bot_status_message = db.Column(db.String(500), nullable=True)

    # Relationships
    applications = db.relationship("Application", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


class Application(db.Model):
    __tablename__ = "applications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    company = db.Column(db.String(300), nullable=True)
    job_title = db.Column(db.String(300), nullable=True)
    job_url = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="applied")  # applied | skipped | error
    similarity_score = db.Column(db.Float, nullable=True)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "company": self.company or "N/A",
            "job_title": self.job_title or "N/A",
            "job_url": self.job_url or "",
            "status": self.status,
            "similarity_score": round(self.similarity_score, 3) if self.similarity_score else None,
            "applied_at": self.applied_at.strftime("%Y-%m-%d %H:%M") if self.applied_at else "",
        }

class UserAdditionalInfo(db.Model):
    __tablename__ = "user_additional_info"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    user_type = db.Column(db.String(20), nullable=True)  # "fresher" or "experienced"

    # Common / Experienced fields
    total_experience = db.Column(db.String(50), nullable=True)
    relevant_experience = db.Column(db.String(50), nullable=True)
    experience_python = db.Column(db.String(50), nullable=True)
    experience_sql = db.Column(db.String(50), nullable=True)
    experience_aws = db.Column(db.String(50), nullable=True)
    experience_tensorflow = db.Column(db.String(50), nullable=True)
    experience_databases = db.Column(db.String(50), nullable=True)

    current_ctc = db.Column(db.String(50), nullable=True)
    expected_ctc = db.Column(db.String(50), nullable=True)
    notice_period = db.Column(db.String(50), nullable=True)
    serving_notice = db.Column(db.String(20), nullable=True)  # "Yes" / "No"
    current_company = db.Column(db.String(200), nullable=True)

    # Common / Fresher fields
    internship_experience = db.Column(db.String(50), nullable=True)
    skills = db.Column(db.Text, nullable=True)
    preferred_role = db.Column(db.String(200), nullable=True)
    preferred_location = db.Column(db.String(200), nullable=True)
    relocate = db.Column(db.String(20), nullable=True)  # "Yes" / "No"
    remote = db.Column(db.String(20), nullable=True)    # "Yes" / "No"
    onsite = db.Column(db.String(20), nullable=True)    # "Yes" / "No"
    immediate_join = db.Column(db.String(20), nullable=True) # "Yes" / "No"
    
    # Address details
    street_address = db.Column(db.String(300), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True, default="India")

    # Relationship back to User
    user = db.relationship("User", backref=db.backref("additional_info", uselist=False))

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
