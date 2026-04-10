"""
app.py – Main Flask application for AutoJob.
"""

import os
import threading
import json
from datetime import datetime

from flask import (
    Flask, render_template, redirect, url_for, request,
    flash, jsonify, session,
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user,
)
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Application

# ─── PDF text extraction ───────────────────────────────────────────────────
from pdfminer.high_level import extract_text as pdf_extract_text

# ──────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.template_filter("from_json")
def from_json_filter(value):
    try:
        return json.loads(value) if value else {}
    except:
        return {}


# ──────────────────────────────────────────────
# Allowed file types
# ──────────────────────────────────────────────
ALLOWED_EXTENSIONS = {"pdf"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────────
# Routes – Auth
# ──────────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username already taken.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash("Invalid username/email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ──────────────────────────────────────────────
# Routes – Dashboard
# ──────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    applications = Application.query.filter_by(user_id=current_user.id)\
        .order_by(Application.applied_at.desc()).limit(50).all()
    
    # Calculate database totals
    applied_count = Application.query.filter_by(user_id=current_user.id, status="applied").count()
    already_applied_count = Application.query.filter_by(user_id=current_user.id, status="already_applied").count()
    skipped_count = Application.query.filter_by(user_id=current_user.id, status="skipped").count()
    failed_count = Application.query.filter_by(user_id=current_user.id, status="failed").count()

    return render_template("dashboard.html", 
                           user=current_user, 
                           applications=applications,
                           applied_count=applied_count,
                           already_applied_count=already_applied_count,
                           skipped_count=skipped_count,
                           failed_count=failed_count)


# ──────────────────────────────────────────────
# Routes – Resume Upload
# ──────────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload_resume():
    if request.method == "POST":
        if "resume" not in request.files:
            flash("No file part in the request.", "error")
            return redirect(request.url)

        file = request.files["resume"]
        if file.filename == "":
            flash("No file selected.", "error")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Only PDF files are allowed.", "error")
            return redirect(request.url)

        # Save PDF
        filename = secure_filename(f"user_{current_user.id}_resume.pdf")
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Extract text
        try:
            resume_text = pdf_extract_text(filepath)
        except Exception as e:
            flash(f"Could not extract text from PDF: {e}", "error")
            return redirect(request.url)

        # Store in DB
        current_user.resume_pdf_path = filepath
        current_user.resume_text = resume_text
        db.session.commit()

        # AI parsing
        try:
            from ai_helper import parse_resume_with_ai
            import json
            parsed = parse_resume_with_ai(resume_text)
            
            # Split Name for Dashboard
            full_name = parsed.get("name", "")
            current_user.parsed_name = full_name
            name_parts = full_name.split()
            if len(name_parts) > 1:
                current_user.parsed_last_name = name_parts[0] # Surname first convention
                current_user.parsed_first_name = " ".join(name_parts[1:])
            else:
                current_user.parsed_first_name = full_name
                current_user.parsed_last_name = ""

            current_user.parsed_email = parsed.get("email", "")
            current_user.parsed_phone = parsed.get("phone", "")
            current_user.parsed_location = parsed.get("location", "")
            current_user.parsed_skills = parsed.get("skills", "")
            current_user.parsed_education = parsed.get("education", "")
            current_user.parsed_education_list = json.dumps(parsed.get("education_list", []))
            current_user.parsed_experience_list = json.dumps(parsed.get("experience_list", []))
            current_user.parsed_projects_list = json.dumps(parsed.get("projects_list", []))
            current_user.parsed_certifications_list = json.dumps(parsed.get("certifications_list", []))
            current_user.parsed_links = json.dumps(parsed.get("links", {}))
            current_user.parsed_summary = parsed.get("summary", "")
            current_user.suggested_role = parsed.get("suggested_role", "")
            
            # Auto-detect user type
            from models import UserAdditionalInfo
            info = current_user.additional_info
            if not info:
                info = UserAdditionalInfo(user_id=current_user.id)
                db.session.add(info)
            
            exp_years_str = parsed.get("total_experience_years", "0")
            try:
                exp_years = float(exp_years_str)
            except:
                exp_years = 0
            
            if exp_years < 1:
                info.user_type = "fresher"
            else:
                info.user_type = "experienced"
                info.total_experience = str(exp_years)

            db.session.commit()
            flash("Resume uploaded and analysed by AI successfully!", "success")
        except Exception as e:
            flash(f"Resume saved but AI parsing failed: {e}. You can continue.", "warning")

        return redirect(url_for("upload_resume"))

    return render_template("upload.html", user=current_user)
    
@app.route("/save_parsed_resume", methods=["POST"])
@login_required
def save_parsed_resume():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided."}), 400

    # Basic Info
    current_user.parsed_first_name = data.get("first_name")
    current_user.parsed_last_name = data.get("last_name")
    current_user.parsed_name = f"{data.get('last_name', '')} {data.get('first_name', '')}".strip()
    current_user.parsed_email = data.get("email")
    current_user.parsed_phone = data.get("phone")
    current_user.parsed_location = data.get("location")
    current_user.parsed_summary = data.get("summary")
    current_user.parsed_skills = data.get("skills")

    # JSON lists
    current_user.parsed_education_list = json.dumps(data.get("education_list", []))
    current_user.parsed_experience_list = json.dumps(data.get("experience_list", []))
    current_user.parsed_projects_list = json.dumps(data.get("projects_list", []))
    current_user.parsed_certifications_list = json.dumps(data.get("certifications_list", []))
    current_user.parsed_links = json.dumps(data.get("links", {}))

    db.session.commit()
    return jsonify({"success": True, "message": "Resume data updated successfully!"})


# ──────────────────────────────────────────────
# Routes – Preferences
# ──────────────────────────────────────────────

@app.route("/preferences", methods=["GET", "POST"])
@login_required
def preferences():
    if request.method == "POST":
        current_user.desired_role = request.form.get("desired_role", "").strip()
        current_user.location = request.form.get("location", "").strip()
        current_user.min_salary = request.form.get("min_salary", "").strip()
        current_user.job_type = request.form.get("job_type", "").strip()
        current_user.linkedin_email = request.form.get("linkedin_email", "").strip()
        current_user.linkedin_password = request.form.get("linkedin_password", "")
        db.session.commit()
        flash("Preferences saved!", "success")
        return redirect(url_for("preferences"))

    return render_template("preferences.html", user=current_user)


@app.route("/additional_questions")
@login_required
def additional_questions():
    return render_template("additional_questions.html", user=current_user)


@app.route("/save_additional_info", methods=["POST"])
@login_required
def save_additional_info():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided."}), 400

    from models import UserAdditionalInfo
    info = current_user.additional_info
    if not info:
        info = UserAdditionalInfo(user_id=current_user.id)
        db.session.add(info)

    # Map incoming data to model fields
    info.user_type = data.get("user_type")
    
    # Common fields
    info.preferred_location = data.get("preferred_location")
    info.relocate = data.get("relocate")
    info.remote = data.get("remote")
    info.onsite = data.get("onsite")
    info.expected_ctc = data.get("expected_ctc")
    
    # Address fields
    info.street_address = data.get("street_address")
    info.city = data.get("city")
    info.state = data.get("state")
    info.pincode = data.get("pincode")
    info.country = data.get("country")

    if info.user_type == "fresher":
        info.internship_experience = data.get("internship_experience")
        info.skills = data.get("skills")
        info.preferred_role = data.get("preferred_role")
        info.immediate_join = data.get("immediate_join")
    else:
        info.total_experience = data.get("total_experience")
        info.relevant_experience = data.get("relevant_experience")
        info.current_ctc = data.get("current_ctc")
        info.notice_period = data.get("notice_period")
        info.serving_notice = data.get("serving_notice")
        info.current_company = data.get("current_company")
        info.experience_python = data.get("experience_python")
        info.experience_sql = data.get("experience_sql")
        info.experience_aws = data.get("experience_aws")
        info.experience_tensorflow = data.get("experience_tensorflow")
        info.experience_databases = data.get("experience_databases")

    db.session.commit()
    return jsonify({"success": True, "message": "Information saved successfully!"})


# ──────────────────────────────────────────────
# Routes – Bot
# ──────────────────────────────────────────────

@app.route("/running")
@login_required
def running():
    return render_template("running.html", user=current_user)


@app.route("/start_bot", methods=["POST"])
@login_required
def start_bot():
    if current_user.bot_running:
        return jsonify({"success": False, "message": "Bot is already running."}), 400

    if not current_user.resume_text:
        return jsonify({"success": False, "message": "Please upload your resume first."}), 400

    if not current_user.desired_role or not current_user.location:
        return jsonify({"success": False, "message": "Please set your job preferences first."}), 400

    if not current_user.linkedin_email or not current_user.linkedin_password:
        return jsonify({"success": False, "message": "Please add your LinkedIn credentials in Preferences."}), 400

    from bot_logic import run_bot, clear_bot_logs
    
    # 🚀 THE FIX: Clear logs and reset counters BEFORE starting the thread
    clear_bot_logs()
    current_user.bot_running = True
    current_user.bot_status_message = "Initializing bot..."
    current_user.total_applied = 0
    current_user.total_scanned = 0
    current_user.total_skipped = 0
    db.session.commit()

    # Snapshot values for the thread
    user_id = current_user.id
    resume_text = current_user.resume_text
    desired_role = current_user.desired_role
    location = current_user.location
    linkedin_email = current_user.linkedin_email
    linkedin_password = current_user.linkedin_password
    threshold = app.config["COSINE_THRESHOLD"]

    def bot_thread():
        run_bot(
            user_id=user_id,
            resume_text=resume_text,
            desired_role=desired_role,
            location=location,
            linkedin_email=linkedin_email,
            linkedin_password=linkedin_password,
            cosine_threshold=threshold,
            max_scan=app.config["MAX_JOBS_SCAN"],
            max_apply=app.config["MAX_JOBS_APPLY"],
        )

    t = threading.Thread(target=bot_thread, daemon=True)
    t.start()

    return jsonify({"success": True, "message": "Bot started!", "redirect": url_for("running")})

@app.route("/stop_bot", methods=["POST"])
@login_required
def stop_bot():
    """Mark bot as stopped and proactively close the browser."""
    from bot_logic import abort_bot
    abort_bot(current_user.id)
    
    current_user.bot_running = False
    current_user.bot_status_message = "Stopped by user."
    db.session.commit()
    return jsonify({"success": True})


# ──────────────────────────────────────────────
# API – Live polling
# ──────────────────────────────────────────────

@app.route("/api/bot_status")
@login_required
def api_bot_status():
    from bot_logic import get_bot_logs
    user = db.session.get(User, current_user.id)
    return jsonify({
        "running": user.bot_running,
        "status_message": user.bot_status_message or "",
        "total_applied": user.total_applied or 0,
        "total_scanned": user.total_scanned or 0,
        "total_skipped": user.total_skipped or 0,
        "logs": get_bot_logs()[-50:],  # Last 50 log lines
    })


@app.route("/api/stats")
@login_required
def api_stats():
    user = db.session.get(User, current_user.id)
    applications = Application.query.filter_by(user_id=current_user.id)\
        .order_by(Application.applied_at.desc()).limit(20).all()
    
    # Get database totals for the frontend
    applied_count = Application.query.filter_by(user_id=current_user.id, status="applied").count()
    already_applied_count = Application.query.filter_by(user_id=current_user.id, status="already_applied").count()
    skipped_count = Application.query.filter_by(user_id=current_user.id, status="skipped").count()
    failed_count = Application.query.filter_by(user_id=current_user.id, status="failed").count()

    return jsonify({
        "total_applied": applied_count,
        "total_already_applied": already_applied_count,
        "total_skipped": skipped_count,
        "total_failed": failed_count,
        "last_run_date": user.last_run_date.strftime("%Y-%m-%d %H:%M") if user.last_run_date else "Never",
        "applications": [a.to_dict() for a in applications],
    })


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.run(debug=True, use_reloader=False)
