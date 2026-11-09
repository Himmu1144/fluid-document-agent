"""A small, made-up set of company records for `lookup_mock_data` (the brief allows mock data).

The company: Meridian Bank & Insurance, a mid-size Indian bank with an insurance arm.
Each record has tags; the lookup tool returns the records whose tags match the task.
"""

RECORDS = [
    {
        "id": "team-kyc",
        "tags": ["kyc", "onboarding", "attendees", "sync"],
        "title": "KYC Onboarding team",
        "data": {
            "members": [
                {"name": "Priya Nair", "role": "KYC Operations Lead (chair)"},
                {"name": "Rahul Mehta", "role": "Compliance Officer"},
                {"name": "Ananya Iyer", "role": "Product Manager, Digital Onboarding"},
                {"name": "Vikram Singh", "role": "Onboarding Analyst"},
                {"name": "Sneha Kulkarni", "role": "IT Support Engineer"},
            ],
        },
    },
    {
        "id": "meeting-kyc-sync",
        "tags": ["kyc", "onboarding", "meeting", "sync", "weekly", "minutes", "notes", "agenda"],
        "title": "Weekly KYC onboarding sync: raw notes (latest)",
        "data": {
            "date": "Thursday 5 November 2026, 11:00–11:45 IST, Teams",
            "attendees": ["Priya Nair", "Rahul Mehta", "Ananya Iyer", "Vikram Singh"],
            "apologies": ["Sneha Kulkarni (on leave)"],
            "agenda": ["Onboarding backlog", "Video KYC drop-offs", "RBI circular on periodic re-KYC", "AOB"],
            "notes": [
                "Backlog: 1,240 applications pending, up from 860 last week; Diwali campaign volume.",
                "Turnaround time is 3.1 days against a 2-day target.",
                "Video KYC: 18% of customers drop off at the document-upload step on Android.",
                "Ananya: the Android upload bug is fixed in app release 4.12, due 12 Nov.",
                "Rahul: the RBI circular on periodic re-KYC needs our policy updated by 30 Nov.",
                "Agreed to add two temporary analysts for three weeks to clear the backlog.",
                "Vikram to pilot an auto-reminder to customers with incomplete applications.",
                "Next sync: Thursday 12 November 2026, 11:00 IST.",
            ],
        },
    },
    {
        "id": "voice-platform",
        "tags": ["voice", "bot", "platform", "speech", "languages", "asr", "tts", "architecture", "technical"],
        "title": "Existing voice AI platform",
        "data": {
            "platform": "In-house voice agent stack: Deepgram speech-to-text, an LLM for dialogue, Twilio telephony",
            "languages_ready": ["English", "Hindi"],
            "languages_in_beta": ["Marathi", "Tamil"],
            "languages_not_supported": ["Bengali", "Telugu"],
            "note": "Each new language needs about 1 week of prompt tuning and testing with native speakers.",
            "integrations": ["Claims core system (REST API)", "CRM", "SMS gateway"],
        },
    },
    {
        "id": "team-ai",
        "tags": ["ai", "voice", "bot", "engineering", "engineers", "team", "resources", "people", "staffing", "delivery"],
        "title": "AI & Automation team (delivers voice and chat bots)",
        "data": {
            "members": [
                {"name": "Arjun Rao", "role": "Engineering Manager, AI & Automation"},
                {"name": "Meera Joshi", "role": "Senior ML Engineer (speech)"},
                {"name": "Karan Desai", "role": "Backend Engineer (integrations)"},
                {"name": "Fatima Shaikh", "role": "QA Engineer"},
            ],
            "availability": "Two engineers and one QA can start next week; the speech engineer is shared with another project at 50%.",
        },
    },
    {
        "id": "claims-line",
        "tags": ["claims", "insurance", "call", "contact", "centre", "volume", "background", "problem"],
        "title": "Insurance claims line: current state",
        "data": {
            "calls_per_month": 42000,
            "share_status_queries": "61% of calls are claim-status checks",
            "average_wait": "7 minutes at peak",
            "agents": 35,
            "cost_per_call_inr": 85,
        },
    },
    {
        "id": "rates",
        "tags": ["cost", "costs", "budget", "rates", "pricing", "estimate", "staffing", "resources"],
        "title": "Standard internal rates (INR)",
        "data": {
            "engineer_day_rate": 9000,
            "qa_day_rate": 6000,
            "language_specialist_day_rate": 5000,
            "project_manager_day_rate": 8000,
            "telephony_per_minute": 0.6,
            "speech_and_llm_per_minute": 1.4,
            "contingency_percent": 10,
        },
    },
    {
        "id": "past-projects",
        "tags": ["past", "projects", "previous", "case", "reference", "timeline"],
        "title": "Past automation projects",
        "data": [
            {"name": "Credit card voice bot (English, Hindi)", "duration_weeks": 6, "cost_inr": 780000,
             "result": "38% of calls fully automated"},
            {"name": "Loan status WhatsApp bot", "duration_weeks": 4, "cost_inr": 420000,
             "result": "Handles 55% of status queries"},
        ],
    },
]
