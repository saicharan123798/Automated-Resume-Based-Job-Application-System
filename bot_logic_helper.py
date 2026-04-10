import re
from ai_helper import answer_screening_question

def generate_job_description(resume_text, role, company):
    """
    Generates a professional 2-3 sentence summary of responsibilities for a role.
    """
    try:
        from ai_helper import answer_screening_question
        prompt = f"Based on the resume below, generate a professional 2-3 sentence description of the candidate's responsibilities and achievements as a '{role}' at '{company}'. Keep it concise and impactful. If the role is NOT in the resume, generate a plausible professional description for such a role based on the candidate's general skills."
        ans = answer_screening_question(prompt, resume_text)
        return str(ans).strip()
    except:
        return "Collaborated on various projects and supported team objectives."

def get_best_experience(exp_list, target_role=""):
    """
    Selects the most relevant experience based on keyword matching with target_role.
    If no specific match, defaults to the most recent (first) entry.
    """
    if not exp_list: return None
    if not target_role: return exp_list[0]
    
    target_role = target_role.lower()
    best_exp = exp_list[0]
    best_score = 0
    
    for exp in exp_list:
        score = 0
        role = (exp.get("role") or "").lower()
        company = (exp.get("company") or "").lower()
        
        # Keyword matching
        if any(word in role for word in target_role.split()): score += 10
        if target_role in role: score += 15
        if any(word in company for word in target_role.split()): score += 5
        
        if score > best_score:
            best_score = score
            best_exp = exp
            
    return best_exp

def get_final_answer(question, user_data, resume_text):
    """
    Intelligent Q&A Model: READ -> UNDERSTAND -> FETCH -> ANSWER
    Returns: (answer_string, question_type, source)
    """
    import json
    if not user_data:
        ans = answer_screening_question(question, resume_text)
        return (ans, "unknown", "AI (No User Data)")

    q = question.lower()
    user_type = (user_data.get("user_type") or "").lower()
    target_role = user_data.get("desired_role") or ""
    
    # Context-aware overrides
    context_company = (user_data.get("current_filling_company") or "").lower()
    
    # --- STEP 2: CLASSIFY ---
    q_type = "text"
    if any(kw in q for kw in ["how many", "years", "experience"]): q_type = "experience"
    elif any(kw in q for kw in ["ctc", "salary", "compensation", "pay", "lpa"]): q_type = "salary"
    elif any(kw in q for kw in ["notice", "how soon", "start"]): q_type = "notice"
    elif any(kw in q for kw in ["comfortable", "willing", "relocate", "remote", "onsite", "on-site", "authorized", "visa", "sponsorship"]): q_type = "boolean"
    elif any(kw in q for kw in ["description", "summarize", "about the role", "responsibilities"]): q_type = "exp_description"
    elif any(kw in q for kw in ["job title", "designation", "role name", "title", "role", "position"]): q_type = "exp_title"
    elif any(kw in q for kw in ["currently work", "last job", "current company", "previous company", "employer", "organization", "company"]): q_type = "company"
    elif any(kw in q for kw in ["city", "town", "location of company", "office location", "where do you work", "location of current role"]): q_type = "exp_city"
    elif any(kw in q for kw in ["phone", "mobile", "contact number"]): q_type = "phone"
    elif "first name" in q: q_type = "first_name"
    elif "last name" in q or "surname" in q: q_type = "last_name"
    elif "street" in q or "address" in q: q_type = "street"
    elif any(kw in q for kw in ["zip", "pin", "postal"]): q_type = "pincode"
    elif any(kw in q for kw in ["location", "current city", "live in", "where are you", "reside", "place of residence"]): q_type = "full_location"
    elif "state" in q or "province" in q: q_type = "state"
    elif "country" in q: q_type = "country"
    
    # --- STEP 3 & 4: FETCH & ANSWER ---

    # 1. EXPERIENCE
    if q_type == "experience":
        is_general = any(kw in q for kw in ["total", "relevant", "overall", "work experience"])
        skill = ""
        if not is_general:
            tech_kw = ["python", "java", "sql", "aws", "react", "node", "docker", "kubernetes", "tensorflow", "spark", "hadoop", "c++", "c#"]
            for t in tech_kw:
                if t in q: skill = t; break
            if not skill:
                words = re.findall(r'\b[A-Z][a-zA-Z0-9+#]*\b', question)
                if words: skill = words[0].lower()

        ans = None
        if is_general:
            ans = user_data.get("relevant_experience") or user_data.get("total_experience")
        elif skill:
            field_map = {"python":"experience_python","sql":"experience_sql","aws":"experience_aws","tensorflow":"experience_tensorflow"}
            ans = user_data.get(field_map.get(skill, ""))

        if ans:
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(ans))
            return (nums[0] if nums else "0", "experience", "DB")
        
        if user_type == "fresher": return ("0", "experience", "Fresher Override")
        
        ans = answer_screening_question(question + " (Respond ONLY with a number, e.g. 5. No text, no units)", resume_text)
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(ans))
        return (nums[0] if nums else "0", "experience", "AI Fallback")

    # 2. WORK EXPERIENCE FIELDS (Title, Company, City, Dates, Description)
    if q_type in ["exp_title", "company", "exp_city", "exp_start_month", "exp_start_year", "exp_end_month", "exp_end_year", "exp_description"]:
        try:
            exp_list = json.loads(user_data.get("experience_list", "[]"))
            
            # If we have a context company, find THAT specific experience
            best_exp = None
            if context_company:
                for exp in exp_list:
                    if context_company in (exp.get("company") or "").lower():
                        best_exp = exp; break
            
            if not best_exp:
                best_exp = get_best_experience(exp_list, target_role)
                
            if best_exp:
                if q_type == "exp_title":
                    return (best_exp.get("role", "N/A"), "exp_title", "Smart Experience")
                elif q_type == "company":
                    if any(kw in q for kw in ["previous", "last"]):
                        if len(exp_list) > 1: return (exp_list[1].get("company", "N/A"), "company", "Parsed Experience (Previous)")
                    return (best_exp.get("company", "N/A"), "company", "Smart Experience")
                elif q_type == "exp_city":
                    loc = best_exp.get("location") or user_data.get("city") or "Remote"
                    return (loc, "exp_city", "Smart Experience")
                elif q_type == "exp_description":
                    role = best_exp.get("role", "Software Engineer")
                    company = best_exp.get("company", "Tech Co")
                    desc = generate_job_description(resume_text, role, company)
                    return (desc, "exp_description", "AI Generation")
                
                # DATE LOGIC (Simple extraction from duration string: "Jan 2023 - Present")
                dur = best_exp.get("duration", "")
                parts = dur.split("-")
                start_part = parts[0].strip() if len(parts) > 0 else ""
                end_part = parts[1].strip() if len(parts) > 1 else ""
                
                if "start" in q_type:
                    # Extraction: "Jan 2023" -> ["Jan", "2023"]
                    bits = start_part.split()
                    if "month" in q_type: return (bits[0] if bits else "January", q_type, "Smart Date")
                    if "year" in q_type: return (bits[1] if len(bits) > 1 else "2023", q_type, "Smart Date")
                elif "end" in q_type:
                    if "present" in end_part.lower() or "current" in end_part.lower(): 
                         if "month" in q_type: return ("Present", q_type, "Smart Date")
                         if "year" in q_type: return ("Present", q_type, "Smart Date")
                    bits = end_part.split()
                    if "month" in q_type: return (bits[0] if bits else "January", q_type, "Smart Date")
                    if "year" in q_type: return (bits[1] if len(bits) > 1 else "2024", q_type, "Smart Date")
        except: pass
        
        fallback_prompt = question + " (Respond ONLY with the specific name, e.g., 'Google' or 'Software Engineer'. No sentences.)"
        ans = answer_screening_question(fallback_prompt, resume_text)
        return (str(ans).strip(), q_type, "AI Fallback")

    # 3. SALARY
    if q_type == "salary":
        if "current" in q:
            if user_type == "fresher": return ("0", "salary", "Fresher Override")
            val = str(user_data.get("current_ctc") or "0")
        else:
            val = str(user_data.get("expected_ctc") or "0")
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", val)
        return (nums[0] if nums else "0", "salary", "DB")

    # 4. BOOLEAN & SMARTS
    if q_type == "boolean":
        if any(kw in q for kw in ["currently", "presently", "at the moment", "employed"]):
            try:
                exp_list = json.loads(user_data.get("experience_list", "[]"))
                
                # Context-aware currently working check
                target_exp = None
                if context_company:
                    for exp in exp_list:
                        if context_company in (exp.get("company") or "").lower():
                            target_exp = exp; break
                
                if not target_exp and exp_list: target_exp = exp_list[0]
                
                if target_exp:
                    dur = (target_exp.get("duration") or "").lower()
                    if any(kw in dur for kw in ["present", "current", "working"]):
                        return ("Yes", "boolean", "Context Experience (Present)")
                    return ("No", "boolean", "Context Experience (Past)")
            except: pass

        if any(kw in q for kw in ["relocate", "location"]):
            pref = (user_data.get("preferred_location") or "").lower()
            if pref and pref in q: return ("Yes", "boolean", "DB (Match)")
            val = (user_data.get("relocate") or "Yes").lower()
            return ("Yes" if "yes" in val else "No", "boolean", "DB")
        
        return ("Yes", "boolean", "Fallback (Positive)")

    # 5. NAMES & CONTACT
    if q_type == "first_name":
        ans = user_data.get("first_name")
        if not ans:
            full_name = user_data.get("full_name") or ""
            ans = full_name.split()[-1] if full_name else "N/A"
        return (str(ans), "first_name", "DB (Verified)")
    
    if q_type == "last_name":
        ans = user_data.get("last_name")
        if not ans:
            full_name = user_data.get("full_name") or ""
            ans = full_name.split()[0] if full_name else "N/A"
        return (str(ans), "last_name", "DB (Verified)")

    if q_type == "phone":
        ans = user_data.get("phone")
        if ans:
             # Ensure 10 digits
             digits = "".join(filter(str.isdigit, str(ans)))[-10:]
             return (digits, "phone", "DB (Verified)")
        return ("9876543210", "phone", "Fallback")

    # 6. ADDRESS & LOCATION
    if q_type == "full_location":
        city = user_data.get("city") or ""
        state = user_data.get("state") or ""
        country = user_data.get("country") or "India"
        parts = [p.strip() for p in [city, state, country] if p and p.strip()]
        if parts: return (", ".join(parts), "full_location", "DB (Concatenated)")
        # Fallback to general location if concatenation fails
        loc = user_data.get("preferred_location")
        if loc: return (str(loc), "full_location", "DB (Pref)")
        
        # AI Fallback
        ans = answer_screening_question(question + " (Respond ONLY with your current city and state)", resume_text)
        if ans and str(ans).strip().lower() not in ["", "none", "n/a"]:
            return (str(ans).strip(), "full_location", "AI")
        
        # Final safety
        return ("Hyderabad, Telangana, India", "full_location", "System Default")

    if q_type in ["street", "city", "state", "pincode", "country"]:
        ans = user_data.get(q_type)
        if ans: return (str(ans), q_type, "DB (Address)")
        
        # Smart Cross-pollenation
        if q_type == "city" and user_data.get("preferred_location"):
            return (user_data.get("preferred_location"), "city", "DB (Cross-Pref)")
        
        if q_type == "country":
            loc = (user_data.get("preferred_location") or "").lower()
            if "india" in loc: return ("India", "country", "Logic")
            ans = answer_screening_question(question + " (Respond ONLY with the name of the country, e.g., India)", resume_text)
            return (str(ans).strip(), "country", "AI")
        
        # Smart City/State Fallback (AI based on resume)
        ans = answer_screening_question(question + " (Respond ONLY with the specific location name)", resume_text)
        if ans and str(ans).strip().lower() not in ["", "none", "n/a"]:
            return (str(ans).strip(), q_type, "AI")
            
        # Final safety fallback instead of N/A
        if q_type == "city": return (user_data.get("preferred_location") or "Hyderabad", "city", "System Default")
        if q_type == "country": return ("India", "country", "System Default")
        return (user_data.get("city") or user_data.get("preferred_location") or "Hyderabad", q_type, "System Fallback")
        
    ans = answer_screening_question(question, resume_text)
    return (str(ans), q_type, "AI Fallback")
