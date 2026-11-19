# FamilyConnect AI 🏡
### AI-Powered Family Safety & Emergency Response Platform

FamilyConnect AI is an intelligent family safety and emergency response platform designed to help families report emergencies, assess incident severity, coordinate responders, and access AI-assisted first-aid guidance.

The platform combines Machine Learning, Natural Language Processing, Retrieval-Augmented Generation (RAG), and real-time communication to support emergency awareness and response coordination.

---

## 🚀 Key Features

### 1. SOS Emergency Reporting
- Submit emergency alerts through the application.
- Capture the user's browser GPS location (with permission) or select preset locations.
- Record incident descriptions, vital signs, and bystander observations.
- Track emergency incident status across the full response lifecycle.

### 2. AI-Powered Emergency Triage
- Machine Learning-based emergency severity classification (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- Random Forest classification model trained on clinical emergency scenarios.
- NLP-based extraction of symptoms, indicators, and negations from bystander descriptions.
- Deterministic clinical safety overrides ensuring critical conditions (e.g., unresponsiveness, severe hemorrhage) bypass model latency or ambiguity.
- Explainable triage results with confidence scores and clinical factor breakdowns.

### 3. Intelligent Responder Coordination
- Responder identification and ranking based on geographical proximity.
- Real-time Haversine distance calculations.
- Incident assignment, dispatch workflow, and responder status updates (`Assigned`, `En Route`, `Arrived`).
- Real-time communication and state synchronization via WebSockets.

### 4. Conversational First Aid Assistant
- ChatGPT-style interactive conversational interface.
- Context-aware follow-up questions tailored to the reported condition.
- RAG-based retrieval grounded in 10 curated clinical first-aid protocols (WHO, ERC, Red Cross standards).
- TF-IDF-based protocol document retrieval with strict relevance thresholds.
- Deterministic clinical safety validator intercepting contraindications, dangerous home remedies, and omissions.
- Instant emergency detection and priority safety overrides.
- Direct protocol references, step-by-step guidance, and pan-India emergency calling links (**112** / **108**).

### 5. Family Dashboard
- Centralized family safety and wellness dashboard.
- Directory of household members with age, relationships, and medical flags (blood groups, pacemaker, asthma, allergies).
- Real-time emergency incident monitoring and live incident timeline tracking.
- Privacy-preserving contact masking for shoulder-surfing protection.
- Family member and community responder coordination.

### 6. Authentication & Role-Based Access
- Secure password hashing using PBKDF2-HMAC-SHA256.
- Token-based session authentication with HMAC-SHA256.
- Role-based access control with three distinct roles: `admin` (household head), `member` (family member), and `responder` (verified emergency responder).
- Strict multi-tenant household isolation ensuring privacy between distinct families.

### 7. Real-Time Updates
- Bi-directional WebSocket-based incident and telemetry updates.
- Responder workflow synchronization across devices.
- Local notification simulation and alert status lifecycle tracking.

---

## 🧠 AI & Machine Learning Components

| Component | Technology | Description |
|---|---|---|
| Emergency Severity Prediction | Random Forest Classifier (`scikit-learn`) | Classifies incident urgency into `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` |
| Context Extraction | Rule-based NLP & Regex | Extracts symptoms, medical history, and handles linguistic negations |
| Emergency Safety Overrides | Deterministic Rule Engine | Enforces unbreachable clinical safety floors for life-threatening symptoms |
| Knowledge Retrieval | TF-IDF Vector Space Model | Calibrated retrieval over verified clinical emergency protocols |
| First Aid Guidance Generation | Grounded RAG Pipeline + Safety Gate | Generates step-by-step guidance verified against contraindication rules |
| Proximity Ranking | Haversine Formula | Calculates geographical distances to dispatch nearest available responders |

### AI Workflow

```text
[ User Emergency SOS Report ]
            │
            ▼
[ Bystander Description & Vital Checkboxes ]
            │
            ▼
[ NLP Context Extractor ] ──▶ Detects symptoms & linguistic negations
            │
            ▼
[ Random Forest ML Model ] ──▶ Predicts base incident severity
            │
            ▼
[ Deterministic Safety Gate ] ──▶ Applies safety overrides for critical vitals
            │
            ▼
[ Haversine Proximity Matcher ] ──▶ Ranks and assigns nearest verified responders
            │
            ▼
[ Real-Time WebSocket Delivery ] ──▶ Dispatches alerts to family & responders
```

---

## 🏗️ System Architecture

- **Frontend:** React 18, Vite, Modern CSS Variables (Light, Dark, and System Themes), PWA Mobile Support
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Starlette ASGI
- **Database:** SQLite (`familyconnect.db`) for local development; PostgreSQL-compatible for production staging
- **AI / Machine Learning:** Scikit-learn (Random Forest v2), NLP context extraction, TF-IDF vectorizer, grounded RAG
- **Real-Time Communication:** WebSockets with role-based event multiplexing
- **Security:** PBKDF2-HMAC-SHA256 password hashing, HMAC-SHA256 signed bearer tokens, Role-Based Access Control (RBAC), multi-tenant household data isolation

---

## 📂 Project Structure

```text
FamilyConnect-AI/
│
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── context_extractor.py         # NLP symptom extraction & negation detection
│   │   │   ├── local_llm.py                 # Optional local LLM synthesis client (Ollama)
│   │   │   ├── rag_assistant.py             # TF-IDF RAG conversational assistant
│   │   │   ├── safety_validator.py          # Deterministic clinical safety validator
│   │   │   ├── train_model_v2.py            # Random Forest ML triage trainer
│   │   │   ├── triage.py                    # Triage engine & emergency overrides
│   │   │   └── triage_model_v2.joblib       # Trained ML triage classifier
│   │   ├── knowledge/
│   │   │   └── protocols/                   # 10 clinical emergency protocols (JSON)
│   │   ├── routes/
│   │   │   ├── admin.py                     # Administrative actions
│   │   │   ├── auth.py                      # User authentication & tokens
│   │   │   ├── emergencies.py               # Incident creation, lifecycle & triage
│   │   │   ├── first_aid.py                 # Conversational First Aid endpoints
│   │   │   ├── household.py                 # Household management
│   │   │   ├── members.py                   # Family member profiles & locations
│   │   │   └── responders.py                # Responder coordination & dispatch
│   │   ├── services/
│   │   │   ├── notifications.py             # Alert delivery & notification engine
│   │   │   └── realtime.py                  # WebSocket connection manager
│   │   ├── auth.py                          # Password hashing & token handling
│   │   ├── database.py                      # Database session & engine setup
│   │   ├── main.py                          # FastAPI application entry point
│   │   ├── models.py                        # SQLAlchemy database models
│   │   └── schemas.py                       # Pydantic validation schemas
│   ├── test_*.py                            # Automated backend test suites
│   └── requirements.txt                     # Backend Python dependencies
│
├── frontend/
│   ├── public/                              # PWA icons, manifest & static assets
│   ├── src/
│   │   ├── components/
│   │   │   ├── AcceptInviteModal.jsx        # Household invitation modal
│   │   │   ├── AiTriageTester.jsx           # Interactive AI triage test suite
│   │   │   ├── EmergencyMonitor.jsx         # Live incident feed & tracking
│   │   │   ├── FamilyDashboard.jsx          # Family member directory & safety status
│   │   │   ├── FirstAidAssistant.jsx        # Conversational First Aid assistant UI
│   │   │   ├── Header.jsx                   # Navigation header & theme controls
│   │   │   ├── IncidentProximityMap.jsx     # Geolocation & proximity map
│   │   │   ├── IosInstallModal.jsx          # PWA installation instructions for iOS
│   │   │   ├── LoginScreen.jsx              # Authentication screen & role switcher
│   │   │   ├── MobileNav.jsx                # Responsive mobile navigation
│   │   │   ├── ResponderAndAlertManager.jsx # Responder coordination & alert management
│   │   │   └── SosTriggerModal.jsx          # One-tap SOS emergency modal
│   │   ├── services/
│   │   │   └── api.js                       # Frontend API & WebSocket client
│   │   ├── utils/
│   │   │   ├── incidentMessage.js           # Incident formatting helpers
│   │   │   ├── memberSelection.js           # Member selector utilities
│   │   │   ├── phone.js                     # Phone number formatting & validation
│   │   │   ├── privacyMask.js               # Privacy masking (phone/email)
│   │   │   └── pwaInstall.js                # PWA installation prompts
│   │   ├── App.jsx                          # Main application component
│   │   ├── index.css                        # Design system & responsive styles
│   │   └── main.jsx                         # React application entry point
│   ├── test/                                # Frontend unit & resilience tests
│   ├── package.json                         # Frontend dependencies & scripts
│   └── vite.config.js                       # Vite build & PWA configuration
│
├── .gitignore
├── .env.example
├── Dockerfile
├── render.yaml
└── README.md
```

---

## ⚙️ Installation & Setup

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** and **npm**
- **Git**

### 1. Clone the Repository

```bash
git clone https://github.com/jerinjohnson2020-glitch/familyconnect-ai.git
cd familyconnect-ai
```

### 2. Backend Setup

Navigate to the `backend` folder:

```bash
cd backend
```

Create and activate a virtual environment:

**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

Configure environment variables:

```bash
cp ../.env.example .env
```
*(Configure required environment variables using `.env.example` as a reference. Never commit sensitive credentials.)*

Start the FastAPI backend server:

```bash
uvicorn app.main:app --reload --port 8000
```

- **Backend API:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 3. Frontend Setup

Open a new terminal window and navigate to the `frontend` folder:

```bash
cd frontend
npm install
npm run dev
```

- **Frontend Application:** [http://localhost:5173](http://localhost:5173)

---

## 🧪 Automated Testing & Verification

The platform includes comprehensive test suites across both backend and frontend layers:

### Backend Test Suites
Run the test suites from the **repository root**:

```bash
# Conversational First Aid & RAG validation
python backend/test_conversational_first_aid.py

# Real-Time WebSocket reliability
python backend/test_phase6_websocket_reliability.py

# Deterministic safety hardening & contraindication validator
python backend/test_first_aid_safety_hardening.py

# Emergency response reliability & state machine
python backend/test_phase5_emergency_response_reliability.py
```

*(Note: If you are already inside the `backend/` directory, omit the `backend/` prefix, e.g., `python test_conversational_first_aid.py`.)*

### Frontend Test Suites
Navigate to the `frontend` directory:

```bash
cd frontend

# Run unit & component tests (use npm.cmd on Windows PowerShell if execution policies restrict scripts)
npm test
# Windows PowerShell: npm.cmd test

# Verify production Vite build
npm run build
# Windows PowerShell: npm.cmd run build
```

---

## 🔐 Security & Privacy

- **Password Security:** Passwords stored using PBKDF2-HMAC-SHA256 with cryptographic salt.
- **Authentication:** Token-based session management with secure HMAC validation.
- **Access Control:** Multi-tenant household boundary isolation and Role-Based Access Control (RBAC).
- **Environment Isolation:** Sensitive environment credentials and database files excluded from source control.
- **First Aid Privacy:** Conversational history is maintained in client-side memory rather than unencrypted persistent storage.
- **Display Privacy:** Sensitive personal identifying information (phone numbers and email addresses) is dynamically masked to guard against shoulder-surfing.

---

## ⚠️ Important Limitations

FamilyConnect AI is an educational and portfolio prototype:

- **Not a Certified Medical Device:** The emergency triage model uses synthetic training scenarios and has not undergone clinical validation. It is intended for research, education, and prototyping.
- **No Substitute for Professional Care:** AI-generated or retrieved first-aid guidance must never replace professional medical attention or clinical diagnosis.
- **No Automatic Emergency Dispatch:** The platform does not automatically dispatch municipal ambulances or contact public emergency services such as 112 or 108.
- **Manual Calling Required:** Users must independently contact emergency authorities during live emergencies.
- **Simulated Notifications:** By default, email and SMS notifications run in simulated mock mode unless external telecom providers are explicitly configured.
- **GPS Availability:** Geolocation functionality depends on device hardware availability and explicit browser permissions.

---

## 🔮 Future Enhancements

- Live SMS, push, and emergency notification service integration.
- Advanced geographical responder live-tracking and navigation routing.
- Native mobile application builds (iOS / Android).
- Multilingual First Aid conversation support.
- Broader clinical emergency protocol datasets.
- Direct telemetry integration with certified emergency response centers.

---

## 🎯 Project Objective

The objective of FamilyConnect AI is to demonstrate how Artificial Intelligence, Machine Learning, Natural Language Processing, and real-time communication technologies can be unified to build a responsive, safe, and privacy-focused family emergency coordination platform.

---

## 👨‍💻 Development

**FamilyConnect AI** is an AI/ML and full-stack development portfolio project.

**Technology Focus:** Artificial Intelligence | Machine Learning | Natural Language Processing | Retrieval-Augmented Generation | Full-Stack Development

---

## 📄 License

A license has not yet been specified. Please check the repository's licensing status before reusing or distributing this project.
