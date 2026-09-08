import os
import json
import logging
import datetime
from typing import Optional, List, Dict, Any
import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from classifier import classify_lead
from whatsapp_service import (
    check_instance_state,
    send_whatsapp_text,
    send_hot_mid_call_whatsapp,
    send_post_call_whatsapp,
    format_whatsapp_chat_id,
    sanitize_for_logging,
    DEV_RECIPIENT_CHAT_ID,
    TEST_WHATSAPP_NUMBER,
    logger
)

load_dotenv()

app = FastAPI(
    title="E-Commerce AI Voice & WhatsApp Lead Engine",
    description="Backend service integrating OmniDimension AI voice agent with Green API WhatsApp delivery.",
    version="1.1.0"
)


# --------------------------------------------------
# REQUEST & RESPONSE MODELS
# --------------------------------------------------

class TestWhatsAppRequest(BaseModel):
    message: Optional[str] = "Test message from the E-Commerce AI Agent."


class WhatsAppRequest(BaseModel):
    phone: Optional[str] = None
    to: Optional[str] = None
    name: Optional[str] = None
    message: Optional[str] = None


class StartCallRequest(BaseModel):
    phone: Optional[str] = None
    customer_name: Optional[str] = None


class Lead(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    business: Optional[str] = None
    products: Optional[int] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    barrier: Optional[str] = None





class HotLeadPayload(BaseModel):
    model_config = {"extra": "allow"}
    event: Optional[Any] = "hot_lead"
    call_id: Optional[Any] = None
    session_id: Optional[Any] = None
    lead_temperature: Optional[Any] = None
    business_type: Optional[Any] = None
    what_they_sell: Optional[Any] = None
    business_goal: Optional[Any] = None
    product_count: Optional[Any] = None
    budget: Optional[Any] = None
    timeline: Optional[Any] = None
    features: Any = Field(default_factory=list)
    important_context: Optional[Any] = None
    preferred_language: Optional[Any] = None
    phone: Optional[Any] = None
    summary: Optional[Any] = None
    conversation: Optional[Any] = None
    fullConversation: Optional[Any] = None
    transcript: Optional[Any] = None


class PostCallPayload(BaseModel):
    model_config = {"extra": "allow"}
    event: Optional[Any] = "post_call"
    call_id: Optional[Any] = None
    session_id: Optional[Any] = None
    phone: Optional[Any] = None
    summary: Optional[Any] = None
    business_type: Optional[Any] = None
    what_they_sell: Optional[Any] = None
    business_goal: Optional[Any] = None
    product_count: Optional[Any] = None
    budget: Optional[Any] = None
    timeline: Optional[Any] = None
    features: Any = Field(default_factory=list)
    extracted_variables: Optional[Any] = None
    fullConversation: Optional[Any] = None
    conversation: Optional[Any] = None
    transcript: Optional[Any] = None


# --------------------------------------------------
# HEALTH & STATUS
# --------------------------------------------------

@app.get("/health")
async def health():
    wa_status = await check_instance_state()
    return {
        "status": "ok",
        "service": "ecommerce-ai-agent",
        "whatsapp_authorized": wa_status.get("authorized", False),
        "omnidim_configured": bool(os.getenv("OMNIDIM_API_KEY") and os.getenv("OMNIDIM_AGENT_ID"))
    }


@app.get("/whatsapp/status")
async def get_whatsapp_status():
    return await check_instance_state()


# --------------------------------------------------
# TEST ENDPOINT (DEV SAFETY STRICT TO DEV_RECIPIENT_CHAT_ID)
# --------------------------------------------------

@app.post("/test/whatsapp")
async def test_whatsapp(request: TestWhatsAppRequest):
    """
    Development-only endpoint: sends a direct WhatsApp test message strictly to DEV_RECIPIENT_CHAT_ID.
    """
    dev_chat_id = DEV_RECIPIENT_CHAT_ID
    target_chat_id = format_whatsapp_chat_id(dev_chat_id)
    msg = request.message or "Test message from the E-Commerce AI Agent."

    logger.info(f"[TEST] /test/whatsapp invoked -> recipient: {target_chat_id}")
    
    try:
        res = await send_whatsapp_text(target_chat_id, msg)
        msg_id = res.get("idMessage", "")
        return {
            "success": True,
            "recipient": dev_chat_id,
            "messageId": msg_id,
            "greenApiResponse": res
        }
    except Exception as exc:
        logger.error(f"[TEST] /test/whatsapp failed: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
                "statusCode": 500
            }
        )


# --------------------------------------------------
# OMNIDIMENSION HOT MID-CALL WEBHOOK / TOOL
# --------------------------------------------------

@app.post("/webhook/hot-lead")
@app.post("/webhook/omnidim")
async def webhook_hot_lead(request: Request):
    """
    Mid-call webhook triggered by OmniDimension when high buying intent is detected.
    Dispatches dynamic WhatsApp message while the live phone call continues.
    """
    t2_time = datetime.datetime.now().isoformat()
    logger.info(f"[TIMESTAMP: T2] [HOT-WEBHOOK] Webhook received at {t2_time}")

    try:
        raw_body = await request.json()
    except Exception as e:
        logger.warning(f"[OMNI] Unable to parse JSON from hot-lead request: {e}")
        raw_body = {}

    logger.info(f"[OMNI] Raw incoming hot-lead payload: {json.dumps(sanitize_for_logging(raw_body))}")

    context_dict = dict(raw_body) if isinstance(raw_body, dict) else {}
    for container_key in ("call_report", "metadata", "call_context", "context"):
        container = context_dict.get(container_key)
        if isinstance(container, dict):
            for k, v in container.items():
                if k not in context_dict or context_dict[k] is None:
                    context_dict[k] = v

    call_id = str(
        context_dict.get("call_id")
        or context_dict.get("call_sid")
        or context_dict.get("session_id")
        or context_dict.get("id")
        or "unknown_call"
    )
    event_type = context_dict.get("event") or "hot_lead"

    logger.info(f"[OMNI] event type: {event_type}")
    logger.info(f"[OMNI] call/session id: {call_id}")
    logger.info(f"[OMNI] payload validated and normalized")

    try:
        # Fast execution for Green API delivery (<1s)
        result = await send_hot_mid_call_whatsapp(context_dict)
        msg_id = result.get("messageId") or result.get("cached_result", {}).get("messageId")

        t5_time = datetime.datetime.now().isoformat()
        logger.info(f"[TIMESTAMP: T5] [HOT-WEBHOOK] Webhook HTTP 200 response returned at {t5_time}")
        logger.info(
            f"[HOT-WEBHOOK] Completed for call_id={call_id}: status={result.get('status')}, "
            f"duplicate={result.get('duplicate')}, msg_id={msg_id}"
        )

        # Return strictly minimal response to voice agent to eliminate semantic context bleed,
        # duplicate assistant turns, and premature call termination.
        resp_status = result.get("status", "sent" if not result.get("duplicate") else "already_sent")
        return {
            "ok": True,
            "status": resp_status
        }
    except Exception as exc:
        logger.error(f"[OMNI] Error processing hot-lead webhook: {exc}")
        return JSONResponse(
            status_code=502,
            content={"ok": False, "status": "failed"}
        )



# --------------------------------------------------
# POST-CALL WEBHOOK / ACTION
# --------------------------------------------------

@app.post("/webhook/post-call")
async def webhook_post_call(request: Request):
    """
    Post-call webhook triggered upon call completion.
    Dispatches contextual project summary + architectural attachments.
    """
    t6_time = datetime.datetime.now().isoformat()
    logger.info(f"[TIMESTAMP: T6] [POST-CALL] Webhook received at {t6_time}")

    try:
        raw_body = await request.json()
    except Exception as e:
        logger.warning(f"[OMNI] Unable to parse JSON from post-call request: {e}")
        raw_body = {}

    logger.info(f"[OMNI] Raw post-call payload: {json.dumps(sanitize_for_logging(raw_body))}")

    context_dict = dict(raw_body) if isinstance(raw_body, dict) else {}
    for container_key in ("call_report", "metadata", "call_context", "context"):
        container = context_dict.get(container_key)
        if isinstance(container, dict):
            for k, v in container.items():
                if k not in context_dict or context_dict[k] is None:
                    context_dict[k] = v

    call_id = str(
        context_dict.get("call_id")
        or context_dict.get("call_sid")
        or context_dict.get("session_id")
        or context_dict.get("id")
        or "unknown_call"
    )
    event_type = context_dict.get("event") or "post_call"

    logger.info(f"[OMNI] post-call event type: {event_type}")
    logger.info(f"[OMNI] post-call call/session id: {call_id}")

    # Handle extracted variables if sent in OmniDimension post-call format
    ev = context_dict.get("extracted_variables")
    if ev and isinstance(ev, dict):
        for k, v in ev.items():
            if v and v != "NA":
                if k not in context_dict or not context_dict[k]:
                    context_dict[k] = v

    try:
        result = await send_post_call_whatsapp(context_dict)
        msg_id = result.get("messageId") or result.get("cached_result", {}).get("messageId")
        return {
            "success": True,
            "status": result.get("status", "sent"),
            "duplicate": result.get("duplicate", False),
            "call_id": call_id,
            "messageId": msg_id,
            "action": "post_call",
            "attachments_count": len(result.get("attachments_sent", [])),
            "generated_message": result.get("generated_message"),
            "timestamp_t6": t6_time
        }
    except Exception as exc:
        logger.error(f"[OMNI] Error processing post-call webhook: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to deliver post-call WhatsApp: {str(exc)}"
        )


# --------------------------------------------------
# GENERAL WHATSAPP DISPATCH
# --------------------------------------------------

@app.post("/send-whatsapp")
async def send_whatsapp(payload: WhatsAppRequest):
    recipient = payload.to or payload.phone or TEST_WHATSAPP_NUMBER
    message_content = payload.message or "Hello from E-Commerce AI Lead Engine!"

    try:
        res = await send_whatsapp_text(recipient, message_content)
        return {
            "success": True,
            "provider": "green-api",
            "messageId": res.get("idMessage", ""),
            "response": res
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Green API delivery error: {str(exc)}"
        )


# --------------------------------------------------
# LEAD CLASSIFICATION & ANALYSIS
# --------------------------------------------------

@app.post("/lead")
def receive_lead(lead: Lead):
    result = classify_lead(lead.model_dump())
    return {
        "success": True,
        "classification": result["classification"],
        "reason": result["reason"],
        "lead": lead.model_dump()
    }





# --------------------------------------------------
# OMNIDIMENSION OUTBOUND CALL
# --------------------------------------------------

@app.post("/start-call")
async def start_call(payload: StartCallRequest):
    api_key = os.getenv("OMNIDIM_API_KEY")
    agent_id = os.getenv("OMNIDIM_AGENT_ID")

    if not api_key:
        raise HTTPException(status_code=500, detail="OMNIDIM_API_KEY is not configured.")
    if not agent_id:
        raise HTTPException(status_code=500, detail="OMNIDIM_AGENT_ID is not configured.")

    recipient = payload.phone or os.getenv("DEFAULT_CUSTOMER_PHONE") or TEST_WHATSAPP_NUMBER
    digits = "".join(filter(str.isdigit, recipient))
    if len(digits) == 10:
        clean_phone = f"+91{digits}"
    elif digits.startswith("91") and len(digits) == 12:
        clean_phone = f"+{digits}"
    else:
        clean_phone = f"+{digits}"

    body = {
        "agent_id": int(agent_id),
        "to_number": clean_phone,
        "call_context": {
            "customer_name": payload.customer_name or "Valued Customer"
        },
        "metadata": {
            "source": "ecommerce_ai_agent"
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://backend.omnidim.io/api/v1/calls/dispatch",
                headers=headers,
                json=body
            )
            response_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw_response": response.text}
            
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response_data)
                
            return {
                "success": True,
                "message": "Call dispatched to OmniDimension.",
                "omnidimension_response": response_data
            }
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach OmniDimension: {str(exc)}")