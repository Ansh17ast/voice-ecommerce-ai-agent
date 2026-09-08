import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure root package is in import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables from repository root .env
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

from whatsapp_service import check_instance_state, send_whatsapp_text

TEST_PHONE = os.getenv("DEFAULT_CUSTOMER_PHONE", "+15551234567")


async def main():
    print(f"=== TESTING WHATSAPP INTEGRATION ===")
    print(f"Target Phone: {TEST_PHONE}\n")

    # Step 1: Check Connection Status
    print("Checking Green API instance state...")
    status = await check_instance_state()
    print("Instance status:", status)

    if not status.get("authorized"):
        print("\n[!] Instance is not authorized yet.")
        print("Please ensure you have:")
        print("1. Created an instance on green-api.com")
        print("2. Added GREEN_API_ID_INSTANCE and GREEN_API_TOKEN in .env")
        print("3. Scanned the QR code with your WhatsApp app (Linked Devices)")
        return

    # Step 2: Send Test Message
    test_msg = (
        "🚀 *ElevateBox AI Agent - WhatsApp Test*\n\n"
        "Hey! This is a test message from your E-Commerce AI Voice & Lead Engine.\n"
        "WhatsApp connection is working successfully!\n\n"
        "Target number tested: " + TEST_PHONE
    )

    print("\nSending test message...")
    try:
        res = await send_whatsapp_text(TEST_PHONE, test_msg)
        print("[SUCCESS] Message Sent Successfully!")
        print("Response:", res)
    except Exception as e:
        print("[ERROR] Error sending message:", e)


if __name__ == "__main__":
    asyncio.run(main())
