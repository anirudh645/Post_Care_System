import streamlit as st

# Configure Streamlit page FIRST - must be the very first Streamlit command
st.set_page_config(
    page_title="Cardiac Post-Care Assistant", 
    layout="wide", 
    page_icon="❤️",
    initial_sidebar_state="expanded"
)

import mysql.connector
import datetime
import time
import hashlib
import requests
import json
import html  # For HTML escaping
import streamlit.components.v1 as components
import tempfile
import os
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# For text-to-speech and lightweight AI processing
try:
    from gtts import gTTS
    import tempfile
    import os
except ImportError:
    st.error("Please install required packages: pip install gtts mysql-connector-python requests python-dotenv")

# Database configuration - loads from .env file if available
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),  # Update with your MySQL username
    'password': os.getenv('DB_PASSWORD', ''),  # Update with your MySQL password
    'database': os.getenv('DB_NAME', 'post_care_db')  # Update with your database name
}

# Initialize database tables
def init_database():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                user_type ENUM('patient', 'doctor') NOT NULL,
                full_name VARCHAR(100) NOT NULL,
                doctor_id INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doctor_id) REFERENCES users(id)
            )
        ''')
        
        # Create patient_assessments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patient_assessments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                patient_id INT NOT NULL,
                doctor_id INT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cardiac_symptoms TEXT,
                breathing_physical TEXT,
                medication_response TEXT,
                activity_fatigue TEXT,
                ai_summary TEXT,
                risk_level ENUM('low', 'medium', 'high') DEFAULT 'medium',
                FOREIGN KEY (patient_id) REFERENCES users(id),
                FOREIGN KEY (doctor_id) REFERENCES users(id)
            )
        ''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False

# Password hashing
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# User authentication
def authenticate_user(username, password):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, user_type, full_name, doctor_id FROM users WHERE username = %s AND password_hash = %s", 
                      (username, hash_password(password)))
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

# Create new user
def create_user(username, email, password, user_type, full_name, doctor_id=None):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, user_type, full_name, doctor_id) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, email, hash_password(password), user_type, full_name, doctor_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"User creation error: {e}")
        return False

# Get doctors list
def get_doctors():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE user_type = 'doctor'")
        doctors = cursor.fetchall()
        conn.close()
        return doctors
    except Exception as e:
        st.error(f"Error fetching doctors: {e}")
        return []

# AI Summary using intelligent template analysis (reliable, local processing)

def clean_api_summary(summary):
    """Clean up repetitive or unclear AI-generated summaries."""
    if not summary:
        return summary
    
    # Remove common repetitive patterns
    import re
    
    # Remove excessive repetition of "cardiac" and "patient"
    summary = re.sub(r'\b(cardiac|patient)\s+\1\b', r'\1', summary, flags=re.IGNORECASE)
    
    # Remove repetitive phrases like "Patient Patient" or "Cardiac Cardiac"
    summary = re.sub(r'\b(\w+)\s+\1\b', r'\1', summary, flags=re.IGNORECASE)
    
    # Clean up excessive colons and formatting artifacts
    summary = re.sub(r':\s*:', ':', summary)
    summary = re.sub(r'\s+', ' ', summary)  # Multiple spaces to single space
    
    # Remove incomplete sentences at the end
    sentences = summary.split('.')
    if len(sentences) > 1 and len(sentences[-1].strip()) < 10:
        summary = '.'.join(sentences[:-1]) + '.'
    
    # Ensure it starts with a capital letter
    summary = summary.strip()
    if summary and not summary[0].isupper():
        summary = summary[0].upper() + summary[1:]
    
    return summary

def generate_ai_summary_api(text):
    """Generate summary using Hugging Face API - optimized for lightweight systems."""
    try:
        # Use a well-known, reliable summarization model
        API_URL = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"  # Try this first
        BACKUP_API_URL = "https://api-inference.huggingface.co/models/t5-small"  # Backup option
        BEST_API_URL = "https://api-inference.huggingface.co/models/google/pegasus-xsum"  # Best summarization model
        
        # Check for API token in environment variable
        api_token = os.getenv('HUGGINGFACE_API_TOKEN', None)
        
        if not api_token:
            # For demonstration, try with a demo approach
            # In production, users should set their own token
            st.info("💡 For enhanced AI summaries, set HUGGINGFACE_API_TOKEN environment variable")
            return None
            
        st.info(f"🤖 Using Hugging Face API with token: {api_token[:10]}...")
        
        headers = {"Authorization": f"Bearer {api_token}"}
        
        # Try the best summarization model first (Pegasus)
        payload = {
            "inputs": text,
            "parameters": {
                "max_length": 100,
                "min_length": 30,
                "do_sample": True,
                "temperature": 0.7,
                "top_p": 0.9,
                "repetition_penalty": 1.2
            }
        }
        
        st.info("🔄 Making API request to Pegasus summarization model...")
        response = requests.post(BEST_API_URL, headers=headers, json=payload, timeout=30)
        
        st.info(f"📡 API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                api_summary = result[0].get('summary_text', '')
                # Clean up the API response
                api_summary = clean_api_summary(api_summary)
                st.success(f"✅ Pegasus Summary Generated: {api_summary[:100]}...")
                return api_summary
        elif response.status_code == 503:
            # Model is loading - try backup model
            st.info("⏳ Pegasus model loading, trying T5-small backup...")
            
            # Try T5-small as backup
            payload_backup = {
                "inputs": f"summarize: {text}",
                "parameters": {
                    "max_length": 100,
                    "min_length": 20,
                    "temperature": 0.7,
                    "do_sample": True
                }
            }
            
            response = requests.post(BACKUP_API_URL, headers=headers, json=payload_backup, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    api_summary = result[0].get('generated_text', '')
                    # Clean up the API response
                    api_summary = clean_api_summary(api_summary)
                    st.success(f"✅ T5 Summary Generated: {api_summary[:100]}...")
                    return api_summary
        else:
            st.warning(f"⚠️ API request failed with status {response.status_code}")
            
    except Exception as e:
        # Silently fail and use fallback - don't overwhelm user with API errors
        st.warning(f"❌ API unavailable: {e}")
    
    st.info("🔄 Falling back to template-based summary")
    return None

def generate_ai_summary(cardiac_symptoms, breathing_physical, medication_response, activity_fatigue):
    """Generate AI summary using intelligent template analysis with enhanced medical logic."""
    try:
        st.info("🎯 Starting intelligent medical summary generation...")
        
        # Always use our enhanced template-based summary for reliability
        st.info("📋 Using intelligent template-based summary (most reliable method)")
        enhanced_summary = generate_enhanced_template_summary(
            cardiac_symptoms, breathing_physical, medication_response, activity_fatigue
        )
        method = "Intelligent Template Analysis"
        
        # Determine risk level based on content analysis
        full_text = f"{cardiac_symptoms} {breathing_physical} {medication_response} {activity_fatigue}"
        risk_level = assess_risk_level(full_text)
        
        st.info(f"🏁 Summary generation complete using: {method}")
        st.info(f"🎯 Risk level assessed as: {risk_level}")
        
        return enhanced_summary, risk_level
        
    except Exception as e:
        st.error(f"❌ Summary generation failed: {str(e)}")
        st.warning("🔄 Using basic template fallback")
        return generate_fallback_summary(cardiac_symptoms, breathing_physical, medication_response, activity_fatigue)

def generate_enhanced_template_summary(cardiac_symptoms, breathing_physical, medication_response, activity_fatigue):
    """Enhanced template-based summary with intelligent content analysis and medical insights."""
    
    # Analyze content for key medical indicators
    cardiac_analysis = analyze_cardiac_content(cardiac_symptoms)
    respiratory_analysis = analyze_respiratory_content(breathing_physical)
    medication_analysis = analyze_medication_content(medication_response)
    activity_analysis = analyze_activity_content(activity_fatigue)
    
    # Generate intelligent medical insights based on combined analysis
    overall_status = determine_overall_status(cardiac_analysis, respiratory_analysis, medication_analysis, activity_analysis)
    recovery_stage = assess_recovery_stage(cardiac_symptoms, breathing_physical, medication_response, activity_fatigue)
    clinical_recommendations = generate_clinical_recommendations(cardiac_analysis, respiratory_analysis, medication_analysis, activity_analysis)
    
    summary = f"""PATIENT ASSESSMENT SUMMARY (Intelligent Medical Analysis):

OVERALL STATUS: {overall_status}

DETAILED ASSESSMENT:
• Cardiac Function: {cardiac_analysis}
• Respiratory Status: {respiratory_analysis}  
• Medication Management: {medication_analysis}
• Physical Activity: {activity_analysis}

RECOVERY ASSESSMENT: {recovery_stage}

CLINICAL NOTES:
• Assessment date: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
• Analysis method: Advanced keyword recognition with medical logic
• Recommendations: {clinical_recommendations}
• Next steps: Continue monitoring per established care plan"""
    
    return summary

def determine_overall_status(cardiac, respiratory, medication, activity):
    """Determine overall patient status based on all assessments."""
    positive_count = sum(1 for analysis in [cardiac, respiratory, medication, activity] if "✅" in analysis)
    concerning_count = sum(1 for analysis in [cardiac, respiratory, medication, activity] if "⚠️" in analysis)
    
    if concerning_count >= 2:
        return "⚠️ Multiple areas of concern requiring immediate medical attention"
    elif concerning_count == 1:
        return "🔶 One area of concern noted - requires monitoring and possible intervention"
    elif positive_count >= 3:
        return "✅ Patient showing excellent recovery progress across all major areas"
    elif positive_count >= 2:
        return "✅ Patient showing good recovery progress with stable condition"
    else:
        return "🔶 Mixed recovery indicators - requires continued close monitoring"

def assess_recovery_stage(cardiac, respiratory, medication, activity):
    """Assess the current stage of recovery."""
    responses = [cardiac.lower(), respiratory.lower(), medication.lower(), activity.lower()]
    full_text = " ".join(responses)
    
    # Check for negative statements about symptoms
    negative_indicators = ['haven\'t', 'have not', 'no', 'not', 'never', 'none', 'without', 'don\'t']
    has_negative_symptoms = any(neg in full_text for neg in negative_indicators)
    
    excellent_indicators = ["excellent", "great", "perfect", "no issues", "normal", "all good"]
    good_indicators = ["good", "fine", "better", "improving", "stable", "feel good"]
    concerning_indicators = ["severe", "pain", "difficulty", "problems", "worse", "tired", "can't"]
    
    excellent_count = sum(1 for indicator in excellent_indicators if indicator in full_text)
    good_count = sum(1 for indicator in good_indicators if indicator in full_text)
    concerning_count = sum(1 for indicator in concerning_indicators if indicator in full_text)
    
    # If they mention concerning symptoms in negative context, treat as positive
    if concerning_count > 0 and has_negative_symptoms:
        excellent_count += 1  # Boost for explicitly denying symptoms
        concerning_count = 0   # Reset concerning count
    
    if excellent_count >= 2 or (good_count >= 3 and concerning_count == 0):
        return "🟢 Advanced recovery stage - patient demonstrating excellent progress"
    elif good_count >= 2 and concerning_count == 0:
        return "🟡 Intermediate recovery stage - steady progress with good indicators"
    elif concerning_count >= 2:
        return "🔴 Early recovery stage - requires intensive monitoring and support"
    else:
        return "🟡 Progressive recovery stage - showing gradual improvement"

def generate_clinical_recommendations(cardiac, respiratory, medication, activity):
    """Generate specific clinical recommendations based on assessment."""
    recommendations = []
    
    if "⚠️" in cardiac:
        recommendations.append("Immediate cardiac evaluation")
    elif "🔶" in cardiac:
        recommendations.append("Enhanced cardiac monitoring")
    
    if "⚠️" in respiratory:
        recommendations.append("Respiratory function assessment")
    elif "🔶" in respiratory:
        recommendations.append("Monitor breathing patterns")
    
    if "⚠️" in medication:
        recommendations.append("Medication review and adjustment")
    elif "🔶" in medication:
        recommendations.append("Medication compliance support")
    
    if "⚠️" in activity:
        recommendations.append("Physical therapy evaluation")
    elif "🔶" in activity:
        recommendations.append("Gradual activity progression")
    
    if not recommendations:
        recommendations.append("Continue current treatment plan")
        recommendations.append("Regular follow-up monitoring")
    
    return " • ".join(recommendations)

def analyze_cardiac_content(text):
    """Analyze cardiac symptoms for intelligent summary."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['severe', 'emergency', 'unbearable', 'level 8', 'level 9', 'level 10']):
        return "⚠️ CONCERNING SYMPTOMS - Requires immediate medical attention"
    elif any(word in text_lower for word in ['moderate', 'level 4', 'level 5', 'level 6', 'occasional']):
        return "🔶 Moderate symptoms noted - Continue close monitoring"
    elif any(word in text_lower for word in ['mild', 'level 1', 'level 2', 'level 3', 'improving']):
        return "✅ Mild symptoms - Positive recovery trajectory"
    elif any(word in text_lower for word in ['no pain', 'no symptoms', 'feeling good', 'normal', 'all good', 'good', 'fine', 'great', 'excellent', 'ok', 'okay', 'well', 'better', 'no issues', 'no problems', 'nothing', 'none']):
        return "✅ No significant cardiac symptoms reported"
    else:
        return "🔍 Mixed symptom presentation - Requires clinical evaluation"

def analyze_respiratory_content(text):
    """Analyze respiratory symptoms for intelligent summary."""
    text_lower = text.lower()
    
    # Check for negative statements first (haven't, no, not, etc.)
    negative_indicators = ['haven\'t', 'have not', 'no', 'not', 'never', 'none', 'without']
    has_negative = any(neg in text_lower for neg in negative_indicators)
    
    # Concerning symptoms
    concerning_words = ['severe', 'difficulty breathing', 'shortness', 'can\'t breathe']
    has_concerning = any(word in text_lower for word in concerning_words)
    
    # If they mention concerning symptoms but in a negative context, treat as positive
    if has_concerning and has_negative:
        return "✅ No significant respiratory symptoms reported"
    elif has_concerning and not has_negative:
        return "⚠️ Respiratory concerns noted - Monitor closely"
    elif any(word in text_lower for word in ['some', 'mild', 'slight', 'occasional']):
        return "🔶 Mild respiratory symptoms - Within expected recovery range"
    elif any(word in text_lower for word in ['good', 'normal', 'no problems', 'breathing well', 'all good', 'fine', 'great', 'excellent', 'ok', 'okay', 'well', 'better', 'no issues', 'nothing', 'none']):
        return "✅ Normal respiratory function reported"
    else:
        return "🔍 Respiratory status requires further evaluation"

def analyze_medication_content(text):
    """Analyze medication adherence for intelligent summary."""
    text_lower = text.lower()
    
    # Check for negative statements first
    negative_indicators = ['haven\'t', 'have not', 'no', 'not', 'never', 'none', 'without']
    has_negative = any(neg in text_lower for neg in negative_indicators)
    
    # Concerning medication issues
    concerning_words = ['not taking', 'stopped', 'forgot', 'can\'t afford']
    side_effect_words = ['side effects', 'problems', 'reaction', 'dizzy', 'nausea']
    
    has_adherence_issues = any(word in text_lower for word in concerning_words)
    has_side_effects = any(word in text_lower for word in side_effect_words)
    
    if has_adherence_issues and not has_negative:
        return "⚠️ MEDICATION ADHERENCE CONCERN - Requires immediate intervention"
    elif has_side_effects and has_negative:
        return "✅ Good medication tolerance - No side effects reported"
    elif has_side_effects and not has_negative:
        return "🔶 Side effects reported - May require medication adjustment"
    elif any(word in text_lower for word in ['taking as directed', 'compliant', 'following', 'no problems', 'all good', 'good', 'fine', 'great', 'excellent', 'ok', 'okay', 'well', 'better', 'no issues', 'taking', 'yes', 'everything', 'nothing']):
        return "✅ Good medication adherence - Continue current regimen"
    else:
        return "🔍 Medication compliance status needs clarification"

def analyze_activity_content(text):
    """Analyze activity tolerance for intelligent summary."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['can\'t', 'unable', 'too tired', 'exhausted', 'bed rest']):
        return "⚠️ Significant activity limitations - Consider intervention"
    elif any(word in text_lower for word in ['some fatigue', 'getting better', 'slowly improving']):
        return "🔶 Gradual improvement in activity tolerance noted"
    elif any(word in text_lower for word in ['normal', 'good energy', 'active', 'no problems', 'all good', 'good', 'fine', 'great', 'excellent', 'ok', 'okay', 'well', 'better', 'no issues', 'everything', 'nothing']):
        return "✅ Good activity tolerance - Recovery progressing well"
    else:
        return "🔍 Activity level requires further assessment"

def generate_fallback_summary(cardiac_symptoms, breathing_physical, medication_response, activity_fatigue):
    """Fallback summary generation when AI model is not available."""
    summary = f"""PATIENT ASSESSMENT SUMMARY (Template-Based):

Cardiac Status: {cardiac_symptoms[:150]}{'...' if len(cardiac_symptoms) > 150 else ''}

Respiratory Function: {breathing_physical[:150]}{'...' if len(breathing_physical) > 150 else ''}

Medication Management: {medication_response[:150]}{'...' if len(medication_response) > 150 else ''}

Activity and Recovery: {activity_fatigue[:150]}{'...' if len(activity_fatigue) > 150 else ''}

Clinical Note: This summary was generated using template-based analysis. 
Assessment completed on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}."""
    
    # Determine risk level
    full_text = f"{cardiac_symptoms} {breathing_physical} {medication_response} {activity_fatigue}"
    risk_level = assess_risk_level(full_text)
    
    return summary, risk_level

def assess_risk_level(text):
    """Assess patient risk level based on response content with negative statement handling."""
    text_lower = text.lower()
    
    # Check for negative indicators first
    negative_indicators = ['haven\'t', 'have not', 'no', 'not', 'never', 'none', 'without', 'don\'t', 'do not']
    has_negative = any(neg in text_lower for neg in negative_indicators)
    
    # High-risk indicators
    high_risk_keywords = [
        "severe", "chest pain", "difficulty breathing", "emergency", "unbearable",
        "pain level 8", "pain level 9", "pain level 10", "worsening", "worse",
        "shortness of breath", "dizziness", "fainting", "swelling", "rapid heartbeat",
        "irregular heartbeat", "nausea", "vomiting", "sweating", "fatigue severe"
    ]
    
    # Low-risk indicators  
    low_risk_keywords = [
        "no pain", "feeling better", "improving", "normal", "stable", "good",
        "pain level 1", "pain level 2", "pain level 3", "comfortable", "well",
        "no issues", "no problems", "managing well", "feeling fine", "recovering",
        "all good", "fine", "great", "excellent", "ok", "okay", "everything is fine",
        "everything is good", "nothing wrong", "no symptoms", "feeling good",
        "better", "no concerns", "everything", "nothing", "none", "alright",
        "doing well", "doing good", "all is well", "perfectly fine"
    ]
    
    # Medium-risk indicators
    medium_risk_keywords = [
        "moderate", "occasional", "mild", "pain level 4", "pain level 5", 
        "pain level 6", "some discomfort", "manageable", "tolerable"
    ]
    
    # Count keywords, but handle negative context
    high_risk_count = 0
    for keyword in high_risk_keywords:
        if keyword in text_lower:
            # Check if this symptom is mentioned in a negative context
            # Look for negative words within 10 characters before the keyword
            keyword_pos = text_lower.find(keyword)
            context_before = text_lower[max(0, keyword_pos-20):keyword_pos]
            if not any(neg in context_before for neg in negative_indicators):
                high_risk_count += 1
    
    low_risk_count = sum(1 for keyword in low_risk_keywords if keyword in text_lower)
    medium_risk_count = sum(1 for keyword in medium_risk_keywords if keyword in text_lower)
    
    # If negative statements are used with concerning keywords, treat as positive
    if has_negative and any(keyword in text_lower for keyword in high_risk_keywords):
        low_risk_count += 2  # Boost low risk for explicitly denying symptoms
    
    if high_risk_count >= 2 or any(keyword in text_lower for keyword in ["severe", "emergency", "pain level 9", "pain level 10"]):
        return "high"
    elif low_risk_count >= 1 and high_risk_count == 0 and medium_risk_count == 0:
        return "low"
    elif low_risk_count >= 2 and high_risk_count == 0:
        return "low"
    elif medium_risk_count >= 1 and high_risk_count == 0 and low_risk_count == 0:
        return "medium"
    else:
        return "medium"

# Text-to-Speech function
def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang='en')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tts.save(tmp_file.name)
            return tmp_file.name
    except Exception as e:
        st.error(f"Text-to-speech error: {e}")
        return None

# Web-based speech recognition component
def web_speech_component(step_key):
    speech_html = f"""
    <div id="speech-container-{step_key}">
        <button id="start-speech-{step_key}" onclick="startSpeech_{step_key}()" style="
            background: linear-gradient(90deg, #ff6b6b, #ff8e8e);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            cursor: pointer;
            margin: 10px;
        ">🎤 Start Recording</button>
        <button id="stop-speech-{step_key}" onclick="stopSpeech_{step_key}()" style="
            background: #dc3545;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            cursor: pointer;
            margin: 10px;
            display: none;
        ">⏹️ Stop Recording</button>
        <div id="speech-status-{step_key}" style="margin: 10px; padding: 10px; background: #f8f9fa; border-radius: 5px; color: #333;">
            Click "Start Recording" to begin speech recognition - text will automatically appear in your response
        </div>
        <button id="manual-paste-{step_key}" onclick="manualPasteToResponse_{step_key}()" style="
            background: #28a745;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            cursor: pointer;
            margin: 10px;
            display: none;
        ">📝 Paste Speech to Response</button>
        <button id="debug-{step_key}" onclick="debugTextareas_{step_key}()" style="
            background: #6c757d;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 12px;
            cursor: pointer;
            margin: 10px;
        ">🔍 Debug</button>
    </div>

    <script>
        let recognition_{step_key} = null;
        let isRecording_{step_key} = false;
        let fullTranscript_{step_key} = '';

        function initSpeechRecognition_{step_key}() {{
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {{
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                recognition_{step_key} = new SpeechRecognition();
                
                recognition_{step_key}.continuous = true;
                recognition_{step_key}.interimResults = true;
                recognition_{step_key}.lang = 'en-US';

                recognition_{step_key}.onstart = function() {{
                    document.getElementById('speech-status-{step_key}').innerHTML = '🎤 Listening... Speak now!';
                    document.getElementById('start-speech-{step_key}').style.display = 'none';
                    document.getElementById('stop-speech-{step_key}').style.display = 'inline-block';
                    isRecording_{step_key} = true;
                    fullTranscript_{step_key} = '';
                }};

                recognition_{step_key}.onresult = function(event) {{
                    let interimTranscript = '';
                    let finalTranscript = '';
                    
                    for (let i = event.resultIndex; i < event.results.length; i++) {{
                        const transcript = event.results[i][0].transcript;
                        if (event.results[i].isFinal) {{
                            finalTranscript += transcript + ' ';
                        }} else {{
                            interimTranscript += transcript;
                        }}
                    }}
                    
                    if (finalTranscript) {{
                        fullTranscript_{step_key} += finalTranscript;
                        
                        // Only update main response after a pause to avoid too many updates
                        clearTimeout(window.updateTimeout_{step_key});
                        window.updateTimeout_{step_key} = setTimeout(function() {{
                            pasteToMainResponse_{step_key}();
                        }}, 2000);
                    }}
                    
                    // Speech will be automatically pasted to main response area
                }};

                recognition_{step_key}.onerror = function(event) {{
                    document.getElementById('speech-status-{step_key}').innerHTML = '❌ Error: ' + event.error;
                    resetButtons_{step_key}();
                }};

                recognition_{step_key}.onend = function() {{
                    document.getElementById('speech-status-{step_key}').innerHTML = '✅ Recording stopped - Inserting text into response...';
                    resetButtons_{step_key}();
                    
                    // Wait a bit longer for Streamlit to render the textarea fully
                    setTimeout(function() {{
                        console.log('=== FIRST ATTEMPT (delayed) ===');
                        pasteToMainResponse_{step_key}(0);
                    }}, 1500);
                    
                    setTimeout(function() {{
                        console.log('=== SECOND ATTEMPT ===');
                        pasteToMainResponse_{step_key}(1);
                    }}, 3000);
                    
                    setTimeout(function() {{
                        console.log('=== THIRD ATTEMPT ===');
                        pasteToMainResponse_{step_key}(2);
                    }}, 5000);
                }};
            }} else {{
                document.getElementById('speech-status-{step_key}').innerHTML = '❌ Speech recognition not supported in this browser';
            }}
        }}

        function startSpeech_{step_key}() {{
            if (recognition_{step_key} && !isRecording_{step_key}) {{
                recognition_{step_key}.start();
            }} else {{
                initSpeechRecognition_{step_key}();
                if (recognition_{step_key}) {{
                    recognition_{step_key}.start();
                }}
            }}
        }}

        function stopSpeech_{step_key}() {{
            if (recognition_{step_key} && isRecording_{step_key}) {{
                recognition_{step_key}.stop();
            }}
        }}

        function resetButtons_{step_key}() {{
            document.getElementById('start-speech-{step_key}').style.display = 'inline-block';
            document.getElementById('stop-speech-{step_key}').style.display = 'none';
            isRecording_{step_key} = false;
        }}

        function pasteToMainResponse_{step_key}(retryCount = 0) {{
            const speechText = fullTranscript_{step_key}.trim();
            if (speechText) {{
                let responseTextarea = null;
                
                console.log('Searching for textarea, attempt:', retryCount + 1);
                console.log('Speech text to paste:', speechText);
                
                // Strategy 1: Look for Streamlit textareas specifically first
                const streamlitTextareas = document.querySelectorAll('[data-testid="stTextArea"] textarea, [data-baseweb="textarea"] textarea, textarea[data-testid], .stTextArea textarea');
                console.log('Streamlit textareas found:', streamlitTextareas.length);
                
                for (let i = 0; i < streamlitTextareas.length; i++) {{
                    const textarea = streamlitTextareas[i];
                    const rect = textarea.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0 && 
                                    window.getComputedStyle(textarea).display !== 'none' &&
                                    window.getComputedStyle(textarea).visibility !== 'hidden';
                    
                    console.log(`Streamlit Textarea ${{i}}:`, {{
                        placeholder: textarea.placeholder,
                        visible: isVisible,
                        disabled: textarea.disabled,
                        readOnly: textarea.readOnly,
                        id: textarea.id,
                        className: textarea.className,
                        value: textarea.value.substring(0, 50)
                    }});
                    
                    if (isVisible && !textarea.disabled && !textarea.readOnly && !textarea.id.includes('temp-speech-display')) {{
                        responseTextarea = textarea;
                        console.log('Found Streamlit textarea:', textarea);
                        break;
                    }}
                }}
                
                // Strategy 2: Look for textareas by placeholder if Streamlit method failed
                if (!responseTextarea) {{
                    const allTextareas = document.querySelectorAll('textarea');
                    console.log('All textareas found:', allTextareas.length);
                    
                    for (let i = 0; i < allTextareas.length; i++) {{
                        const textarea = allTextareas[i];
                        const rect = textarea.getBoundingClientRect();
                        const isVisible = rect.width > 0 && rect.height > 0 && 
                                        window.getComputedStyle(textarea).display !== 'none' &&
                                        window.getComputedStyle(textarea).visibility !== 'hidden';
                        
                        console.log(`All Textarea ${{i}}:`, {{
                            placeholder: textarea.placeholder,
                            visible: isVisible,
                            disabled: textarea.disabled,
                            readOnly: textarea.readOnly,
                            id: textarea.id,
                            value: textarea.value.substring(0, 50)
                        }});
                        
                        // Skip our temporary display and only look for main response textareas
                        if (isVisible && !textarea.disabled && !textarea.readOnly && 
                            !textarea.id.includes('temp-speech-display') && 
                            !textarea.id.includes('speech-container')) {{
                            
                            const placeholder = textarea.placeholder.toLowerCase();
                            if (placeholder.includes('describe') || 
                                placeholder.includes('cardiac') || 
                                placeholder.includes('breathing') || 
                                placeholder.includes('medication') || 
                                placeholder.includes('activity') ||
                                placeholder.includes('symptoms') ||
                                placeholder.includes('pain') ||
                                placeholder.includes('chest')) {{
                                responseTextarea = textarea;
                                console.log('Found matching textarea by placeholder:', placeholder);
                                break;
                            }}
                        }}
                    }}
                }}
                
                // Strategy 3: Get the largest visible, writable textarea (excluding temp displays)
                if (!responseTextarea) {{
                    const allTextareas = document.querySelectorAll('textarea');
                    let largestArea = 0;
                    for (let textarea of allTextareas) {{
                        const rect = textarea.getBoundingClientRect();
                        const area = rect.width * rect.height;
                        const isVisible = area > 0 && 
                                        window.getComputedStyle(textarea).display !== 'none' &&
                                        window.getComputedStyle(textarea).visibility !== 'hidden';
                        
                        if (isVisible && !textarea.disabled && !textarea.readOnly && 
                            !textarea.id.includes('temp-speech-display') && 
                            area > largestArea) {{
                            largestArea = area;
                            responseTextarea = textarea;
                            console.log('Found largest writable textarea with area:', area);
                        }}
                    }}
                }}
                
                // Strategy 3: Use MutationObserver to wait for textarea to appear
                if (!responseTextarea && retryCount < 2) {{
                    console.log('Textarea not found, waiting for DOM changes...');
                    const observer = new MutationObserver(function(mutations) {{
                        mutations.forEach(function(mutation) {{
                            if (mutation.type === 'childList') {{
                                observer.disconnect();
                                setTimeout(() => {{
                                    pasteToMainResponse_{step_key}(retryCount + 1);
                                }}, 500);
                            }}
                        }});
                    }});
                    
                    observer.observe(document.body, {{
                        childList: true,
                        subtree: true
                    }});
                    
                    // Disconnect observer after 2 seconds
                    setTimeout(() => {{
                        observer.disconnect();
                        if (retryCount < 2) {{
                            pasteToMainResponse_{step_key}(retryCount + 1);
                        }}
                    }}, 2000);
                    
                    document.getElementById('speech-status-{step_key}').innerHTML = `🔄 Waiting for response area to load... (attempt ${{retryCount + 1}}/3)`;
                    return;
                }}
                
                if (responseTextarea) {{
                    console.log('Attempting to paste into textarea:', responseTextarea);
                    
                    // Clear existing value first
                    responseTextarea.value = '';
                    responseTextarea.focus();
                    
                    // Set the value using multiple methods
                    responseTextarea.value = speechText;
                    
                    // For Streamlit textareas, we need to trigger React events
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                    nativeInputValueSetter.call(responseTextarea, speechText);
                    
                    // Create and dispatch a proper input event for React
                    const inputEvent = new Event('input', {{ bubbles: true }});
                    Object.defineProperty(inputEvent, 'target', {{ writable: false, value: responseTextarea }});
                    responseTextarea.dispatchEvent(inputEvent);
                    
                    // Also dispatch change event
                    const changeEvent = new Event('change', {{ bubbles: true }});
                    Object.defineProperty(changeEvent, 'target', {{ writable: false, value: responseTextarea }});
                    responseTextarea.dispatchEvent(changeEvent);
                    
                    // Try using document.execCommand as additional fallback
                    responseTextarea.select();
                    if (document.execCommand) {{
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, speechText);
                    }}
                    
                    // Trigger all possible events that Streamlit might listen to
                    const eventTypes = ['focus', 'input', 'change', 'keyup', 'keydown', 'blur', 'paste'];
                    eventTypes.forEach(eventType => {{
                        const event = new Event(eventType, {{ bubbles: true, cancelable: true }});
                        responseTextarea.dispatchEvent(event);
                    }});
                    
                    // Try InputEvent with more specific properties
                    try {{
                        const inputEvent = new InputEvent('input', {{
                            bubbles: true,
                            cancelable: true,
                            data: speechText,
                            inputType: 'insertText'
                        }});
                        responseTextarea.dispatchEvent(inputEvent);
                    }} catch (e) {{
                        console.log('InputEvent not supported, using basic Event');
                    }}
                    
                    // Force focus and blur cycle multiple times
                    setTimeout(() => {{
                        responseTextarea.focus();
                        responseTextarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        responseTextarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}, 100);
                    
                    setTimeout(() => {{
                        responseTextarea.blur();
                        responseTextarea.focus();
                        responseTextarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}, 200);
                    
                    // Verify the value was set
                    setTimeout(() => {{
                        if (responseTextarea.value === speechText) {{
                            console.log('SUCCESS: Text value confirmed in textarea');
                            document.getElementById('speech-status-{step_key}').innerHTML = '✅ Text successfully inserted into response area!';
                            document.getElementById('manual-paste-{step_key}').style.display = 'none';
                            
                            // Hide temporary display if it exists
                            const tempDisplay = document.getElementById('temp-speech-display-{step_key}');
                            if (tempDisplay) {{
                                tempDisplay.style.display = 'none';
                            }}
                            
                            // Scroll to the response area
                            responseTextarea.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }} else {{
                            console.log('WARNING: Text value not confirmed, showing manual options');
                            document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Text may not have been inserted. Use manual paste below.';
                            document.getElementById('manual-paste-{step_key}').style.display = 'inline-block';
                        }}
                    }}, 500);
                    
                    console.log('Speech text insertion completed');
                }} else {{
                    console.log('Failed to find any suitable textarea after all attempts');
                    console.log('Available textareas:', document.querySelectorAll('textarea'));
                    
                    // Show manual paste button and copy to clipboard as fallback
                    document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ <strong>Manual Action Needed:</strong> Click the green "Paste Speech to Response" button below, or copy from the text box.';
                    document.getElementById('manual-paste-{step_key}').style.display = 'inline-block';
                    
                    // Create a temporary text display if it doesn't exist
                    let tempDisplay = document.getElementById('temp-speech-display-{step_key}');
                    if (!tempDisplay) {{
                        tempDisplay = document.createElement('textarea');
                        tempDisplay.id = 'temp-speech-display-{step_key}';
                        tempDisplay.style.cssText = `
                            width: 100%;
                            height: 120px;
                            margin: 10px 0;
                            padding: 15px;
                            border: 2px solid #ff6b6b;
                            border-radius: 5px;
                            background: #fff3f3;
                            font-size: 14px;
                            color: #333;
                            font-family: Arial, sans-serif;
                            resize: vertical;
                            box-sizing: border-box;
                        `;
                        tempDisplay.placeholder = 'Your speech text will appear here - copy and paste it into the response area below';
                        tempDisplay.readOnly = false; // Make it editable so users can copy
                        document.getElementById('speech-container-{step_key}').appendChild(tempDisplay);
                    }}
                    tempDisplay.value = speechText;
                    tempDisplay.style.display = 'block';
                    
                    // Select all text for easy copying
                    tempDisplay.focus();
                    tempDisplay.select();
                    
                    // Copy to clipboard as backup
                    if (navigator.clipboard) {{
                        navigator.clipboard.writeText(speechText).then(() => {{
                            console.log('Text copied to clipboard as fallback');
                            document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Text copied to clipboard and shown below. Paste manually into response area.';
                        }}).catch(e => {{
                            console.log('Clipboard copy failed:', e);
                            document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Copy the text from the box below and paste into response area.';
                        }});
                    }} else {{
                        document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Copy the text from the box below and paste into response area.';
                    }}
                }}
            }} else {{
                console.log('No speech text to paste');
            }}
        }}

        function debugTextareas_{step_key}() {{
            console.log('=== TEXTAREA DEBUG INFO ===');
            
            // Check for Streamlit-specific textareas first
            const streamlitTextareas = document.querySelectorAll('[data-testid="stTextArea"] textarea, [data-baseweb="textarea"] textarea, textarea[data-testid], .stTextArea textarea');
            console.log('Streamlit textareas found:', streamlitTextareas.length);
            
            streamlitTextareas.forEach((textarea, index) => {{
                const rect = textarea.getBoundingClientRect();
                const style = window.getComputedStyle(textarea);
                console.log(`Streamlit Textarea ${{index}}:`, {{
                    placeholder: textarea.placeholder,
                    value: textarea.value.substring(0, 30) + '...',
                    visible: rect.width > 0 && rect.height > 0 && style.display !== 'none',
                    display: style.display,
                    visibility: style.visibility,
                    disabled: textarea.disabled,
                    readOnly: textarea.readOnly,
                    offsetParent: textarea.offsetParent !== null,
                    className: textarea.className,
                    id: textarea.id,
                    testid: textarea.getAttribute('data-testid'),
                    rect: {{
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left
                    }}
                }});
            }});
            
            // Check all textareas
            const allTextareas = document.querySelectorAll('textarea');
            console.log('All textareas found:', allTextareas.length);
            
            allTextareas.forEach((textarea, index) => {{
                const rect = textarea.getBoundingClientRect();
                const style = window.getComputedStyle(textarea);
                console.log(`All Textarea ${{index}}:`, {{
                    placeholder: textarea.placeholder,
                    value: textarea.value.substring(0, 30) + '...',
                    visible: rect.width > 0 && rect.height > 0,
                    display: style.display,
                    visibility: style.visibility,
                    disabled: textarea.disabled,
                    readOnly: textarea.readOnly,
                    offsetParent: textarea.offsetParent !== null,
                    className: textarea.className,
                    id: textarea.id,
                    isTempDisplay: textarea.id.includes('temp-speech-display'),
                    rect: {{
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left
                    }}
                }});
            }});
            
            // Check for specific Streamlit elements
            const stTextAreas = document.querySelectorAll('[data-testid="stTextArea"]');
            console.log('Elements with stTextArea testid:', stTextAreas.length);
            
            document.getElementById('speech-status-{step_key}').innerHTML = `🔍 Debug info logged. Found ${{allTextareas.length}} total textareas, ${{streamlitTextareas.length}} Streamlit textareas.`;
        }}

        function manualPasteToResponse_{step_key}() {{
            console.log('=== MANUAL PASTE ATTEMPT ===');
            const speechText = fullTranscript_{step_key}.trim();
            
            if (!speechText) {{
                document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ No speech text available to paste.';
                return;
            }}
            
            // Try a more aggressive approach to find and populate ANY visible textarea
            const allTextareas = document.querySelectorAll('textarea');
            let success = false;
            
            console.log('Manual paste: Found', allTextareas.length, 'textareas');
            
            for (let i = 0; i < allTextareas.length; i++) {{
                const textarea = allTextareas[i];
                const rect = textarea.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0 && 
                                window.getComputedStyle(textarea).display !== 'none';
                
                console.log(`Manual paste textarea ${{i}}:`, {{
                    id: textarea.id,
                    placeholder: textarea.placeholder,
                    visible: isVisible,
                    disabled: textarea.disabled,
                    readOnly: textarea.readOnly,
                    isTempDisplay: textarea.id.includes('temp-speech-display')
                }});
                
                // Skip temp displays and look for the main response textarea
                if (isVisible && !textarea.disabled && !textarea.id.includes('temp-speech-display')) {{
                    try {{
                        // Force focus and clear
                        textarea.focus();
                        textarea.value = '';
                        
                        // Set the value
                        textarea.value = speechText;
                        
                        // Trigger comprehensive events for Streamlit
                        const events = [
                            new Event('focus', {{ bubbles: true }}),
                            new Event('input', {{ bubbles: true }}),
                            new Event('change', {{ bubbles: true }}),
                            new Event('keyup', {{ bubbles: true }}),
                            new Event('blur', {{ bubbles: true }})
                        ];
                        
                        events.forEach(event => textarea.dispatchEvent(event));
                        
                        // React-specific value setting
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                        if (nativeInputValueSetter) {{
                            nativeInputValueSetter.call(textarea, speechText);
                            const inputEvent = new Event('input', {{ bubbles: true }});
                            textarea.dispatchEvent(inputEvent);
                        }}
                        
                        // Check if value stuck
                        if (textarea.value === speechText) {{
                            success = true;
                            document.getElementById('speech-status-{step_key}').innerHTML = '✅ Text successfully pasted to response area!';
                            document.getElementById('manual-paste-{step_key}').style.display = 'none';
                            
                            // Hide temp display
                            const tempDisplay = document.getElementById('temp-speech-display-{step_key}');
                            if (tempDisplay) {{
                                tempDisplay.style.display = 'none';
                            }}
                            
                            textarea.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            console.log('Manual paste successful to textarea:', textarea);
                            break;
                        }}
                    }} catch (e) {{
                        console.log('Error with textarea', i, ':', e);
                    }}
                }}
            }}
            
            if (!success) {{
                console.log('Manual paste failed for all textareas');
                document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Manual paste failed. Copy text from box below and paste manually.';
                
                // Ensure temp display is visible with the text
                const tempDisplay = document.getElementById('temp-speech-display-{step_key}');
                if (tempDisplay) {{
                    tempDisplay.value = speechText;
                    tempDisplay.style.display = 'block';
                    tempDisplay.focus();
                    tempDisplay.select();
                }}
            }}
        }}

        function copyToResponse_{step_key}() {{
            // This function now forces a more aggressive paste attempt
            const speechText = fullTranscript_{step_key}.trim();
            if (!speechText) {{
                document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ No speech text available to paste.';
                return;
            }}
            
            // Try every possible textarea aggressively
            const allTextareas = document.querySelectorAll('textarea');
            let success = false;
            
            for (let textarea of allTextareas) {{
                const rect = textarea.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && !textarea.disabled) {{
                    try {{
                        textarea.focus();
                        textarea.value = speechText;
                        
                        // Fire all possible events
                        ['focus', 'input', 'change', 'keyup', 'keydown', 'blur'].forEach(eventType => {{
                            textarea.dispatchEvent(new Event(eventType, {{ bubbles: true }}));
                        }});
                        
                        // Check if the value was actually set
                        if (textarea.value === speechText) {{
                            success = true;
                            document.getElementById('speech-status-{step_key}').innerHTML = '✅ Text manually pasted successfully!';
                            document.getElementById('manual-paste-{step_key}').style.display = 'none';
                            textarea.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            break;
                        }}
                    }} catch (e) {{
                        console.log('Error pasting to textarea:', e);
                    }}
                }}
            }}
            
            if (!success) {{
                // Copy to clipboard as final fallback
                if (navigator.clipboard) {{
                    navigator.clipboard.writeText(speechText).then(() => {{
                        document.getElementById('speech-status-{step_key}').innerHTML = '📋 Text copied to clipboard. Please paste manually (Ctrl+V).';
                    }}).catch(() => {{
                        document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Please manually copy the text: "' + speechText.substring(0, 50) + '..."';
                    }});
                }} else {{
                    document.getElementById('speech-status-{step_key}').innerHTML = '⚠️ Please manually copy the text: "' + speechText.substring(0, 50) + '..."';
                }}
            }}
        }}

        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {{
            initSpeechRecognition_{step_key}();
        }});
    </script>
    """
    return speech_html

# Save patient response to database
def save_patient_response(patient_id, doctor_id, cardiac_symptoms, breathing_physical, medication_response, activity_fatigue):
    try:
        # Generate AI summary
        ai_summary, risk_level = generate_ai_summary(cardiac_symptoms, breathing_physical, medication_response, activity_fatigue)
        
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO patient_assessments 
            (patient_id, doctor_id, cardiac_symptoms, breathing_physical, medication_response, activity_fatigue, ai_summary, risk_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (patient_id, doctor_id, cardiac_symptoms, breathing_physical, medication_response, activity_fatigue, ai_summary, risk_level))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Failed to save assessment: {e}")
        return False

# Get patient assessments
def get_patient_assessments(patient_id=None, doctor_id=None):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        if patient_id:
            cursor.execute('''
                SELECT a.*, u.full_name as patient_name 
                FROM patient_assessments a 
                JOIN users u ON a.patient_id = u.id 
                WHERE a.patient_id = %s 
                ORDER BY a.timestamp DESC
            ''', (patient_id,))
        elif doctor_id:
            cursor.execute('''
                SELECT a.*, u.full_name as patient_name 
                FROM patient_assessments a 
                JOIN users u ON a.patient_id = u.id 
                WHERE a.doctor_id = %s 
                ORDER BY a.timestamp DESC
            ''', (doctor_id,))
        else:
            cursor.execute('''
                SELECT a.*, u.full_name as patient_name 
                FROM patient_assessments a 
                JOIN users u ON a.patient_id = u.id 
                ORDER BY a.timestamp DESC 
                LIMIT 10
            ''')
        
        assessments = cursor.fetchall()
        conn.close()
        return assessments
    except Exception as e:
        st.error(f"Failed to load assessments: {e}")
        return []

# Initialize database
init_database()

# Custom CSS for better styling
st.markdown("""
<style>
    /* Hide default Streamlit elements that might cause visual artifacts */
    .stApp > header {
        background-color: transparent;
    }
    
    .stApp > div[data-testid="stDecoration"] {
        display: none;
    }
    
    /* Main styling */
    .main-header {
        background: linear-gradient(90deg, #ff6b6b, #ff8e8e);
        padding: 2rem;
        border-radius: 10px;
        text-align: center;
        color: white;
        margin-bottom: 2rem;
        border: none;
    }
    .step-container {
        background: #f8f9fa;
        padding: 2rem;
        border-radius: 15px;
        border-left: 5px solid #ff6b6b;
        margin: 1rem 0;
    }
    .patient-info {
        background: #e3f2fd;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #2196f3;
        margin: 1rem 0;
    }
    .question-box {
        background: #fff3e0;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #ff9800;
        margin: 1rem 0;
        font-size: 1.1rem;
        font-weight: 500;
        color: #333333;
    }
    .response-box {
        background: #f3e5f5;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #9c27b0;
        margin: 1rem 0;
        font-size: 1.1rem;
        line-height: 1.6;
        color: #333;
        font-weight: 500;
    }
    .current-response {
        background: #e8f5e8;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #4caf50;
        margin: 1rem 0;
        font-size: 1.1rem;
        line-height: 1.6;
        color: #2e7d32;
        font-weight: 500;
        box-shadow: 0 2px 8px rgba(76, 175, 80, 0.2);
    }
    .success-box {
        background: #e8f5e8;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #4caf50;
        text-align: center;
    }
    .high-risk {
        background: #ffebee;
        border: 2px solid #f44336;
        color: #c62828;
    }
    .medium-risk {
        background: #fff3e0;
        border: 2px solid #ff9800;
        color: #e65100;
    }
    .low-risk {
        background: #e8f5e8;
        border: 2px solid #4caf50;
        color: #2e7d32;
    }
    .stButton > button {
        background: linear-gradient(90deg, #ff6b6b, #ff8e8e);
        color: white;
        border: none;
        padding: 0.5rem 2rem;
        border-radius: 25px;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(255, 107, 107, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state for authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'user_type' not in st.session_state:
    st.session_state.user_type = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'full_name' not in st.session_state:
    st.session_state.full_name = None
if 'doctor_id' not in st.session_state:
    st.session_state.doctor_id = None

# Authentication and Registration
if not st.session_state.authenticated:
    st.markdown("""
    <div class="main-header">
        <h1>❤️ Cardiac Post-Care Health Assessment</h1>
        <p>Secure patient monitoring system</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])
    
    with tab1:
        st.subheader("Login to Your Account")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit_button = st.form_submit_button("Login", use_container_width=True)
            
            if submit_button and username and password:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user_id = user[0]
                    st.session_state.username = user[1]
                    st.session_state.user_type = user[2]
                    st.session_state.full_name = user[3]
                    st.session_state.doctor_id = user[4]
                    st.success(f"Welcome back, {user[3]}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    
    with tab2:
        st.subheader("Create New Account")
        
        with st.form("register_form"):
            reg_username = st.text_input("Choose Username")
            reg_email = st.text_input("Email")
            reg_password = st.text_input("Password", type="password")
            reg_full_name = st.text_input("Full Name")
            reg_user_type = st.selectbox("Account Type", ["patient", "doctor"])
            
            reg_doctor_id = None
            if reg_user_type == "patient":
                doctors = get_doctors()
                if doctors:
                    doctor_options = {f"{doc[1]}": doc[0] for doc in doctors}
                    selected_doctor = st.selectbox("Select Your Doctor", [""] + list(doctor_options.keys()))
                    if selected_doctor:
                        reg_doctor_id = doctor_options[selected_doctor]
            
            register_button = st.form_submit_button("Register", use_container_width=True)
            
            if register_button and reg_username and reg_email and reg_password and reg_full_name:
                if create_user(reg_username, reg_email, reg_password, reg_user_type, reg_full_name, reg_doctor_id):
                    st.success("Account created successfully! Please login.")
                else:
                    st.error("Failed to create account. Username or email may already exist.")

else:
    # Main application for authenticated users
    st.markdown(f"""
    <div class="main-header">
        <h1>❤️ Cardiac Post-Care Health Assessment</h1>
        <p>Welcome, {st.session_state.full_name} ({st.session_state.user_type.title()})</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Logout button
    if st.button("🚪 Logout", key="logout_btn"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    # Different interfaces for patients and doctors
    if st.session_state.user_type == "patient":
        # Patient Assessment Interface
        st.markdown("## 🩺 Health Assessment")
        
        # Survey Information
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info("📊 **Total Questions:** 8")
        with col2:
            st.info("⏱️ **Estimated Time:** 8-12 minutes")
        with col3:
            st.info("🎤 **Speech Recognition Available**")
        
        # Initialize session state variables for assessment (8 steps now)
        if 'step' not in st.session_state:
            st.session_state.step = 1
        if 'chest_pain_response' not in st.session_state:
            st.session_state.chest_pain_response = ""
        if 'pain_triggers_response' not in st.session_state:
            st.session_state.pain_triggers_response = ""
        if 'breathing_response' not in st.session_state:
            st.session_state.breathing_response = ""
        if 'swelling_response' not in st.session_state:
            st.session_state.swelling_response = ""
        if 'medication_adherence_response' not in st.session_state:
            st.session_state.medication_adherence_response = ""
        if 'medication_side_effects_response' not in st.session_state:
            st.session_state.medication_side_effects_response = ""
        if 'energy_level_response' not in st.session_state:
            st.session_state.energy_level_response = ""
        if 'daily_activities_response' not in st.session_state:
            st.session_state.daily_activities_response = ""
        
        # Progress Bar
        if st.session_state.step <= 8:
            progress_percentage = ((st.session_state.step - 1) / 8) * 100
        else:
            progress_percentage = 100
        
        st.markdown(f"""
        <div style="background: #f0f0f0; border-radius: 10px; padding: 1rem; margin: 1rem 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="font-weight: 600; color: #333;">Assessment Progress</span>
                <span style="font-weight: 600; color: #ff6b6b;">{"Complete" if st.session_state.step > 8 else f"Step {st.session_state.step}/8"}</span>
            </div>
            <div style="background: #ddd; border-radius: 10px; height: 10px; overflow: hidden;">
                <div style="background: linear-gradient(90deg, #ff6b6b, #ff8e8e); height: 100%; width: {progress_percentage}%; transition: width 0.3s ease;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Assessment Steps - Now 8 focused questions
        if st.session_state.step == 1:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("💓 Step 1: Chest Pain Assessment")
            
            question_text = "Since your heart attack, have you experienced any chest pain or discomfort? If yes, please rate the severity on a scale of 1 to 10."
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            # Text-to-speech for question
            if st.button("🔊 Play Question Audio", key="tts_step1"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as audio_data:
                            st.audio(audio_data.read(), format="audio/mp3")
                except Exception as e:
                    st.error(f"Audio playback error: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step1"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe any chest pain or discomfort:", 
                value=st.session_state.chest_pain_response,
                placeholder="Please describe any chest pain and rate its severity (1-10)...",
                height=120,
                key="chest_pain_response_textarea"
            )
            
            if manual_response != st.session_state.chest_pain_response:
                st.session_state.chest_pain_response = manual_response
            
            if st.session_state.chest_pain_response:
                st.markdown(f'<div class="current-response"><strong>✅ Your Response:</strong><br>{st.session_state.chest_pain_response}</div>', unsafe_allow_html=True)
            
            if st.button("➡️ Next: Pain Triggers", key="next_step1"):
                if st.session_state.chest_pain_response.strip():
                    st.session_state.step = 2
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 2:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("🎯 Step 2: Pain Triggers and Timing")
            
            question_text = "When does your chest discomfort occur? What activities or situations seem to trigger it (exercise, stress, rest, eating, etc.)?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step2"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step2"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe when pain occurs and what triggers it:", 
                value=st.session_state.pain_triggers_response,
                placeholder="Please describe when your chest discomfort occurs and what triggers it...",
                height=120,
                key="pain_triggers_response_textarea"
            )
            
            if manual_response != st.session_state.pain_triggers_response:
                st.session_state.pain_triggers_response = manual_response
            
            if st.button("➡️ Next: Breathing Assessment", use_container_width=True):
                if st.session_state.pain_triggers_response.strip():
                    st.session_state.step = 3
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 3:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("🫁 Step 3: Breathing and Shortness of Breath")
            
            question_text = "How is your breathing? Do you experience shortness of breath during normal activities, while resting, or when lying down?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step3"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step3"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe your breathing and any shortness of breath:", 
                value=st.session_state.breathing_response,
                placeholder="Please describe your breathing and any shortness of breath...",
                height=120,
                key="breathing_response_textarea"
            )
            
            if manual_response != st.session_state.breathing_response:
                st.session_state.breathing_response = manual_response
            
            if st.button("➡️ Next: Swelling Assessment", use_container_width=True):
                if st.session_state.breathing_response.strip():
                    st.session_state.step = 4
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 4:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("🦵 Step 4: Swelling and Fluid Retention")
            
            question_text = "Do you have any swelling in your legs, ankles, feet, or hands? Do you notice weight gain or that your clothes feel tighter?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step4"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step4"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe any swelling or fluid retention:", 
                value=st.session_state.swelling_response,
                placeholder="Please describe any swelling in legs, ankles, feet, hands, or weight gain...",
                height=120,
                key="swelling_response_textarea"
            )
            
            if manual_response != st.session_state.swelling_response:
                st.session_state.swelling_response = manual_response
            
            if st.button("➡️ Next: Medication Adherence", use_container_width=True):
                if st.session_state.swelling_response.strip():
                    st.session_state.step = 5
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 5:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("💊 Step 5: Medication Adherence")
            
            question_text = "Are you taking all your prescribed heart medications as directed? Do you ever miss doses or have trouble remembering to take them?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step5"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step5"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe your medication routine:", 
                value=st.session_state.medication_adherence_response,
                placeholder="Please describe how well you're taking your medications as prescribed...",
                height=120,
                key="medication_adherence_response_textarea"
            )
            
            if manual_response != st.session_state.medication_adherence_response:
                st.session_state.medication_adherence_response = manual_response
            
            if st.button("➡️ Next: Medication Side Effects", use_container_width=True):
                if st.session_state.medication_adherence_response.strip():
                    st.session_state.step = 6
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 6:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("⚠️ Step 6: Medication Side Effects")
            
            question_text = "Have you experienced any side effects from your medications such as dizziness, nausea, unusual bleeding, or any other concerning symptoms?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step6"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step6"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe any medication side effects:", 
                value=st.session_state.medication_side_effects_response,
                placeholder="Please describe any side effects from your medications...",
                height=120,
                key="medication_side_effects_response_textarea"
            )
            
            if manual_response != st.session_state.medication_side_effects_response:
                st.session_state.medication_side_effects_response = manual_response
            
            if st.button("➡️ Next: Energy Level", use_container_width=True):
                if st.session_state.medication_side_effects_response.strip():
                    st.session_state.step = 7
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 7:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("⚡ Step 7: Energy Level and Fatigue")
            
            question_text = "How is your energy level? Do you feel more tired than usual or experience fatigue during normal activities?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step7"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step7"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe your energy level and fatigue:", 
                value=st.session_state.energy_level_response,
                placeholder="Please describe your energy level and any fatigue you experience...",
                height=120,
                key="energy_level_response_textarea"
            )
            
            if manual_response != st.session_state.energy_level_response:
                st.session_state.energy_level_response = manual_response
            
            if st.button("➡️ Next: Final Question", use_container_width=True):
                if st.session_state.energy_level_response.strip():
                    st.session_state.step = 8
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before continuing.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 8:
            st.markdown('<div class="step-container">', unsafe_allow_html=True)
            st.subheader("🏃‍♂️ Step 8: Daily Activities and Physical Limitations")
            
            question_text = "Can you perform your usual daily activities like climbing stairs, walking distances, or doing household chores? Do you have any physical limitations?"
            
            st.markdown(f'<div class="question-box">🗣️ <strong>Question:</strong> {question_text}</div>', unsafe_allow_html=True)
            
            if st.button("🔊 Play Question Audio", key="tts_step8"):
                try:
                    audio_file = text_to_speech(question_text)
                    if audio_file:
                        with open(audio_file, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        os.unlink(audio_file)
                except Exception as e:
                    st.error(f"Audio playback failed: {e}")
            
            st.markdown("### 🎙️ Record Your Response")
            components.html(web_speech_component("step8"), height=200)
            
            st.markdown("### ✏️ Type Your Response")
            st.info("💡 **Tip:** Use the speech recording above to automatically fill this area, or type/edit your response manually.")
            manual_response = st.text_area(
                "Describe your ability to perform daily activities:", 
                value=st.session_state.daily_activities_response,
                placeholder="Please describe your ability to perform daily activities and any limitations...",
                height=120,
                key="daily_activities_response_textarea"
            )
            
            if manual_response != st.session_state.daily_activities_response:
                st.session_state.daily_activities_response = manual_response
            
            if st.button("✅ Complete Assessment", use_container_width=True):
                if st.session_state.daily_activities_response.strip():
                    # Combine responses for the original database structure
                    cardiac_symptoms_combined = f"Chest Pain: {st.session_state.chest_pain_response}\n\nPain Triggers: {st.session_state.pain_triggers_response}"
                    breathing_physical_combined = f"Breathing: {st.session_state.breathing_response}\n\nSwelling: {st.session_state.swelling_response}"
                    medication_combined = f"Adherence: {st.session_state.medication_adherence_response}\n\nSide Effects: {st.session_state.medication_side_effects_response}"
                    activity_fatigue_combined = f"Energy Level: {st.session_state.energy_level_response}\n\nDaily Activities: {st.session_state.daily_activities_response}"
                    
                    # Save to database
                    if save_patient_response(
                        st.session_state.user_id,
                        st.session_state.doctor_id,
                        cardiac_symptoms_combined,
                        breathing_physical_combined,
                        medication_combined,
                        activity_fatigue_combined
                    ):
                        st.session_state.step = 9
                        st.rerun()
                else:
                    st.warning("⚠️ Please provide a response before completing the assessment.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.step == 9:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.markdown("## 🎉 Assessment Complete!")
            st.markdown("### Thank you for completing your cardiac health assessment!")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if st.button("🆕 Start New Assessment", use_container_width=True):
                st.session_state.step = 1
                st.session_state.cardiac_symptoms_response = ""
                st.session_state.breathing_chest_response = ""
                st.session_state.medication_response = ""
                st.session_state.activity_fatigue_response = ""
                st.rerun()
        
        # Patient Assessment History
        st.markdown("---")
        st.subheader("📋 Your Assessment History")
        
        assessments = get_patient_assessments(patient_id=st.session_state.user_id)
        if assessments:
            for assessment in assessments:
                risk_class = f"{assessment[9]}-risk" if assessment[9] else "medium-risk"
                with st.expander(f"Assessment on {assessment[3]} - Risk: {assessment[9].title() if assessment[9] else 'Medium'}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**AI Summary:**")
                        safe_summary = html.escape(assessment[8] if assessment[8] else "No summary available")
                        st.markdown(f'<div class="response-box {risk_class}">{safe_summary}</div>', unsafe_allow_html=True)
                    with col2:
                        st.markdown("**Detailed Responses:**")
                        st.write(f"**Cardiac:** {assessment[4][:100]}...")
                        st.write(f"**Breathing:** {assessment[5][:100]}...")
                        st.write(f"**Medication:** {assessment[6][:100]}...")
                        st.write(f"**Activity:** {assessment[7][:100]}...")
        else:
            st.info("No previous assessments found.")
    
    elif st.session_state.user_type == "doctor":
        # Doctor Dashboard Interface
        st.markdown("## 👨‍⚕️ Doctor Dashboard")
        
        # Get all assessments for this doctor's patients
        assessments = get_patient_assessments(doctor_id=st.session_state.user_id)
        
        if assessments:
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Patients", len(set([a[1] for a in assessments])))
            with col2:
                st.metric("Total Assessments", len(assessments))
            with col3:
                high_risk_count = len([a for a in assessments if a[9] == 'high'])
                st.metric("High Risk Patients", high_risk_count)
            with col4:
                recent_count = len([a for a in assessments if a[3] and a[3].date() == datetime.date.today()])
                st.metric("Today's Assessments", recent_count)
            
            st.markdown("---")
            st.subheader("📊 Patient Assessments")
            
            # Filter by risk level
            risk_filter = st.selectbox("Filter by Risk Level", ["All", "High", "Medium", "Low"])
            
            filtered_assessments = assessments
            if risk_filter != "All":
                filtered_assessments = [a for a in assessments if a[9] == risk_filter.lower()]
            
            for assessment in filtered_assessments:
                risk_class = f"{assessment[9]}-risk" if assessment[9] else "medium-risk"
                risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(assessment[9], "🟡")
                
                with st.expander(f"{risk_emoji} {assessment[10]} - {assessment[3]} (Risk: {assessment[9].title() if assessment[9] else 'Medium'})"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown("**AI Summary:**")
                        safe_summary = html.escape(assessment[8] if assessment[8] else "No summary available")
                        
                        # Add indicator for summary type
                        if "AI-Generated via Hugging Face API" in safe_summary:
                            st.markdown("🤖 **AI-Generated Summary (Hugging Face API)**")
                            summary_class = f"response-box {risk_class}"
                        elif "Intelligent Template Analysis" in safe_summary:
                            st.markdown("📋 **Enhanced Template Summary**")
                            summary_class = f"response-box {risk_class}"
                        elif "Template-Based" in safe_summary:
                            st.markdown("📝 **Basic Template Summary**")
                            summary_class = f"response-box {risk_class}"
                        else:
                            st.markdown("❓ **Legacy Summary Format**")
                            summary_class = f"response-box {risk_class}"
                        
                        st.markdown(f'<div class="{summary_class}">{safe_summary}</div>', unsafe_allow_html=True)
                    with col2:
                        st.markdown("**Quick Details:**")
                        st.write(f"**Patient:** {assessment[10]}")
                        st.write(f"**Date:** {assessment[3]}")
                        st.write(f"**Risk Level:** {assessment[9].title() if assessment[9] else 'Medium'}")
                    
                    # Full details section (flat, not nested in another expander)
                    st.markdown("---")
                    st.markdown("**📋 Full Response Details:**")
                    
                    detail_col1, detail_col2 = st.columns(2)
                    with detail_col1:
                        st.markdown("**Cardiac Symptoms:**")
                        safe_cardiac = html.escape(assessment[4]) if assessment[4] else ""
                        st.markdown(f'<div class="response-box">{safe_cardiac}</div>', unsafe_allow_html=True)
                        st.markdown("**Medication Response:**")
                        safe_medication = html.escape(assessment[6]) if assessment[6] else ""
                        st.markdown(f'<div class="response-box">{safe_medication}</div>', unsafe_allow_html=True)
                    with detail_col2:
                        st.markdown("**Breathing & Physical:**")
                        safe_breathing = html.escape(assessment[5]) if assessment[5] else ""
                        st.markdown(f'<div class="response-box">{safe_breathing}</div>', unsafe_allow_html=True)
                        st.markdown("**Activity & Fatigue:**")
                        safe_activity = html.escape(assessment[7]) if assessment[7] else ""
                        st.markdown(f'<div class="response-box">{safe_activity}</div>', unsafe_allow_html=True)
        else:
            st.info("No patient assessments found for your patients.")

# Sidebar - Emergency Information
with st.sidebar:
    st.markdown("### 🚨 Emergency Information")
    st.error("**Emergency: Call 911**")
    st.warning("**Cardiac Emergency: Call Cardiology Unit**")
    st.info("**Non-Emergency: Contact Primary Care**")
    
    if st.session_state.authenticated:
        st.markdown("---")
        st.markdown(f"**Logged in as:** {st.session_state.full_name}")
        st.markdown(f"**Account Type:** {st.session_state.user_type.title()}")
        
        if st.session_state.user_type == "patient" and st.session_state.doctor_id:
            # Get doctor name
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cursor = conn.cursor()
                cursor.execute("SELECT full_name FROM users WHERE id = %s", (st.session_state.doctor_id,))
                doctor_name = cursor.fetchone()
                conn.close()
                if doctor_name:
                    st.markdown(f"**Your Doctor:** {doctor_name[0]}")
            except:
                pass

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; padding: 2rem; background: #f8f9fa; border-radius: 10px; margin-top: 2rem; color: #333333;">
    <h3 style="color: #ff6b6b;">❤️ Cardiac Post-Care Health Assessment System</h3>
    <p style="color: #333333;"><strong>Specialized monitoring for heart attack recovery patients</strong></p>
    <p style="color: #333333;">🏥 Secure, web-based patient monitoring with AI-powered assessment summaries</p>
    <p style="color: #666666;"><em>⚠️ This system uses web-based speech recognition. For emergency symptoms, call 911 immediately.</em></p>
</div>
""", unsafe_allow_html=True)
