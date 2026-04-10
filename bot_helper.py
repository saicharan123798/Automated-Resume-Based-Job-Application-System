def get_answer_from_user_data(question, user_data):
    """
    Normalizes the question and matches keywords to return data from UserAdditionalInfo.
    """
    if not user_data:
        return None

    q = question.lower()

    # --- EXPERIENCE ---
    if "experience" in q:
        if "python" in q:
            return user_data.get("experience_python")
        if "sql" in q:
            return user_data.get("experience_sql")
        if "aws" in q:
            return user_data.get("experience_aws")
        if "tensorflow" in q:
            return user_data.get("experience_tensorflow")
        if "database" in q:
            return user_data.get("experience_databases")
        if "total" in q:
            return user_data.get("total_experience")
        if "relevant" in q:
            return user_data.get("relevant_experience")
        
        # Fallback if just "experience" without specific skill
        if user_data.get("user_type") == "fresher":
            return user_data.get("internship_experience")
        else:
            return user_data.get("total_experience")

    # --- SALARY ---
    if "ctc" in q or "salary" in q:
        if "current" in q:
            return user_data.get("current_ctc")
        if "expected" in q:
            return user_data.get("expected_ctc")
        return user_data.get("expected_ctc") # Default to expected

    # --- NOTICE PERIOD ---
    if "notice" in q:
        return user_data.get("notice_period")

    # --- YES/NO QUESTIONS ---
    if "relocate" in q or "comfortable" in q or "commute" in q:
        return user_data.get("relocate")

    if "onsite" in q:
        return user_data.get("onsite")

    if "remote" in q:
        return user_data.get("remote")

    if "serving notice" in q:
        return user_data.get("serving_notice")

    if "immediate" in q or "join" in q:
        return user_data.get("immediate_join")

    # --- OTHER ---
    if "internship" in q:
        return user_data.get("internship_experience")
    
    if "current company" in q or "last company" in q:
        return user_data.get("current_company")

    return None
