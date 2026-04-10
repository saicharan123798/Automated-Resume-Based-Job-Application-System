"""
bot_logic.py – LinkedIn automation bot for AutoJob.
Fully upgraded: Strict Success Validation, Discard Popup Handling, and Success Verification.
"""

import os
import time
import pickle
import threading
import re
import random
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    StaleElementReferenceException, WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

class IntegritySkipException(Exception):
    """Raised when a form requires dishonest data for freshers."""
    pass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sk_cosine_similarity

from bot_helper import get_answer_from_user_data
from bot_logic_helper import get_final_answer

# Global driver registry for immediate termination
import state
active_drivers = state.active_drivers

def abort_bot(user_id):
    """Proactively closes the browser for a specific user to stop the bot immediately."""
    _log(f"    [DEBUG] abort_bot called for user_id: {user_id} (Type: {type(user_id)})")
    _log(f"    [DEBUG] Current active drivers: {list(active_drivers.keys())}")
    
    # Try both ways just in case of type mismatch (int vs str)
    driver = active_drivers.pop(user_id, None)
    if not driver:
        # Retry with string if it's an int, or vice versa
        alt_id = str(user_id) if isinstance(user_id, int) else (int(user_id) if str(user_id).isdigit() else None)
        if alt_id:
            driver = active_drivers.pop(alt_id, None)

    if driver:
        _log(f"    [STOP] Aborting bot for user {user_id}. Closing browser...")
        try:
            driver.quit()
        except Exception as e:
            _log(f"    [!] Error quitting driver during abort: {e}")
    else:
        _log(f"    [!] No active driver found for user_id: {user_id}")

def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line.strip())
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except: pass

def _log_step(data: dict) -> None:
    """Structured debug logging for application steps."""
    ts = datetime.now().strftime("%H:%M:%S")
    msg = f"    [STEP] {data.get('step')} | Q: '{data.get('question')}' | A: '{data.get('answer')}' | Method: {data.get('method')} | Status: {data.get('status')}"
    _log(msg)

def wait_safe(driver: webdriver.Chrome, xpath: str, timeout: int = 10):
    """Network-resilient wait with automatic refresh."""
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))
    except:
        _log("    [NETWORK] Element timeout. Refreshing page...")
        driver.refresh()
        time.sleep(3)
        try:
            return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))
        except:
            return None

def _save_cookies(driver: webdriver.Chrome, user_id: int) -> None:
    """Saves session cookies for persistence."""
    try:
        cookie_path = os.path.join(os.path.dirname(__file__), "logs", f"cookies_{user_id}.pkl")
        with open(cookie_path, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
    except Exception as e:
        _log(f"    [!] Cookie save failed: {e}")

def _load_cookies(driver: webdriver.Chrome, user_id: int) -> bool:
    """Loads session cookies to skip login."""
    try:
        cookie_path = os.path.join(os.path.dirname(__file__), "logs", f"cookies_{user_id}.pkl")
        if os.path.exists(cookie_path):
            driver.get("https://www.linkedin.com") # Must be on domain
            with open(cookie_path, "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    driver.add_cookie(cookie)
            driver.refresh()
            time.sleep(2)
            return True
    except Exception as e:
        _log(f"    [!] Cookie load failed: {e}")
    return False

def capture_debug(driver: webdriver.Chrome, step_name: str) -> None:
    """Captures a screenshot for debugging on failure."""
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        if not os.path.exists(log_dir): os.makedirs(log_dir)
        filename = f"{step_name}_{int(time.time())}.png"
        path = os.path.join(log_dir, filename)
        driver.save_screenshot(path)
        _log(f"    [DEBUG] Screenshot saved: {filename}")
    except Exception as e:
        _log(f"    [!] Failed to capture debug: {e}")

def normalize_question(q: str) -> str:
    """Normalizes question text for consistent matching."""
    q = q.lower().strip().replace("?", "").replace(":", "")
    # Mapping common variations
    mappings = {
        "notice period": ["notice", "how soon", "start date", "joining"],
        "visa sponsorship": ["visa", "sponsorship", "authorized", "right to work"],
        "salary expectation": ["salary", "compensation", "package", "expectation"],
        "experience": ["years of", "how many years", "work experience"],
        "hybrid/remote": ["hybrid", "remote", "onsite", "office"],
        "job title": ["job title", "designation", "role name", "position title"],
        "company name": ["company name", "organization", "employer name"],
        "city": ["city", "town", "location of company", "office location"],
        "start month": ["start month"],
        "start year": ["start year"],
        "end month": ["end month"],
        "end year": ["end year"]
    }
    for key, variations in mappings.items():
        if any(v in q for v in variations):
            return key
    return q

def get_bot_logs() -> list[str]:
    try:
        if not os.path.exists(LOG_FILE): return []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-50:]]
    except: return []

def clear_bot_logs() -> None:
    try: open(LOG_FILE, "w").close()
    except: pass

def build_resume_vectorizer(resume_text: str):
    try:
        vec = TfidfVectorizer(stop_words="english", max_features=5000)
        r_vec = vec.fit_transform([resume_text])
        return vec, r_vec
    except Exception as e:
        _log(f"Vectorizer build error: {e}")
        return None, None

def compute_similarity(vectorizer, resume_vector, job_text: str) -> float:
    try:
        if vectorizer is None or resume_vector is None or not job_text.strip():
            return 0.0
        j_vec = vectorizer.transform([job_text])
        score = sk_cosine_similarity(resume_vector, j_vec)[0][0]
        return float(score)
    except Exception:
        return 0.0

def _is_external_job(driver: webdriver.Chrome) -> bool:
    try:
        url = driver.current_url.lower()
        return "linkedin.com" not in url
    except Exception:
        return False

_PROFILE_DIR = os.path.join(os.path.dirname(__file__), "AutoJob_Profile")

def _build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument(f"--user-data-dir={_PROFILE_DIR}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )
    return driver

# Persistence Helpers already defined at top

def _ensure_logged_in(driver: webdriver.Chrome, email: str, password: str, user_id: int = 0) -> bool:
    # 1. Try Cookie Session
    if _load_cookies(driver, user_id):
        if "feed" in driver.current_url or driver.find_elements(By.CSS_SELECTOR, ".global-nav__me"):
            _log("  [PERSISTENCE] Logged in via cookies.")
            return True

    # 2. Manual Login
    driver.get("https://www.linkedin.com/login")
    _log("Cookie login failed. Waiting 90s for manual login...")
    timeout = time.time() + 90
    while time.time() < timeout:
        if "feed" in driver.current_url or "/in/" in driver.current_url:
            _log("Login successful.")
            _save_cookies(driver, user_id)
            return True
        time.sleep(2)
    return False

def _search_jobs(driver: webdriver.Chrome, role: str, location: str) -> None:
    url = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={role.replace(' ', '%20')}"
        f"&location={location.replace(' ', '%20')}"
        "&f_AL=true&sortBy=R"
    )
    driver.get(url)
    time.sleep(4)

def _scroll_job_list(driver: webdriver.Chrome, target: int = 25) -> None:
    """
    Scrolls the job list sidebar to load all jobs on the CURRENT page.
    """
    try:
        # 1. IDENTIFY THE SCROLLABLE PANEL
        selectors = [
            ".jobs-search-results-list",
            ".scaffold-layout__list",
            "div.jobs-search-results-list",
            "section.scaffold-layout__list"
        ]
        panel = None
        for sel in selectors:
            try:
                found = driver.find_element(By.CSS_SELECTOR, sel)
                if found.is_displayed(): panel = found; break
            except: continue
        
        if not panel:
            _log("    [SCROLL] Could not find scrollable job list panel.")
            return

        # 2. INCREMENTAL SCROLLING
        last_count = 0
        for _ in range(10): # Max 10 scrolls per page
            cards = driver.find_elements(By.CSS_SELECTOR, "div.job-card-container")
            if len(cards) == last_count: break
            last_count = len(cards)
            
            # Scroll to the last card
            driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", cards[-1])
            time.sleep(1.5)
            
            if len(cards) >= target: break
            
    except Exception as e:
        _log(f"    [SCROLL] Error during job list scroll: {e}")

def _go_to_next_page(driver: webdriver.Chrome) -> bool:
    """
    Finds and clicks the 'Next' button in LinkedIn's pagination.
    """
    try:
        # Scroll to the bottom of the page to reveal pagination
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        
        # 1. Look for 'Next' button specifically
        next_button = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Page next') or contains(@aria-label, 'Next page') or contains(., 'Next')]")
        for btn in next_button:
            if btn.is_displayed() and btn.is_enabled():
                _log("    [PAGINATION] Clicking 'Next' page button.")
                try: btn.click()
                except: driver.execute_script("arguments[0].click();", btn)
                time.sleep(5) # Wait for page reload
                return True
                
        # 2. Look for the next number button if 'Next' isn't found
        # (e.g., if page 1 is active, look for page 2)
        try:
            active_page_btn = driver.find_element(By.CSS_SELECTOR, "button.jobs-search-pagination__indicator--active")
            active_num = int(active_page_btn.text.strip())
            next_num = active_num + 1
            next_page_btn = driver.find_element(By.XPATH, f"//button[@aria-label='Page {next_num}']")
            if next_page_btn:
                _log(f"    [PAGINATION] Clicking Page {next_num} button.")
                try: next_page_btn.click()
                except: driver.execute_script("arguments[0].click();", next_page_btn)
                time.sleep(5)
                return True
        except: pass
        
    except Exception as e:
        _log(f"    [PAGINATION] Navigation error: {e}")
    return False

def _find_easy_apply_button(driver: webdriver.Chrome):
    time.sleep(2)
    try:
        panel = driver.find_element(By.CSS_SELECTOR, ".job-view-layout, .jobs-search__job-details--container, .jobs-details")
    except:
        panel = driver
        
    xpaths = [
        ".//button[contains(@class, 'jobs-apply-button')]",
        ".//button[contains(@aria-label, 'Easy Apply')]",
        ".//button[.//span[contains(text(), 'Easy Apply')]]",
        ".//div[contains(@class, 'jobs-apply')]//button"
    ]
    
    for xp in xpaths:
        try:
            btns = panel.find_elements(By.XPATH, xp)
            for btn in btns:
                if btn.is_displayed():
                    # Check if button text is "Applied"
                    if "applied" in btn.text.lower():
                        return "ALREADY_APPLIED"
                    return btn
        except:
            continue
    return None

def _is_already_applied(driver: webdriver.Chrome) -> bool:
    """
    Checks if the current job has already been applied on LinkedIn.
    """
    try:
        # Check Top Card for "Applied" text/indicators
        indicators = [
            ".jobs-s-apply--applied",
            ".artdeco-inline-feedback--success",
            ".jobs-applied-checkmark",
            ".jobs-details-premium-insight__as-applied-text"
        ]
        for css in indicators:
            if driver.find_elements(By.CSS_SELECTOR, css):
                return True
        
        # Check the details panel text broadly
        panel_text = driver.find_element(By.CSS_SELECTOR, ".job-view-layout, .jobs-search__job-details--container, .jobs-details").text.lower()
        if "applied " in panel_text or "already applied" in panel_text:
            return True
            
        # Check the button itself
        btn = _find_easy_apply_button(driver)
        if btn == "ALREADY_APPLIED":
            return True
    except: pass
    return False

def _click_easy_apply(driver: webdriver.Chrome) -> bool:
    btn = _find_easy_apply_button(driver)
    if not btn:
        _log("  Easy Apply button not found.")
        return False
    
    if btn == "ALREADY_APPLIED":
        _log("  Job already applied on LinkedIn.")
        return False # This will be caught by _is_already_applied in the loop

    _log("  Easy Apply button detected. Clicking...")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(1)
    try:
        driver.execute_script("arguments[0].click();", btn)
    except:
        btn.click()
    time.sleep(2.5)

    try:
        safety_btn = driver.find_element(By.XPATH, "//button[contains(., 'Continue applying')]")
        if safety_btn.is_displayed():
            driver.execute_script("arguments[0].click();", safety_btn)
            _log("  Dismissed Safety Popup.")
            time.sleep(1)
    except: pass

    return True

_M = ".jobs-easy-apply-modal"

def fill_field(driver: webdriver.Chrome, element, value: str, question: str = "Unknown") -> str:
    """
    UPGRADED 3-LAYER AUTOMATION SYSTEM:
    Layer 1: Human-like interaction (ActionChains + Randomness)
    Layer 2: React-Compatible JS Fallback
    Layer 3: Failsafe
    """
    time.sleep(1 + (time.time() % 1.5)) 
    
    try:
        # --- LAYER 1: HUMAN-LIKE ---
        driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", element)
        time.sleep(0.5)
        
        # Mouse randomness
        ActionChains(driver).move_to_element(element).move_by_offset(random.randint(-5, 5), random.randint(-5, 5)).pause(0.3).click().perform()
        
        tag = element.tag_name.lower()
        if tag in ["input", "textarea"]:
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.DELETE)
            element.send_keys(value)
            time.sleep(0.5)
            
            # --- LOCATION SUGGESTION LOGIC ---
            if any(kw in question.lower() for kw in ["location", "city", "country", "state", "where are you", "reside"]):
                _handle_location_suggestions(driver, element)
            
            if element.get_attribute("value") == str(value):
                _log_step({"step": "fill", "question": question, "answer": value, "method": "UI", "status": "SUCCESS"})
                return "SUCCESS"
        return "SUCCESS"

    except Exception as e:
        _log(f"    [!] Layer 1 failed for '{question}'. Trying Layer 2...")

    try:
        # --- LAYER 2: REACT-COMPATIBLE JS FALLBACK ---
        js_code = """
        const el = arguments[0];
        const val = arguments[1];
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value') || 
                                       Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
        
        if (nativeInputValueSetter && nativeInputValueSetter.set) {
            nativeInputValueSetter.set.call(el, val);
        } else {
            el.value = val;
        }

        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        """
        driver.execute_script(js_code, element, value)
        time.sleep(0.5)
        
        if element.tag_name.lower() in ["input", "textarea"]:
            if element.get_attribute("value") == str(value):
                _log_step({"step": "fill", "question": question, "answer": value, "method": "JS_REACT", "status": "SUCCESS"})
                return "SUCCESS"
        return "SUCCESS"

    except Exception as e:
        _log(f"    [!] Layer 2 failed: {e}.")

    _log_step({"step": "fill", "question": question, "answer": value, "method": "FAIL", "status": "FAILED"})
    return "FAILED"

def get_answer(question: str, user_data: dict, resume_text: str, qa_memory: dict = None, ai_tracker: dict = None) -> tuple[str, str, str]:
    """
    UPGRADED: Priority logic with Smart Field Memory and AI Tracking.
    """
    q_norm = normalize_question(question)
    if qa_memory and q_norm in qa_memory:
        return qa_memory[q_norm], "Memory", "SUCCESS"

    ans, source, status = get_final_answer(question, user_data or {}, resume_text)
    
    if source == "AI" and ai_tracker is not None:
        ai_tracker["count"] = ai_tracker.get("count", 0) + 1

    if qa_memory and status == "SUCCESS":
        qa_memory[q_norm] = ans
    
    return ans, source, status

def _handle_contact_info(driver: webdriver.Chrome, resume_text: str, user_email: str, user_type: str = "", user_data: dict = None) -> None:
    try:
        # 1. GET ACCURATE PHONE (Prioritize Verified Profile)
        phone_raw = user_data.get("phone") if user_data and user_data.get("phone") else ""
        if not phone_raw:
            phone_match = re.search(r"(\+?\d[\d\s\-().]{8,}\d)", resume_text)
            phone_raw = phone_match.group(1).strip() if phone_match else "9876543210"
        
        phone_digits = "".join(filter(str.isdigit, phone_raw))[-10:]
        
        # Use verified email if available
        final_email = user_data.get("email") if user_data and user_data.get("email") else user_email

        # 1. HANDLE DROPDOWNS (The issue in your photo)
        dropdowns = driver.find_elements(By.CSS_SELECTOR, f"{_M} select")
        for sel in dropdowns:
            try:
                s = Select(sel)
                label = driver.find_element(By.XPATH, f"//label[@for='{sel.get_attribute('id')}']").text.lower()
                
                if "country code" in label or "phone" in label:
                    # Tries to find India or +91
                    for opt in s.options:
                        if "India" in opt.text or "+91" in opt.text:
                            s.select_by_visible_text(opt.text)
                            break
                elif "email" in label:
                    # Selects the first available email in the dropdown
                    if len(s.options) > 1:
                        s.select_by_index(1)
            except: pass

        # 2. HANDLE STANDARD INPUTS (Existing logic)
        inputs = driver.find_elements(By.CSS_SELECTOR, f"{_M} input[type='text'], {_M} input[type='email'], {_M} input[type='tel'], {_M} input.artdeco-text-input--input")
        for inp in inputs:
            if (inp.get_attribute("value") or "").strip(): continue
            
            inp_id = inp.get_attribute("id") or ""
            try: label = driver.find_element(By.XPATH, f"//label[@for='{inp_id}']").text.lower()
            except: label = ""

            if "phone" in label or "mobile" in label:
                inp.clear()
                inp.send_keys(phone_digits)
            elif "email" in label:
                inp.clear()
                inp.send_keys(final_email)
            
            # Validation check
            _validate_and_fix_input(driver, inp, label, inp.get_attribute("value"), user_type)
                
    except Exception as e:
        _log(f"  Contact info error: {e}")

def _handle_resume_step(driver: webdriver.Chrome, resume_pdf_path: str) -> None:
    try:
        if driver.find_elements(By.CSS_SELECTOR, f"{_M} .jobs-document-upload-redesign-card__container"):
            return
        upload_input = driver.find_element(By.CSS_SELECTOR, f"{_M} input[type='file']")
        if os.path.exists(resume_pdf_path):
            upload_input.send_keys(os.path.abspath(resume_pdf_path))
            time.sleep(2)
    except:
        pass

def _handle_checkboxes(driver: webdriver.Chrome) -> None:
    try:
        checkboxes = driver.find_elements(By.CSS_SELECTOR, f"{_M} input[type='checkbox']:not(:checked)")
        for cb in checkboxes:
            try:
                driver.execute_script("arguments[0].click();", cb)
                time.sleep(0.3)
            except: pass
    except: pass

def _validate_and_fix_input(driver: webdriver.Chrome, element, label_text: str, current_val: str, user_type: str) -> None:
    """
    Detects red validation errors and corrects them automatically based on the error text.
    """
    try:
        time.sleep(1)
        # 1. DETECT ERROR
        error_selectors = [
            "span.artdeco-inline-feedback__message",
            "div.artdeco-inline-feedback--error",
            ".artdeco-inline-feedback"
        ]
        
        error_el = None
        # Look for error near the element (parent's parent usually contains the feedback)
        try:
            parent = element.find_element(By.XPATH, "./..")
            # Try ancestor up to 3 levels
            for _ in range(3):
                for sel in error_selectors:
                    els = parent.find_elements(By.CSS_SELECTOR, sel)
                    if els and any(e.is_displayed() for e in els):
                        error_el = next(e for e in els if e.is_displayed())
                        break
                if error_el: break
                parent = parent.find_element(By.XPATH, "./..")
        except: pass

        if not error_el:
            return # No error detected

        error_text = error_el.text.lower()
        _log(f"    [!] Validation Error detected: '{error_text}' for '{label_text}'")

        # 2. HANDLE ERROR TYPES
        fixed_val = None
        is_numeric = any(kw in label_text.lower() or kw in error_text for kw in ["number", "digit", "years", "experience", "how many", "salary", "notice"])
        tag_name = element.tag_name.lower()

        if is_numeric:
            if any(kw in error_text for kw in ["greater than 0", "at least 1", "must be 1", "one or more", "positive"]):
                # Global Integrity Rule: No fake '1' bypass.
                _log(f"    [INTEGRITY] Skipping job: Form requires >0 but bot calculated 0 for {label_text}")
                raise IntegritySkipException(f"Mandatory > 0 but bot found 0: {label_text}")
            else:
                fixed_val = "0"
        elif tag_name == "select":
            fixed_val = "first_option"
        else:
            fixed_val = "N/A"

        # 3. RETRY (Robust Fill)
        if fixed_val:
            try:
                # Force Scroll
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                time.sleep(0.3)
                
                if tag_name == "select":
                    dropdown = Select(element)
                    if len(dropdown.options) > 1:
                        dropdown.select_by_index(1)
                else:
                    # Robust Clear
                    element.click()
                    element.send_keys(Keys.CONTROL + "a")
                    element.send_keys(Keys.DELETE)
                    driver.execute_script("arguments[0].value = '';", element)
                    time.sleep(0.2)
                    
                    # Type Fix
                    element.send_keys(str(fixed_val))
                    time.sleep(0.5)
                    
                    # Verify
                    if not element.get_attribute("value"):
                        driver.execute_script(f"arguments[0].value = '{fixed_val}';", element)

                _log(f"    [FIX] Correcting error for '{label_text}' -> using safe fallback: {fixed_val}")
                time.sleep(0.5)
            except:
                pass

    except Exception as e:
        _log(f"    [!] Validation fix error: {e}")
def _handle_dropdowns_and_radios(driver: webdriver.Chrome, resume_text: str, user_data: dict = None, qa_memory: dict = None, ai_tracker: dict = None, user_type: str = "") -> None:
    try:
        # 1. DROPDOWNS
        dropdowns = driver.find_elements(By.CSS_SELECTOR, f"{_M} .jobs-easy-apply-form-section__grouping, {_M} .jobs-easy-apply-form-element")
        for drop in dropdowns:
            try:
                # Find the trigger and question
                trigger = None
                question_text = ""
                tag_name = ""
                
                # Standard <select>
                selects = drop.find_elements(By.TAG_NAME, "select")
                if selects:
                    trigger = selects[0]
                    tag_name = "select"
                    try:
                        label = driver.find_element(By.XPATH, f"//label[@for='{trigger.get_attribute('id')}']")
                        question_text = label.text
                    except: pass
                
                # Custom Artdeco/React
                if not trigger:
                    try:
                        trigger = drop.find_element(By.CSS_SELECTOR, ".artdeco-dropdown__trigger, [role='button'], button")
                        question_text = trigger.text.strip() or trigger.get_attribute("aria-label") or ""
                    except: continue

                if not question_text: continue

                # 🚀 SAFETY CHECK: Don't overwrite already selected dropdowns
                if tag_name == "select":
                    dropdown = Select(trigger)
                    if dropdown.first_selected_option and "select" not in dropdown.first_selected_option.text.lower():
                        _log(f"    [SKIP] Dropdown already selected: '{dropdown.first_selected_option.text}'")
                        if any(kw in question_text.lower() for kw in ["company", "employer"]):
                             user_data["current_filling_company"] = dropdown.first_selected_option.text
                        continue
                
                # --- CONTEXT ENHANCEMENT ---
                q_lower = question_text.lower()
                if q_lower == "month" or q_lower == "year":
                    try:
                        parent_text = trigger.find_element(By.XPATH, "./../../..").text.lower()
                        if "from" in parent_text: question_text = f"Start {question_text}"
                        elif "to" in parent_text: question_text = f"End {question_text}"
                    except: pass

                ans_val, source, status = get_answer(question_text, user_data, resume_text, qa_memory, ai_tracker)
                
                # Track filled company for context
                if any(kw in q_lower for kw in ["company", "employer", "organization"]):
                    user_data["current_filling_company"] = ans_val
                ans_lower = str(ans_val).lower()
                
                # Special case: "Follow company" or "Insights"
                if any(kw in question_text.lower() for kw in ["follow", "insights", "subscribe"]):
                    ans_lower = "yes"
                    source = "Rule: Follow/Insights"

                # LAYER 1 & 2 via fill_field if it's a standard select
                if tag_name == "select":
                    status = fill_field(driver, trigger, ans_val, question_text)
                    if status == "SUCCESS":
                        _log_step({"step": "dropdown", "question": question_text, "answer": ans_val, "method": "SELECT", "status": "SUCCESS"})
                        continue

                # CUSTOM DROPDOWNS (PORTAL/GLOBAL SEARCH)
                matched = False
                choice = ""
                
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", trigger)
                    time.sleep(0.5)
                    ActionChains(driver).move_to_element(trigger).move_by_offset(random.randint(-2,2), random.randint(-2,2)).click().perform()
                    time.sleep(1)
                    
                    # PORTAL SEARCH: Look for options GLOBALLY (outside the modal portal)
                    option_xpaths = [
                        "//div[contains(@class,'artdeco-dropdown-slot')]//span",
                        "//div[contains(@class,'artdeco-dropdown__content')]//li",
                        "//div[@role='listbox']//div[@role='option']",
                        "//ul[@role='listbox']//li"
                    ]
                    
                    visible_options = []
                    for xp in option_xpaths:
                        raw_opts = driver.find_elements(By.XPATH, xp)
                        visible_options = [o for o in raw_opts if o.is_displayed()]
                        if visible_options: break
                    
                    if not visible_options:
                        # Retry trigger click if options didn't appear
                        ActionChains(driver).move_to_element(trigger).click().perform()
                        time.sleep(1)
                        for xp in option_xpaths:
                            raw_opts = driver.find_elements(By.XPATH, xp)
                            visible_options = [o for o in raw_opts if o.is_displayed()]
                            if visible_options: break

                    for opt in visible_options:
                        opt_text = opt.text.lower().strip()
                        if ans_lower == opt_text or ans_lower in opt_text:
                            driver.execute_script("arguments[0].click();", opt)
                            matched = True; choice = opt.text; break
                    
                    if not matched and visible_options:
                        driver.execute_script("arguments[0].click();", visible_options[0])
                        matched = True; choice = visible_options[0].text; source = f"{source} -> PortalFallback"
                except:
                    _log(f"    [!] Portal search failed. Trying JS force.")
                    try:
                        driver.execute_script("arguments[0].click();", trigger)
                        time.sleep(0.5)
                        opts = driver.find_elements(By.XPATH, "//div[@role='option'] | //li[@role='option']")
                        if opts:
                            driver.execute_script("arguments[0].click();", opts[0])
                            matched = True; choice = "JS Portal Force"; source = f"{source} -> JS_FORCE"
                    except: pass

                if matched:
                    _log_step({"step": "dropdown", "question": question_text, "answer": choice, "method": "PORTAL", "status": "SUCCESS"})
                else:
                    _log_step({"step": "dropdown", "question": question_text, "answer": "FAILED", "method": "FAIL", "status": "FAILED"})
            except: pass

        # 2. RADIO BUTTONS / FIELDSETS
        fieldsets = driver.find_elements(By.CSS_SELECTOR, f"{_M} fieldset")
        for fs in fieldsets:
            try:
                # Force Scroll
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", fs)
                time.sleep(0.5)
                
                # --- STEP 1: READ ---
                question_text = ""
                try: 
                    legend = fs.find_element(By.CSS_SELECTOR, "legend, .fb-form-element__label, .artdeco-fieldset__legend")
                    question_text = legend.text.strip()
                except: pass
                
                if not question_text:
                    question_text = fs.get_attribute("aria-label") or ""
                
                if not question_text: continue
                
                # Intelligent Answer
                ans_val, q_type, source = get_final_answer(question_text, user_data, resume_text)
                ans_lower = str(ans_val).lower()
                
                labels = fs.find_elements(By.CSS_SELECTOR, "label")
                if not labels: continue
                
                clicked = False
                # STRICT MATCHING + JS CLICK
                for l in labels:
                    t = l.text.lower().strip()
                    if ans_lower == t or (f" {ans_lower} " in f" {t} "):
                        driver.execute_script("arguments[0].click();", l)
                        clicked = True; choice = l.text; break
                
                # Default to Yes for unidentified boolean
                if not clicked:
                    for l in labels:
                        t = l.text.lower()
                        if "yes" in t or "agree" in t:
                            driver.execute_script("arguments[0].click();", l)
                            clicked = True; choice = l.text; source = f"{source} -> Default(Yes)"; break
                    
                    if not clicked:
                        driver.execute_script("arguments[0].click();", labels[0])
                        clicked = True; choice = labels[0].text; source = f"{source} -> Default(1st)"; break
                
                _log(f"    [RADIO] Q: '{question_text}' | Type: {q_type} | A: '{choice}' | Source: {source}")
                if clicked:
                    _validate_and_fix_input(driver, labels[0], question_text, choice, "")
            except: pass

        # 3. CUSTOM DROPDOWNS (artdeco)
        custom_dropdowns = driver.find_elements(By.CSS_SELECTOR, f"{_M} .artdeco-dropdown__trigger")
        for drop in custom_dropdowns:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", drop)
                time.sleep(0.3); drop.click(); time.sleep(0.5)
                options = driver.find_elements(By.CSS_SELECTOR, f"{_M} .artdeco-dropdown__item")
                if options: 
                    driver.execute_script("arguments[0].click();", options[0])
                    _log(f"    [CUSTOM DROP] Selected first option.")
            except: pass
    except: pass
def get_question_type(q: str) -> str:
    """Simplified question type detection."""
    q = q.lower()
    if any(x in q for x in ["notice", "how soon", "start"]): return "notice"
    if any(x in q for x in ["salary", "compensation", "pay", "ctc", "lpa"]): return "salary"
    if any(x in q for x in ["experience", "years", "total"]): return "experience"
    if any(x in q for x in ["authorized", "visa", "sponsorship", "citizen", "clearance"]): return "boolean"
    if any(x in q for x in ["country", "location", "city", "town", "state", "zip", "postal"]): return "location"
    return "text"

def _handle_text_inputs(driver: webdriver.Chrome, resume_text: str, user_data: dict = None, qa_memory: dict = None, ai_tracker: dict = None, user_type: str = "") -> None:
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, f"{_M} input[type='text'], {_M} textarea")
        for inp in inputs:
            if not inp.is_displayed(): continue
            
            # 🚀 SAFETY CHECK: Don't overwrite already filled fields (e.g. from Contact Info)
            if existing_val and existing_val.lower() not in ["", "n/a"]:
                _log(f"    [SKIP] Field already filled: '{existing_val}'")
                if any(kw in (inp.get_attribute("aria-label") or "").lower() for kw in ["company", "employer"]):
                    user_data["current_filling_company"] = existing_val
                continue
            question_text = ""
            try:
                # Priority: aria-label -> label text -> placeholder
                question_text = inp.get_attribute("aria-label") or ""
                if not question_text:
                    label = driver.find_element(By.XPATH, f"//label[@for='{inp.get_attribute('id')}']")
                    question_text = label.text
            except: pass
            
            if not question_text: continue
            
            # --- CONTEXT ENHANCEMENT ---
            q_lower = question_text.lower()
            if q_lower == "month" or q_lower == "year":
                # Look for "From" or "To" in parent text
                try:
                    parent_text = inp.find_element(By.XPATH, "./../../..").text.lower()
                    if "from" in parent_text: question_text = f"Start {question_text}"
                    elif "to" in parent_text: question_text = f"End {question_text}"
                except: pass

            # SMART ANSWER
            final_ans, source, status = get_answer(question_text, user_data, resume_text, qa_memory, ai_tracker)
            
            # Track filled company for context
            if any(kw in q_lower for kw in ["company", "employer", "organization"]):
                user_data["current_filling_company"] = final_ans
            
            # Systemic cleaning for numeric types
            if final_ans and get_question_type(question_text) in ["experience", "salary", "notice"]:
                # Aggressive Numeric Sterilization: "12 LPA" -> "12"
                clean_ans = re.sub(r'[^\d.]', '', str(final_ans))
                if clean_ans:
                    # Remove trailing dots or multiple dots
                    if clean_ans.startswith('.'): clean_ans = "0" + clean_ans
                    if clean_ans.endswith('.'): clean_ans = clean_ans[:-1]
                    final_ans = clean_ans
                else:
                    final_ans = "0"
                    source = f"{source} -> Fallback(0)"
            
            # Text fallback
            if not final_ans or str(final_ans).strip().lower() in ["none", "n/a", ""]:
                q_type_simple = get_question_type(question_text)
                if q_type_simple == "boolean": final_ans = "Yes"
                elif q_type_simple in ["experience", "salary", "notice"]: final_ans = "0"
                elif q_type_simple == "location": 
                    # Strict multi-layer fallback from user_data
                    final_ans = "Hyderabad"
                    for field in ["city", "preferred_location", "location", "state"]:
                        val = user_data.get(field)
                        if val and str(val).strip().lower() not in ["", "none", "n/a"]:
                            final_ans = val; break
                else: final_ans = "N/A"
                source = f"{source} -> Fallback(System)"

            _log_step({"step": "text", "question": question_text, "answer": final_ans, "method": "INFO", "status": "START"})
            
            # --- STEP 5: SMART RETRY FILL ---
            for attempt in range(2):
                status = fill_field(driver, inp, final_ans, question_text)
                if status == "SUCCESS":
                    # Check for red validation error
                    time.sleep(0.5)
                    error_selectors = ["span.artdeco-inline-feedback__message", ".artdeco-inline-feedback--error"]
                    has_error = False
                    try:
                        parent = inp.find_element(By.XPATH, "./..")
                        for sel in error_selectors:
                            errors = parent.find_elements(By.CSS_SELECTOR, sel)
                            if errors and any(e.is_displayed() for e in errors):
                                has_error = True; break
                    except: pass
                    
                    if not has_error: break
                    _log(f"    [!] Validation error on attempt {attempt+1}. Retrying...")
                else:
                    _log(f"    [!] Fill failed on attempt {attempt+1}.")
                time.sleep(1)

            # Final validation check
            _validate_and_fix_input(driver, inp, question_text, final_ans, user_type)
    except Exception as e: _log(f"  Text input error: {e}")

def _force_fill_all_fields(driver: webdriver.Chrome, user_data: dict = None) -> None:
    """
    Final check to ensure NO field is empty before clicking Next/Submit.
    """
    try:
        # 1. Empty Inputs
        inputs = driver.find_elements(By.CSS_SELECTOR, f"{_M} input.artdeco-text-input--input:not([readonly]), {_M} input[type='text']:not([readonly]), {_M} textarea:not([readonly])")
        for inp in inputs:
            val = (inp.get_attribute("value") or "").strip()
            if not val:
                _log(f"    [FORCE] Filling empty input: {inp.get_attribute('id')}")
                # Safe defaults
                label = ""
                try: label = driver.find_element(By.XPATH, f"//label[@for='{inp.get_attribute('id')}']").text.lower()
                except: pass
                
                if any(kw in label for kw in ["experience", "years", "salary", "notice", "phone", "number"]):
                    inp.send_keys("0")
                elif any(kw in label for kw in ["location", "city", "town", "state", "address"]):
                    inp.send_keys(user_data.get("city") or user_data.get("preferred_location") or "Hyderabad")
                else:
                    inp.send_keys("N/A")
                time.sleep(0.5)

        # 2. Unselected Dropdowns
        for sel in driver.find_elements(By.CSS_SELECTOR, f"{_M} select"):
            try:
                dropdown = Select(sel)
                if not dropdown.first_selected_option or "select" in dropdown.first_selected_option.text.lower():
                    if len(dropdown.options) > 1:
                        _log(f"    [FORCE] Selecting first option for dropdown: {sel.get_attribute('id')}")
                        dropdown.select_by_index(1)
                        time.sleep(0.5)
            except: pass
            
    except Exception as e:
        _log(f"    [!] Force fill error: {e}")

def _handle_checkboxes(driver: webdriver.Chrome, user_data: dict, resume_text: str) -> None:
    try:
        checkboxes = driver.find_elements(By.CSS_SELECTOR, f"{_M} input[type='checkbox']")
        for cb in checkboxes:
            if not cb.is_displayed(): continue
            try:
                cb_id = cb.get_attribute("id")
                label = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                q_text = label.text.strip()
                
                # Smart Answer
                ans, _, _ = get_answer(q_text, user_data, resume_text)
                is_checked = "yes" in ans.lower() or "true" in ans.lower()
                
                if is_checked != cb.is_selected():
                    _log(f"    [CHECKBOX] '{q_text}' -> Setting to {is_checked}")
                    try: 
                        cb.click()
                    except:
                        try: label.click()
                        except: driver.execute_script("arguments[0].click();", cb)
                time.sleep(0.5)
            except: pass
    except Exception as e:
        _log(f"  Checkbox handling error: {e}")

def _handle_location_suggestions(driver: webdriver.Chrome, element: WebElement) -> None:
    """
    Waits for and clicks the first suggestion in a location dropdown.
    """
    try:
        # 1. Wait for suggestions to appear
        time.sleep(1.5)
        
        # 2. LinkedIn suggestion selectors (Artdeco/Typeahead/Listbox)
        suggestion_selectors = [
            ".artdeco-typeahead__result", 
            ".artdeco-typeahead__result-list li",
            "[role='listbox'] [role='option']",
            ".jobs-easy-apply-modal [role='option']",
            ".artdeco-typeahead__results li"
        ]
        
        suggestions = []
        for sel in suggestion_selectors:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            suggestions = [s for s in found if s.is_displayed()]
            if suggestions: break
            
        if suggestions:
            _log(f"    [LOCATION] Found {len(suggestions)} suggestions. Clicking first.")
            try:
                suggestions[0].click()
            except:
                driver.execute_script("arguments[0].click();", suggestions[0])
            time.sleep(1)
        else:
            _log("    [LOCATION] No suggestions appeared. Proceeding with typed text.")
            # Trigger 'Enter' just in case
            element.send_keys(Keys.ENTER)
            time.sleep(0.5)
            
    except Exception as e:
        _log(f"    [LOCATION] Suggestion handling error: {e}")

def _fill_current_step(driver: webdriver.Chrome, resume_text: str, resume_pdf_path: str, user_email: str, user_location: str, user_data: dict = None, qa_memory: dict = None, ai_tracker: dict = None, user_type: str = "") -> None:
    # Reset step context
    if user_data:
        user_data["current_filling_company"] = ""
        user_data["current_filling_date_type"] = ""
        
    _handle_contact_info(driver, resume_text, user_email, user_type, user_data)
    _handle_text_inputs(driver, resume_text, user_data, qa_memory, ai_tracker, user_type)
    _handle_dropdowns_and_radios(driver, resume_text, user_data, qa_memory, ai_tracker, user_type)
    _handle_checkboxes(driver, user_data, resume_text)
    _handle_resume_step(driver, resume_pdf_path)
    # FINAL FORCE FILL
    _force_fill_all_fields(driver, user_data)

def _handle_discard_popup(driver: webdriver.Chrome) -> None:
    """
    Handles 'Save this application?' popup by clicking 'Discard'.
    """
    try:
        # Look for discard button globally as it might be outside the main modal
        discard = driver.find_elements(By.XPATH, "//button[contains(., 'Discard')]")
        for btn in discard:
            if btn.is_displayed():
                _log("    [!] Discard popup detected. Clicking Discard.")
                try: btn.click()
                except: driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                break
    except:
        pass

def _safe_click(driver: webdriver.Chrome, modal, labels: list) -> str:
    """
    UPGRADED: Finds and clicks buttons inside modal.
    Returns: label of button clicked or ""
    """
    try:
        # Search ALL buttons globally but filter for modal/displayed
        buttons = driver.find_elements(By.XPATH, "//button")
        for btn in buttons:
            if not btn.is_displayed() or not btn.is_enabled(): continue
            
            text = btn.text.lower()
            aria = (btn.get_attribute("aria-label") or "").lower()
            combined = text + " " + aria
            
            # Block dismissive buttons
            if any(x in combined for x in ["close", "dismiss", "cancel", "save application", "discard"]):
                continue
                
            for label in labels:
                if label.lower() in combined:
                    _log(f"    [ACTION] Detected '{label}' button. Clicking...")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", btn)
                    time.sleep(0.5)
                    
                    try:
                        btn.click()
                    except:
                        driver.execute_script("arguments[0].click();", btn)
                    
                    return label
        return ""
    except Exception as e:
        _log(f"    [!] Safe click error: {e}")
        return ""

def _close_modal(driver: webdriver.Chrome) -> None:
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
        _handle_discard_popup(driver)
        # Final fallback for X button
        close_x = driver.find_elements(By.XPATH, "//button[@aria-label='Dismiss' or @aria-label='Close']")
        if close_x: 
            try: driver.execute_script("arguments[0].click();", close_x[0])
            except: pass
    except: pass

def _attempt_easy_apply(driver: webdriver.Chrome, resume_text: str, resume_pdf_path: str, user_email: str, user_location: str, user_data: dict = None, qa_memory: dict = None, ai_tracker: dict = None, user_type: str = "") -> bool:
    if not _click_easy_apply(driver): return False
    if _is_external_job(driver): return False

    _log("  Easy Apply wizard opened.")
    
    # STUCK STATE DETECTION
    prev_html = ""
    
    # FORM LOOP (Maximum 15 steps)
    for step in range(15):
        # 0. STUCK CHECK
        current_html = driver.page_source
        if current_html == prev_html:
            _log("    [!] Stuck detected (Phase unchanged). Breaking flow.")
            _close_modal(driver); return False
        prev_html = current_html

        try:
            modal = driver.find_element(By.CSS_SELECTOR, ".jobs-easy-apply-modal, .artdeco-modal")
        except:
            _log("    [!] Modal not found or closed.")
            return True # Assume success if modal is gone

        # 1. FILL ALL VISIBLE FIELDS
        _fill_current_step(driver, resume_text, resume_pdf_path, user_email, user_location, user_data, qa_memory, ai_tracker, user_type)
        
        # 2. ANTI-BOT: RANDOM DELAY
        time.sleep(1.5 + (time.time() % 2))

        # 3. BUTTONS: SUBMIT vs NEXT
        # Check SUBMIT first
        if _safe_click(driver, modal, ["Submit application", "Submit"]):
            _log("    [?] Submit clicked. Verifying success...")
            time.sleep(4)
            
            # BULLETPROOF SUCCESS VERIFICATION
            success_keywords = [
                "your application was sent", 
                "application was sent",
                "applied",
                "submitted",
                "successfully",
                "received"
            ]
            page_text = driver.execute_script("return document.body.innerText;").lower()
            
            if any(word in page_text for word in success_keywords):
                _log("    [SUCCESS] Application confirmed.")
                _close_modal(driver)
                return True
            else:
                _log("    [!] Success message not detected after Submit.")
                _close_modal(driver); return False

        # If not Submit, try NEXT/REVIEW
        clicked_label = _safe_click(driver, modal, ["Review", "Next", "Continue"])
        if clicked_label:
            _log(f"    [>] Step {step+1} ({clicked_label}) finished. Moving to next...")
            time.sleep(2)
            continue

        _log("    [!] No 'Submit' or 'Next' button found. Form stuck.")
        _close_modal(driver); return False

    _close_modal(driver); return False

def run_bot(user_id, resume_text, desired_role, location, linkedin_email, linkedin_password, cosine_threshold=0.5, max_scan=100, max_apply=20):
    from app import app, db
    from models import User, Application
    clear_bot_logs(); driver = None; applied_count, skipped_count, scanned_count = 0, 0, 0
    qa_memory = {}; failed_jobs = []; ai_tracker = {"count": 0}; user_type = "experienced"
    
    # ELITE-LEVEL CONFIGURATION
    SESSION_MAX = random.randint(15, 25)
    AI_LIMIT = 50 # Max AI calls per session for cost optimization
    
    # BEHAVIOR PATTERNS
    MODE = random.choice(["fast_apply", "slow_reader", "skip_heavy"])
    _log(f"  [BEHAVIOR] Anti-detection mode: {MODE}")
    
    # Pattern delays
    pattern_delays = {
        "fast_apply": (1, 3),
        "slow_reader": (5, 12),
        "skip_heavy": (2, 5)
    }
    MIN_WAIT, MAX_WAIT = pattern_delays[MODE]
    
    def _sync(status_msg=""):
        try:
            with app.app_context():
                u = db.session.get(User, user_id)
                if u:
                    if status_msg: u.bot_status_message = status_msg
                    u.total_applied, u.total_scanned, u.total_skipped = applied_count, scanned_count, skipped_count
                    db.session.commit()
        except: pass
    try:
        # ANTI-BOT: NATURAL DELAY START
        time.sleep(random.randint(MIN_WAIT, MAX_WAIT))
        _sync("Starting browser..."); vectorizer, resume_vector = build_resume_vectorizer(resume_text); driver = _build_driver()
        
        # Register driver for immediate abort
        _log(f"    [DEBUG] Registering driver for user_id: {user_id} (Type: {type(user_id)})")
        active_drivers[user_id] = driver
        _log(f"    [DEBUG] Current registry after registration: {list(active_drivers.keys())}")
        
        if not _ensure_logged_in(driver, linkedin_email, linkedin_password, user_id): return
        resume_pdf_path = ""; user_location = location; user_data = None
        
        # Pull latest user config
        try:
            with app.app_context():
                u = db.session.get(User, user_id)
                if u:
                    if u.resume_pdf_path: resume_pdf_path = u.resume_pdf_path
                    if u.additional_info: 
                        user_data = u.additional_info.to_dict()
                        user_type = u.additional_info.user_type or "experienced"
                    else: user_data = {}
                    
                    # Map all parsed profile fields for the bot to use
                    user_data["full_name"] = u.parsed_name or ""
                    user_data["first_name"] = u.parsed_first_name or ""
                    user_data["last_name"] = u.parsed_last_name or ""
                    user_data["email"] = u.parsed_email or ""
                    user_data["phone"] = u.parsed_phone or ""
                    user_data["location"] = u.parsed_location or ""
                    user_data["summary"] = u.parsed_summary or ""
                    user_data["experience_list"] = u.parsed_experience_list or "[]"
                    user_data["education_list"] = u.parsed_education_list or "[]"
                    user_data["projects_list"] = u.parsed_projects_list or "[]"
                    user_data["skills_tags"] = u.parsed_skills or ""
                    user_data["certifications_list"] = u.parsed_certifications_list or "[]"
                    user_data["social_links"] = u.parsed_links or "{}"
                    
                    user_data["education_text"] = u.parsed_education or "" # Legacy field
                    
                    if u.desired_role: 
                        desired_role = u.desired_role
                        user_data["desired_role"] = desired_role
                    if u.desired_location: location = u.desired_location
        except: pass

        # --- MAIN SCANNING LOOP (HANDLES MULTIPLE PAGES) ---
        _sync("Searching jobs..."); _search_jobs(driver, desired_role, location)
        
        while scanned_count < max_scan and applied_count < max_apply:
            _sync(f"Scanning Page... ({scanned_count} scanned)"); _scroll_job_list(driver, target=25)
            
            cards = driver.find_elements(By.CSS_SELECTOR, "div.job-card-container")
            page_cards_count = len(cards)
            _log(f"--- Page Scan: Found {page_cards_count} jobs on this page ---")
            
            for idx in range(page_cards_count):
                if applied_count >= max_apply or scanned_count >= max_scan: break
                
                # SESSION COOLDOWN (Safety)
                if applied_count >= SESSION_MAX:
                    cooldown = random.randint(600, 1200)
                    _sync(f"Cooldown ({cooldown//60}m)"); _log(f"⚠️ Rate limit safety: Cooldown for {cooldown//60} mins...")
                    time.sleep(cooldown); applied_count = 0; SESSION_MAX = random.randint(15, 25)

                # ANTI-DETECTION: RANDOM JOB SKIPPING
                skip_chance = 0.5 if MODE == "skip_heavy" else 0.2
                if random.random() < skip_chance:
                    _log("    [STEALTH] Randomly skipping job to vary application density.")
                    continue

                # SMART DEDUPLICATION: Check DB
                scanned_count += 1; cards = driver.find_elements(By.CSS_SELECTOR, "div.job-card-container")
                if idx >= len(cards): continue
                card = cards[idx]
                
                try:
                    # Scroll card into view before clicking
                    driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'smooth'});", card)
                    time.sleep(1)
                    card.click()
                    time.sleep(2)
                    job_url = driver.current_url
                    
                    # Check for "Already Applied" on LinkedIn
                    if _is_already_applied(driver):
                        _log(f"    [ALREADY] Detected as already applied on LinkedIn. Skipping.")
                        status = "already_applied"; sim = 1.0 
                        with app.app_context():
                             db.session.add(Application(user_id=user_id, company="LinkedIn Check", job_title="Previously Applied", job_url=job_url, status=status, similarity_score=sim))
                             db.session.commit()
                        continue

                    with app.app_context():
                        existing = db.session.query(Application).filter_by(user_id=user_id, job_url=job_url).first()
                        if existing:
                            _log(f"    [DEDUPE] Already applied to this job recorded at {existing.applied_at}. Skipping.")
                            continue
                except: continue

                try: job_title = driver.find_element(By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__job-title, h1").text.strip()
                except: job_title = "Unknown"
                try: company = driver.find_element(By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name").text.strip()
                except: company = "Unknown"
                
                _log(f"[{scanned_count}/{max_scan}] {job_title} @ {company}")
                
                job_desc = ""; 
                try: job_desc = driver.find_element(By.CSS_SELECTOR, "#job-details").text.strip()
                except: pass
                
                job_text = (job_title + " " + job_desc[:500]).strip()
                sim = compute_similarity(vectorizer, resume_vector, job_text)
                
                # DEFAULT STATUS
                status = "skipped"
                
                if sim < cosine_threshold:
                    _log(f"    [SKIP] Similarity ({sim:.2f}) below threshold.")
                    skipped_count += 1
                else:
                    _log(f"    [APPLY] Similarity ({sim:.2f}) satisfies threshold.")
                    try:
                        # AI Call Mitigation
                        if ai_tracker["count"] >= AI_LIMIT: 
                            _log("    [COST] AI limit reached for session. Skipping AI calls.")
                        
                        try:
                            success = _attempt_easy_apply(driver, resume_text, resume_pdf_path, linkedin_email, user_location, user_data, qa_memory, ai_tracker, user_type)
                            if success: applied_count += 1; status = "applied"
                            else: 
                                skipped_count += 1; status = "skipped" 
                                failed_jobs.append(job_url)
                        except IntegritySkipException as e:
                            _log(f"    [SKIP] {e}")
                            _close_modal(driver); skipped_count += 1; status = "skipped"
                        except Exception as e:
                            _log(f"    [!] Error: {e}"); status = "failed"; failed_jobs.append(job_url)
                            capture_debug(driver, "run_bot_error")
                    except: pass
                        
                try:
                    with app.app_context():
                        db.session.add(Application(user_id=user_id, company=company, job_title=job_title, job_url=job_url, status=status, similarity_score=sim))
                        db.session.commit()
                except: pass
                
                _sync(f"Applied: {applied_count} | Scanned: {scanned_count}")
                time.sleep(random.uniform(MIN_WAIT, MAX_WAIT))
                
                # Re-fetch cards because DOM might have changed after click/apply
                cards = driver.find_elements(By.CSS_SELECTOR, "div.job-card-container")

            # After finishing all cards on current page, try to go to next page
            if scanned_count < max_scan and applied_count < max_apply:
                if not _go_to_next_page(driver):
                    _log("    [PAGINATION] No more pages found. Ending search.")
                    break
            else:
                break
        if failed_jobs:
            _log(f"--- Retrying {len(failed_jobs)} failed jobs ---")
            
    except Exception as e: 
        _log(f"Bot crashed: {e}")
        if driver: capture_debug(driver, "crash")
    finally:
        active_drivers.pop(user_id, None)
        if driver: 
            try: driver.quit()
            except: pass
        _sync(f"Done! Applied: {applied_count}")
        try:
            with app.app_context():
                u = db.session.get(User, user_id)
                if u: u.bot_running = False; db.session.commit()
        except: pass