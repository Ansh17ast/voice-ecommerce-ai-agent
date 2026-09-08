import sys
import os
import json
import asyncio
from pathlib import Path

# Ensure root package is in import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi.testclient import TestClient
from dotenv import load_dotenv

# Load environment variables from repository root .env
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

from main import app
from whatsapp_service import (
    normalize_call_context,
    build_hot_mid_call_message,
    build_post_call_message,
    extract_context_from_text,
    get_target_recipient,
    format_whatsapp_chat_id,
    TEST_WHATSAPP_NUMBER,
    MY_CONTACT_PHONE,
    MY_CONTACT_NAME,
    check_instance_state
)

client = TestClient(app)

def print_separator(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_1_customer_full_context():
    print_separator("TEST 1: Customer Full Context Follow-Up")
    customer_statement = (
        "I'm planning to sell clothes online, around 500 to 600 products. "
        "My budget is about 80,000 and I want to launch next month. "
        "I need payments, order tracking and inventory."
    )
    print(f"Customer Input: \"{customer_statement}\"")

    norm = normalize_call_context({"conversation": customer_statement})
    print("\nNormalized Context:")
    print(json.dumps(norm, indent=2))

    post_msg = build_post_call_message(norm)
    print("\nGenerated POST-CALL WhatsApp Message:")
    print("-" * 50)
    print(post_msg)
    print("-" * 50)

    # Verification rules
    assert "sell clothes online" in post_msg
    assert "500–600" in post_msg or "500 to 600" in post_msg
    assert "80,000" in post_msg
    assert "next month" in post_msg
    assert "payments" in post_msg
    assert "order tracking" in post_msg
    assert "inventory" in post_msg
    assert MY_CONTACT_PHONE in post_msg
    assert f"— {MY_CONTACT_NAME}" in post_msg

    print("\n>>> TEST 1 PASSED: All customer facts accurately preserved without hallucination.")


def test_2_minimal_store_no_inventions():
    print_separator("TEST 2: Customer with Minimal Statement ('I want an online store')")
    customer_statement = "I want an online store."
    print(f"Customer Input: \"{customer_statement}\"")

    norm = normalize_call_context({"conversation": customer_statement})
    print("\nNormalized Context:")
    print(json.dumps(norm, indent=2))

    post_msg = build_post_call_message(norm)
    print("\nGenerated POST-CALL WhatsApp Message:")
    print("-" * 50)
    print(post_msg)
    print("-" * 50)

    # Must NOT invent missing facts
    assert "products" not in post_msg.lower()
    assert "budget" not in post_msg.lower()
    assert "₹" not in post_msg
    assert "launch" not in post_msg.lower()
    assert "main requirements were" not in post_msg.lower()
    assert "online store" in post_msg.lower()
    assert MY_CONTACT_PHONE in post_msg

    print("\n>>> TEST 2 PASSED: Missing fields cleanly omitted. Zero hallucination.")


def test_3_planned_business_preservation():
    print_separator("TEST 3: Planned Business vs Existing Store Distinction")
    customer_statement = "I'm planning to sell clothes online."
    print(f"Customer Input: \"{customer_statement}\"")

    norm = normalize_call_context({"conversation": customer_statement})
    post_msg = build_post_call_message(norm)

    print("\nGenerated POST-CALL WhatsApp Message:")
    print("-" * 50)
    print(post_msg)
    print("-" * 50)

    # Critical rule: Do NOT say "You have a clothes store"
    assert "you have a clothes store" not in post_msg.lower()
    assert "sell clothes online" in post_msg
    assert "products" not in post_msg.lower()
    assert "budget" not in post_msg.lower()

    print("\n>>> TEST 3 PASSED: Correctly phrased as planning to sell, never claimed existing store.")


def test_4_vague_information():
    print_separator("TEST 4: Customer Gives Vague Information")
    customer_statement = "We might explore options sometime in the future."
    print(f"Customer Input: \"{customer_statement}\"")

    norm = normalize_call_context({"conversation": customer_statement})
    post_msg = build_post_call_message(norm)

    print("\nGenerated POST-CALL WhatsApp Message:")
    print("-" * 50)
    print(post_msg)
    print("-" * 50)

    # No invented fields
    assert "products" not in post_msg.lower()
    assert "budget" not in post_msg.lower()
    assert "₹" not in post_msg
    assert "main requirements were" not in post_msg.lower()
    assert MY_CONTACT_PHONE in post_msg

    print("\n>>> TEST 4 PASSED: Handled vague input safely without fabricating scope.")


def test_5_duplicate_call_id_protection():
    print_separator("TEST 5: Duplicate Protection Idempotency (/webhook/post-call)")
    dup_call_id = "test-dup-call-999"
    payload = {
        "event": "post_call",
        "call_id": dup_call_id,
        "what_they_sell": "clothing",
        "product_count": "around 500",
        "budget": "₹70,000",
        "timeline": "next month",
        "features": ["payments", "order tracking"],
        "phone": "+15551234567"
    }

    # First attempt: should send
    print("Submitting First Call:")
    res1 = client.post("/webhook/post-call", json=payload)
    print(f"Status Code 1: {res1.status_code}")
    data1 = res1.json()
    print("Response 1:", json.dumps(data1, indent=2))
    assert res1.status_code == 200
    assert data1["success"] is True
    assert data1["duplicate"] is False
    assert data1["status"] == "sent"

    # Second attempt with same call_id: should be blocked as duplicate
    print("\nSubmitting Duplicate Call (same call_id):")
    res2 = client.post("/webhook/post-call", json=payload)
    print(f"Status Code 2: {res2.status_code}")
    data2 = res2.json()
    print("Response 2:", json.dumps(data2, indent=2))
    assert res2.status_code == 200
    assert data2["success"] is True
    assert data2["duplicate"] is True
    assert data2["status"] == "already_sent"

    print("\n>>> TEST 5 PASSED: Idempotency enforced. Duplicate event safely ignored.")


def test_6_hot_lead_webhook_live():
    print_separator("TEST 6: Mid-Call HOT Lead Webhook (/webhook/hot-lead)")
    hot_payload = {
        "event": "hot_lead",
        "call_id": "test-hot-live-001",
        "lead_temperature": "HOT",
        "business_type": "clothes",
        "what_they_sell": "clothes",
        "product_count": "around 500–600",
        "budget": "about ₹80,000",
        "timeline": "next month",
        "features": [
            "payments",
            "order tracking",
            "inventory management",
            "a simple checkout"
        ],
        "important_context": "Customer asked what is needed to get started immediately.",
        "preferred_language": "English",
        "phone": "+15551234567"
    }

    res = client.post("/webhook/hot-lead", json=hot_payload)
    print(f"Status Code: {res.status_code}")
    data = res.json()
    print("Response:", json.dumps(data, indent=2))

    assert res.status_code == 200
    assert data.get("ok") is True
    assert data.get("status") == "sent"
    # Ensure zero semantic context leak back to the voice agent
    assert "generated_message" not in data
    assert "message" not in data
    assert "timestamps" not in data

    # Test Duplicate HOT with the same call_id
    print("\nSubmitting Duplicate HOT Call (same call_id):")
    res_dup = client.post("/webhook/hot-lead", json=hot_payload)
    print(f"Status Code: {res_dup.status_code}")
    data_dup = res_dup.json()
    print("Duplicate Response:", json.dumps(data_dup, indent=2))
    assert res_dup.status_code == 200
    assert data_dup.get("ok") is True
    assert data_dup.get("status") == "already_sent"
    assert "generated_message" not in data_dup

    # Check recipient safety
    expected_chat = format_whatsapp_chat_id(TEST_WHATSAPP_NUMBER)
    target_chat = get_target_recipient(hot_payload["phone"])
    assert target_chat == expected_chat

    print(f"\n>>> TEST 6 PASSED: Mid-call HOT message dispatched live to {TEST_WHATSAPP_NUMBER} & duplicate blocked.")


def test_7_post_call_webhook_live():
    print_separator("TEST 7: Post-Call Webhook with Attachments (/webhook/post-call)")
    post_payload = {
        "event": "post_call",
        "call_id": "test-post-live-002",
        "business_goal": "sell clothes online",
        "product_count": "around 500–600",
        "budget": "about ₹80,000",
        "timeline": "next month",
        "features": [
            "payments",
            "order tracking",
            "inventory"
        ],
        "phone": "+15551234567"
    }

    res = client.post("/webhook/post-call", json=post_payload)
    print(f"Status Code: {res.status_code}")
    data = res.json()
    print("Response:", json.dumps(data, indent=2))

    assert res.status_code == 200
    assert data["success"] is True
    assert data["action"] == "post_call"
    assert data["messageId"]
    assert data["attachments_count"] >= 1  # Architecture diagram and/or resume

    print("\nGenerated Post-Call WhatsApp text:")
    print("-" * 50)
    print(data.get("generated_message"))
    print("-" * 50)

    print(f"\n>>> TEST 7 PASSED: Full post-call summary + attachments dispatched live to {TEST_WHATSAPP_NUMBER}.")


if __name__ == "__main__":
    print("\n" + "#" * 70)
    print(" RUNNING ELEVATEBOX VOICE E-COMMERCE AI AGENT VERIFICATION TEST SUITE ")
    print(f" Target Test Recipient: {TEST_WHATSAPP_NUMBER}")
    print("#" * 70)

    test_1_customer_full_context()
    test_2_minimal_store_no_inventions()
    test_3_planned_business_preservation()
    test_4_vague_information()
    test_5_duplicate_call_id_protection()
    test_6_hot_lead_webhook_live()
    test_7_post_call_webhook_live()

    print("\n" + "#" * 70)
    print(" ALL 7 TESTS COMPLETED AND FULLY VERIFIED! ")
    print("#" * 70 + "\n")
