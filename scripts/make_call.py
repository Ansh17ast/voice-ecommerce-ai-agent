import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

# Load environment variables from repository root .env
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

API_KEY = os.getenv("OMNIDIM_API_KEY")
AGENT_ID = os.getenv("OMNIDIM_AGENT_ID")
RAW_PHONE = os.getenv("DEFAULT_CUSTOMER_PHONE", "+15551234567")

# Clean phone number to standard E.164 format (e.g. +15551234567)
digits = "".join(filter(str.isdigit, RAW_PHONE))
if len(digits) == 10:
    clean_phone = f"+91{digits}"
elif digits.startswith("91") and len(digits) == 12:
    clean_phone = f"+{digits}"
else:
    clean_phone = f"+{digits}"

print("=== INITIATING OUTBOUND AI VOICE CALL ===")
print(f"Target Phone: {clean_phone}")
print(f"Agent ID: {AGENT_ID}")

if not API_KEY or not AGENT_ID:
    print("[ERROR] OMNIDIM_API_KEY or OMNIDIM_AGENT_ID is missing in .env")
    exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

body = {
    "agent_id": int(AGENT_ID),
    "to_number": clean_phone,
    "call_context": {
        "customer_name": "Valued Customer"
    },
    "metadata": {
        "source": "ecommerce_ai_agent_test"
    }
}

try:
    with httpx.Client(timeout=30) as client:
        print("\nDispatching call to OmniDimension API...")
        response = client.post(
            "https://backend.omnidim.io/api/v1/calls/dispatch",
            headers=headers,
            json=body
        )
        print(f"Status Code: {response.status_code}")
        print("Response:", response.text)
        
        if response.status_code in [200, 201]:
            print("\n[SUCCESS] Call dispatched successfully! Expect a call on your phone shortly.")
        else:
            print("\n[FAILED] Call dispatch returned non-200 status.")
except Exception as e:
    print(f"\n[ERROR] Exception while dispatching call: {e}")
