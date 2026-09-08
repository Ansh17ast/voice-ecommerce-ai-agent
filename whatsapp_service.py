import os
import re
import json
import logging
import datetime
from typing import Dict, Any, Optional, List, Set
import httpx
from dotenv import load_dotenv

load_dotenv()

# Logger setup
logger = logging.getLogger("ecommerce_ai_agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

GREEN_API_HOST = os.getenv("GREEN_API_HOST", "https://api.green-api.com").rstrip("/")
GREEN_API_ID_INSTANCE = os.getenv("GREEN_API_ID_INSTANCE")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")

# Safety & Destination Configuration
TEST_WHATSAPP_NUMBER = os.getenv("TEST_WHATSAPP_NUMBER", "15551234567")
DEV_RECIPIENT_CHAT_ID = os.getenv("DEV_RECIPIENT_CHAT_ID", "15551234567@c.us")
MY_CONTACT_PHONE = os.getenv("MY_CONTACT_PHONE", "+1-555-123-4567")
MY_CONTACT_NAME = os.getenv("MY_CONTACT_NAME", "Alex")
TRIAL_MODE = os.getenv("TRIAL_MODE", "true").lower() in ("true", "1", "yes")

# In-memory idempotency cache for duplicate protection
PROCESSED_HOT_CALLS: Dict[str, Dict[str, Any]] = {}
IN_FLIGHT_HOT_CALLS: Set[str] = set()
PROCESSED_POST_CALLS: Dict[str, Dict[str, Any]] = {}


def sanitize_for_logging(data: Any) -> Any:
    """
    Ensure no secrets, tokens, or authorization headers are logged.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(secret_term in k.lower() for secret_term in ["token", "secret", "key", "auth", "password"]):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_for_logging(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_logging(i) for i in data]
    return data


def format_whatsapp_chat_id(phone_or_chat_id: str) -> str:
    """
    Format any phone number or chatId into Green API valid chatId format.
    Green API expects standard digits format with country code (e.g. 15551234567@c.us).
    """
    clean_str = str(phone_or_chat_id).strip()
    digits = "".join(filter(str.isdigit, clean_str))
    
    # Prepend India country code 91 if 10 digits
    if len(digits) == 10:
        digits = "91" + digits
    elif digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]
    
    return f"{digits}@c.us"


def get_target_recipient(provided_phone: Optional[str] = None) -> str:
    """
    Determine safe recipient chatId.
    SAFETY: During trial phase (TRIAL_MODE=True), ALL messages strictly go to
    TEST_WHATSAPP_NUMBER to guarantee real caller numbers are never messaged.
    """
    if TRIAL_MODE:
        target = TEST_WHATSAPP_NUMBER
    else:
        target = provided_phone or TEST_WHATSAPP_NUMBER
    return format_whatsapp_chat_id(target)


async def check_instance_state() -> Dict[str, Any]:
    """
    Check if the Green API instance credentials are configured and reachable.
    """
    if not GREEN_API_ID_INSTANCE or not GREEN_API_TOKEN:
        return {"authorized": False, "error": "GREEN_API_ID_INSTANCE or GREEN_API_TOKEN not configured."}

    url = f"{GREEN_API_HOST}/waInstance{GREEN_API_ID_INSTANCE}/getStateInstance/{GREEN_API_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                state = data.get("stateInstance")
                return {
                    "authorized": state == "authorized",
                    "stateInstance": state,
                    "instance_id": GREEN_API_ID_INSTANCE,
                    "host": GREEN_API_HOST
                }
            return {
                "authorized": False,
                "status_code": resp.status_code,
                "error": resp.text
            }
    except Exception as e:
        return {"authorized": False, "error": str(e)}


async def send_whatsapp_text(phone_or_chat_id: str, text: str) -> Dict[str, Any]:
    """
    Send a direct text message to a WhatsApp recipient via Green API.
    """
    if not GREEN_API_ID_INSTANCE or not GREEN_API_TOKEN:
        raise RuntimeError("Green API credentials missing in .env (GREEN_API_ID_INSTANCE, GREEN_API_TOKEN).")

    chat_id = format_whatsapp_chat_id(phone_or_chat_id)
    url = f"{GREEN_API_HOST}/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_TOKEN}"
    
    payload = {
        "chatId": chat_id,
        "message": text
    }

    logger.info(f"[WA] Green API request started -> recipient: {chat_id}")
    
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        status_code = response.status_code
        logger.info(f"[WA] Green API response status: {status_code}")
        
        try:
            resp_data = response.json()
            safe_resp = sanitize_for_logging(resp_data)
            logger.info(f"[WA] Green API response body: {json.dumps(safe_resp)}")
        except Exception:
            resp_data = {"raw_response": response.text}
            logger.info(f"[WA] Green API raw response: {response.text[:200]}")
            
        if status_code >= 400:
            logger.error(f"[WA] Green API error: HTTP {status_code} - {resp_data}")
            raise RuntimeError(f"Green API request failed with status {status_code}: {resp_data}")

        msg_id = resp_data.get("idMessage", "")
        logger.info(f"[WA] send successful, message id: {msg_id}")
        return resp_data


async def send_whatsapp_file(phone_or_chat_id: str, file_path: str, filename: str, caption: str = "") -> Dict[str, Any]:
    """
    Send a local file (Architecture Diagram or Resume PDF) via Green API.
    """
    if not GREEN_API_ID_INSTANCE or not GREEN_API_TOKEN:
        raise RuntimeError("Green API credentials missing in .env (GREEN_API_ID_INSTANCE, GREEN_API_TOKEN).")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    chat_id = format_whatsapp_chat_id(phone_or_chat_id)
    url = f"{GREEN_API_HOST}/waInstance{GREEN_API_ID_INSTANCE}/sendFileByUpload/{GREEN_API_TOKEN}"

    logger.info(f"[WA] Green API file upload started -> recipient: {chat_id}, file: {filename}")

    async with httpx.AsyncClient(timeout=30) as client:
        with open(file_path, "rb") as f:
            files = {"file": (filename, f)}
            data = {"chatId": chat_id, "caption": caption}
            response = await client.post(url, data=data, files=files)
            
            logger.info(f"[WA] Green API file upload response status: {response.status_code}")
            try:
                resp_data = response.json()
            except Exception:
                resp_data = {"raw_response": response.text}

            if response.status_code >= 400:
                logger.error(f"[WA] File upload failed: {resp_data}")
                raise RuntimeError(f"File send failed: {resp_data}")

            msg_id = resp_data.get("idMessage", "")
            logger.info(f"[WA] File send successful, message id: {msg_id}")
            return resp_data


# --------------------------------------------------
# CONTEXT EXTRACTION & NORMALIZATION
# --------------------------------------------------

def clean_value(val: Any) -> Optional[str]:
    """Return string value if valid, or None if empty / NA / placeholder."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("na", "n/a", "none", "null", "not provided", "unspecified"):
        return None
    return s


def extract_context_from_text(text: str) -> Dict[str, Any]:
    """
    Safely extract confirmed customer facts from text transcripts or summaries.
    Does NOT invent unmentioned information.
    """
    extracted: Dict[str, Any] = {}
    lower = text.lower()

    # 1. Planned selling / Business goal
    m_planned = re.search(r"planning\s+to\s+sell\s+([a-zA-Z\s]+?)\s+online", text, re.IGNORECASE)
    if m_planned:
        item = m_planned.group(1).strip()
        extracted["what_they_sell"] = item
        extracted["business_goal"] = f"sell {item} online"
    else:
        m_sell = re.search(r"\bsell\s+([a-zA-Z\s]+?)\s+online\b", text, re.IGNORECASE)
        if m_sell:
            item = m_sell.group(1).strip()
            extracted["what_they_sell"] = item
            extracted["business_goal"] = f"sell {item} online"
        elif "online store" in lower or "ecommerce store" in lower or "e-commerce store" in lower:
            extracted["business_goal"] = "set up an online store"
        elif "online website" in lower or "e-commerce website" in lower:
            extracted["business_goal"] = "launch an e-commerce website"

    # 2. Product count
    m_prod = re.search(r"(around|approx\.?|approximately|roughly)?\s*(\d+(?:\s*(?:to|-|–)\s*\d+)?)\s*products?", text, re.IGNORECASE)
    if m_prod:
        prefix = m_prod.group(1)
        cnt = m_prod.group(2).strip().replace(" to ", "–").replace("-", "–")
        extracted["product_count"] = f"around {cnt}" if prefix or "–" in cnt else cnt
    else:
        m_num_only = re.search(r"\b(\d+(?:\s*(?:to|-|–)\s*\d+)?)\s*products?\b", text, re.IGNORECASE)
        if m_num_only:
            extracted["product_count"] = m_num_only.group(1).strip().replace(" to ", "–").replace("-", "–")

    # 3. Budget
    m_budget = re.search(r"(?:budget\s+(?:is\s+)?(?:of\s+)?|approx\.?|about|roughly)?\s*(?:₹|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,7})", text, re.IGNORECASE)
    if ("budget" in lower or "₹" in text or "rs" in lower) and m_budget:
        snippet = text[m_budget.start():m_budget.start() + 40]
        num_m = re.search(r"([0-9,]+)", snippet)
        if num_m:
            raw_n = num_m.group(1).replace(",", "")
            try:
                formatted_n = f"{int(raw_n):,}"
                extracted["budget"] = f"about ₹{formatted_n}"
            except Exception:
                extracted["budget"] = f"about ₹{num_m.group(1)}"

    # 4. Timeline
    m_time = re.search(r"\b(next\s+month|next\s+week|this\s+month|\d+\s+(?:days?|weeks?|months?))\b", text, re.IGNORECASE)
    if m_time and any(t_word in lower for t_word in ["launch", "month", "week", "timeline", "target", "start"]):
        extracted["timeline"] = m_time.group(1).strip()

    # 5. Features
    feature_patterns = [
        (r"\b(online\s+payments?|payments?)\b", "payments"),
        (r"\b(order\s+tracking|tracking)\b", "order tracking"),
        (r"\b(inventory\s+management|inventory)\b", "inventory management"),
        (r"\b(simple\s+checkout|checkout)\b", "a simple checkout"),
        (r"\b(customer\s+accounts?|user\s+accounts?)\b", "customer accounts"),
        (r"\b(whatsapp(?:\s+integration)?)\b", "WhatsApp integration"),
        (r"\b(shipping|delivery)\b", "shipping integration"),
    ]
    feats = []
    for pat, name in feature_patterns:
        if re.search(pat, text, re.IGNORECASE):
            if not any(name in f or f in name for f in feats):
                feats.append(name)
    if feats:
        extracted["features"] = feats

    return extracted


def normalize_call_context(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map raw incoming webhook payload from OmniDimension or custom triggers
    into a standardized, clean context object:
    {
      "business_goal": "...",
      "what_they_sell": "...",
      "product_count": "...",
      "budget": "...",
      "timeline": "...",
      "features": [...],
      "important_context": "...",
      "customer_phone": "...",
      "customer_name": "...",
      "call_id": "..."
    }
    """
    # Make a shallow copy so we don't mutate input
    payload_data = dict(data) if isinstance(data, dict) else {}

    # Unpack nested containers if present (OmniDimension call_report, metadata, call_context)
    for container_key in ("call_report", "metadata", "call_context", "context"):
        container = payload_data.get(container_key)
        if isinstance(container, dict):
            for k, v in container.items():
                if k not in payload_data or payload_data[k] is None:
                    payload_data[k] = v

    normalized: Dict[str, Any] = {
        "business_goal": None,
        "what_they_sell": None,
        "product_count": None,
        "budget": None,
        "timeline": None,
        "features": [],
        "important_context": None,
        "customer_phone": None,
        "customer_name": None,
        "call_id": None
    }

    # 1. Unpack extracted_variables if provided by OmniDimension
    ev = payload_data.get("extracted_variables")
    ev_dict = {}
    if isinstance(ev, dict):
        ev_dict = ev
    elif isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict) and "key" in item:
                ev_dict[item.get("key")] = item.get("value")

    # Combine data sources with priority: direct field -> ev_dict
    def get_field(*keys):
        for k in keys:
            v = clean_value(payload_data.get(k))
            if v is not None:
                return v
            v = clean_value(ev_dict.get(k))
            if v is not None:
                return v
        return None

    normalized["call_id"] = get_field("call_id", "call_sid", "session_id", "id", "call_recording_id", "call_request_id") or "unknown_call"
    normalized["customer_phone"] = get_field("phone", "customer_phone", "to_number", "to", "phone_number", "customer_number")
    normalized["customer_name"] = get_field("customer_name", "name")
    normalized["what_they_sell"] = get_field("what_they_sell", "business_type", "business")
    normalized["business_goal"] = get_field("business_goal")
    normalized["product_count"] = get_field("product_count", "products")
    normalized["budget"] = get_field("budget")
    normalized["timeline"] = get_field("timeline", "launch_timeline")
    normalized["important_context"] = get_field("important_context", "summary", "notes")

    # Handle features list or string
    raw_feats = payload_data.get("features") or ev_dict.get("important_features") or ev_dict.get("features") or payload_data.get("important_features")
    if isinstance(raw_feats, list):
        normalized["features"] = [str(f).strip() for f in raw_feats if clean_value(f)]
    elif isinstance(raw_feats, str) and clean_value(raw_feats):
        parts = [f.strip() for f in raw_feats.split(",") if clean_value(f)]
        normalized["features"] = parts

    # 2. Text fallback extraction: parse conversation or summary if fields are missing
    text_source = (
        payload_data.get("summary")
        or payload_data.get("fullConversation")
        or payload_data.get("full_conversation")
        or payload_data.get("conversation")
        or payload_data.get("transcript")
    )
    if text_source and isinstance(text_source, str):
        parsed = extract_context_from_text(text_source)
        if not normalized["what_they_sell"] and parsed.get("what_they_sell"):
            normalized["what_they_sell"] = parsed["what_they_sell"]
        if not normalized["business_goal"] and parsed.get("business_goal"):
            normalized["business_goal"] = parsed["business_goal"]
        if not normalized["product_count"] and parsed.get("product_count"):
            normalized["product_count"] = parsed["product_count"]
        if not normalized["budget"] and parsed.get("budget"):
            normalized["budget"] = parsed["budget"]
        if not normalized["timeline"] and parsed.get("timeline"):
            normalized["timeline"] = parsed["timeline"]
        if not normalized["features"] and parsed.get("features"):
            normalized["features"] = parsed["features"]

    # 3. Clean and normalize budget formatting
    if normalized["budget"]:
        b = str(normalized["budget"]).strip()
        if re.search(r"^\d+$", b):
            normalized["budget"] = f"about ₹{int(b):,}"

    # 4. Clean and normalize product count
    if normalized["product_count"]:
        p = str(normalized["product_count"]).strip()
        p = p.replace(" to ", "–").replace("-", "–")
        normalized["product_count"] = p

    return normalized


def format_features_natural(features: Any) -> str:
    """Format feature list naturally: 'payments, order tracking and inventory management'."""
    if not features:
        return ""
    if isinstance(features, str):
        parts = [f.strip() for f in features.split(",") if clean_value(f)]
        features = parts
    if not isinstance(features, list) or len(features) == 0:
        return ""
    cleaned = [str(f).strip() for f in features if clean_value(f)]
    if len(cleaned) == 0:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])} and {cleaned[-1]}"


# --------------------------------------------------
# DYNAMIC MESSAGE BUILDERS
# --------------------------------------------------

def build_hot_mid_call_message(context: Dict[str, Any]) -> str:
    """
    Construct dynamic, contextual HOT mid-call message from actual conversation details.
    Triggered DURING the active voice call when high buying intent is detected.
    Does NOT invent facts, does not include HOT/WARM/COLD, does not sound like CRM.
    """
    what_they_sell = context.get("what_they_sell")
    business_goal = context.get("business_goal")
    product_count = context.get("product_count")
    budget = context.get("budget")
    timeline = context.get("timeline")
    features = context.get("features", [])

    lines = ["Hi, thanks for discussing your e-commerce requirement with me.", ""]

    # Build primary requirement sentence
    lead_clause = ""
    if what_they_sell:
        lead_clause = f"you're planning to sell {what_they_sell} online"
    elif business_goal:
        lead_clause = f"you're looking to {business_goal}"
    else:
        lead_clause = "you're looking to launch an e-commerce website"

    clauses = []
    if product_count:
        p_val = str(product_count).strip()
        if not p_val.lower().startswith("around") and not p_val.lower().startswith("approx"):
            clauses.append(f"around {p_val} products" if "products" not in p_val.lower() else f"around {p_val}")
        else:
            clauses.append(f"{p_val} products" if "products" not in p_val.lower() else p_val)

    if budget:
        b_val = str(budget).strip()
        if not b_val.lower().startswith("about") and not b_val.lower().startswith("around") and not b_val.lower().startswith("a budget"):
            clauses.append(f"a budget of about {b_val}" if "₹" not in b_val and "rs" not in b_val.lower() else f"a budget of {b_val}")
        elif not b_val.lower().startswith("a budget"):
            clauses.append(f"a budget of {b_val}")
        else:
            clauses.append(b_val)

    if timeline:
        t_val = str(timeline).strip()
        if not t_val.lower().startswith("a target launch") and not t_val.lower().startswith("target launch"):
            clauses.append(f"a target launch {t_val}")
        else:
            clauses.append(t_val)

    if clauses:
        if len(clauses) == 1:
            details_str = f" with {clauses[0]}"
        elif len(clauses) == 2:
            details_str = f" with {clauses[0]} and {clauses[1]}"
        else:
            details_str = f" with {', '.join(clauses[:-1])}, and {clauses[-1]}"
        lines.append(f"You mentioned {lead_clause}{details_str}.")
    else:
        lines.append(f"You mentioned {lead_clause}.")

    # Features clause
    feat_text = format_features_natural(features)
    if feat_text:
        lines.append(f"Your key requirements include {feat_text}.")

    lines.append("")
    lines.append(f"— {MY_CONTACT_NAME}\n📞 {MY_CONTACT_PHONE}")

    return "\n".join(lines).strip()


def build_post_call_message(context: Dict[str, Any]) -> str:
    """
    Construct dynamic, contextual POST-CALL follow-up WhatsApp message.
    Sent after call ends, generated from ACTUAL conversation data.
    Structure:
    Hi, thanks for speaking with me.
    You mentioned that you're looking to {{business_goal_or_requirement}}, with around {{product_count}} products, a budget of {{budget}}, and a target launch of {{timeline}}.
    Your main requirements were {{features}}.
    Based on what we discussed, the e-commerce website can be tailored around these requirements. I'll follow up with the relevant details.
    — Alex
    📞 +1-555-123-4567
    """
    what_they_sell = context.get("what_they_sell")
    business_goal = context.get("business_goal")
    product_count = context.get("product_count")
    budget = context.get("budget")
    timeline = context.get("timeline")
    features = context.get("features", [])

    lines = ["Hi, thanks for speaking with me.", ""]

    # Determine business goal or requirement phrase
    if business_goal:
        bg_clean = business_goal.strip()
        bg_clean = re.sub(r"^(?:i\s+want\s+to|i'm\s+planning\s+to|planning\s+to|looking\s+to)\s+", "", bg_clean, flags=re.IGNORECASE)
        goal_phrase = bg_clean
    elif what_they_sell:
        goal_phrase = f"sell {what_they_sell} online"
    else:
        goal_phrase = "set up an online store"

    clauses = []
    if product_count:
        p_val = str(product_count).strip()
        if not p_val.lower().startswith("around") and not p_val.lower().startswith("approx"):
            clauses.append(f"around {p_val} products" if "products" not in p_val.lower() else f"around {p_val}")
        else:
            clauses.append(f"{p_val} products" if "products" not in p_val.lower() else p_val)

    if budget:
        b_val = str(budget).strip()
        if not b_val.lower().startswith("about") and not b_val.lower().startswith("around") and not b_val.lower().startswith("a budget"):
            clauses.append(f"a budget of about {b_val}" if "₹" not in b_val and "rs" not in b_val.lower() else f"a budget of {b_val}")
        elif not b_val.lower().startswith("a budget"):
            clauses.append(f"a budget of {b_val}")
        else:
            clauses.append(b_val)

    if timeline:
        t_val = str(timeline).strip()
        if not t_val.lower().startswith("a target launch") and not t_val.lower().startswith("target launch"):
            clauses.append(f"a target launch of {t_val}")
        else:
            clauses.append(t_val)

    if clauses:
        if len(clauses) == 1:
            sub_clauses = f", with {clauses[0]}"
        elif len(clauses) == 2:
            sub_clauses = f", with {clauses[0]}, and {clauses[1]}"
        else:
            sub_clauses = f", with {', '.join(clauses[:-1])}, and {clauses[-1]}"
        lines.append(f"You mentioned that you're looking to {goal_phrase}{sub_clauses}.")
    else:
        lines.append(f"You mentioned that you're looking to {goal_phrase}.")

    feat_text = format_features_natural(features)
    if feat_text:
        lines.append("")
        lines.append(f"Your main requirements were {feat_text}.")

    lines.append("")
    if feat_text or clauses:
        lines.append("Based on what we discussed, the e-commerce website can be tailored around these requirements. I'll follow up with the relevant details.")
    else:
        lines.append("Based on what we discussed, the e-commerce website can be tailored around your requirements. I'll follow up with the relevant details.")

    lines.append("")
    lines.append(f"— {MY_CONTACT_NAME}\n📞 {MY_CONTACT_PHONE}")

    return "\n".join(lines).strip()


# --------------------------------------------------
# ACTION HANDLERS
# --------------------------------------------------

async def send_hot_mid_call_whatsapp(raw_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    HOT MID-CALL ACTION:
    Triggered when high buying intent is detected during the active voice call.
    Sends dynamic contextual WhatsApp message without waiting for the call to end.
    Enforces idempotency using hot_whatsapp:{call_id} and in-flight deduplication.
    """
    context = normalize_call_context(raw_context)
    call_id = context.get("call_id") or "unknown_call"
    # Recipient selection (Trial Safety: strictly routes to TEST_WHATSAPP_NUMBER)
    recipient = get_target_recipient(context.get("customer_phone"))
    logger.info(f"[WA] target recipient: {recipient}")

    if call_id != "unknown_call":
        idempotency_key = f"hot_whatsapp:{call_id}"
    else:
        idempotency_key = f"hot_whatsapp:{recipient}"

    # Check duplicate protection
    if idempotency_key in PROCESSED_HOT_CALLS:
        logger.info(f"[WA] Duplicate HOT event detected for key: {idempotency_key}. Returning cached response.")
        return {
            "success": True,
            "duplicate": True,
            "status": "already_sent",
            "message": "HOT mid-call WhatsApp was already sent for this call session.",
            "call_id": call_id,
            "cached_result": PROCESSED_HOT_CALLS[idempotency_key]
        }
    if idempotency_key in IN_FLIGHT_HOT_CALLS:
        logger.info(f"[WA] In-flight HOT send already running for key: {idempotency_key}. Returning in_flight status.")
        return {
            "success": True,
            "duplicate": True,
            "status": "in_flight",
            "message": "HOT mid-call WhatsApp send is currently in progress.",
            "call_id": call_id
        }
    IN_FLIGHT_HOT_CALLS.add(idempotency_key)


    # Generate contextual message
    message_text = build_hot_mid_call_message(context)
    logger.info(f"[WA] HOT message generated:\n{message_text}")

    # Send via Green API
    try:
        t3_time = datetime.datetime.now().isoformat()
        logger.info(f"[TIMESTAMP: T3] [HOT-WHATSAPP] Green API send started at {t3_time} -> recipient: {recipient}")

        green_res = await send_whatsapp_text(recipient, message_text)
        message_id = green_res.get("idMessage", "")

        t4_time = datetime.datetime.now().isoformat()
        logger.info(f"[TIMESTAMP: T4] [HOT-WHATSAPP] Green API message delivered at {t4_time}, messageId: {message_id}")

        result = {
            "success": True,
            "duplicate": False,
            "status": "sent",
            "action": "hot_mid_call",
            "call_id": call_id,
            "recipient": recipient,
            "messageId": message_id,
            "greenApiResponse": green_res,
            "generated_message": message_text,
            "normalized_context": context,
            "timestamps": {
                "t3_send_started": t3_time,
                "t4_send_success": t4_time
            }
        }

        PROCESSED_HOT_CALLS[idempotency_key] = result
        return result

    except Exception as e:
        logger.error(f"[WA] Error during hot mid-call send: {str(e)}")
        raise
    finally:
        IN_FLIGHT_HOT_CALLS.discard(idempotency_key)



async def send_post_call_whatsapp(raw_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST-CALL ACTION:
    Triggered after call completes. Sends complete contextual follow-up summary
    along with architecture diagram and resume PDF attachments.
    Enforces idempotency using post_call_whatsapp:{call_id}.
    """
    context = normalize_call_context(raw_context)
    call_id = context.get("call_id") or "unknown_call"
    idempotency_key = f"post_call_whatsapp:{call_id}"

    t6_time = datetime.datetime.now().isoformat()
    logger.info(f"[TIMESTAMP: T6] [POST-CALL] Action started at {t6_time} -> call_id: {call_id}")

    # Check duplicate protection
    if call_id != "unknown_call" and idempotency_key in PROCESSED_POST_CALLS:
        logger.info(f"[WA] Duplicate POST-CALL event detected for key: {idempotency_key}. Returning cached response.")
        return {
            "success": True,
            "duplicate": True,
            "status": "already_sent",
            "message": "Post-call WhatsApp was already sent for this call session.",
            "call_id": call_id,
            "cached_result": PROCESSED_POST_CALLS[idempotency_key]
        }

    # Recipient selection (Trial Safety: strictly routes to TEST_WHATSAPP_NUMBER)
    recipient = get_target_recipient(context.get("customer_phone"))
    logger.info(f"[WA] target recipient: {recipient}")

    # Generate contextual message
    message_text = build_post_call_message(context)
    logger.info(f"[WA] POST-CALL message generated:\n{message_text}")

    try:
        # Step 1: Send primary contextual text message
        green_res = await send_whatsapp_text(recipient, message_text)
        message_id = green_res.get("idMessage", "")

        files_sent = []
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")

        # Step 2: Attach Architecture Diagram Image
        arch_path = os.path.join(assets_dir, "system_architecture.png")
        if os.path.exists(arch_path):
            try:
                logger.info(f"[WA] Attaching system architecture diagram...")
                f_res = await send_whatsapp_file(
                    recipient,
                    arch_path,
                    "ElevateBox_System_Architecture.png",
                    caption="ElevateBox E-Commerce Voice & WhatsApp Architecture Flow"
                )
                files_sent.append({"type": "architecture_image", "filename": "system_architecture.png", "response": f_res})
            except Exception as fe:
                logger.warning(f"[WA] Architecture image attachment failed (text was delivered): {fe}")

        # Step 3: Attach Resume PDF
        resume_path = os.path.join(assets_dir, "sample_resume.pdf")
        if os.path.exists(resume_path):
            try:
                logger.info(f"[WA] Attaching resume PDF...")
                f_res = await send_whatsapp_file(
                    recipient,
                    resume_path,
                    f"{MY_CONTACT_NAME.replace(' ', '_')}_Resume.pdf",
                    caption=f"{MY_CONTACT_NAME} - Resume"
                )
                files_sent.append({"type": "resume_pdf", "filename": "sample_resume.pdf", "response": f_res})
            except Exception as fe:
                logger.warning(f"[WA] Resume PDF attachment failed (text was delivered): {fe}")

        result = {
            "success": True,
            "duplicate": False,
            "status": "sent",
            "action": "post_call",
            "call_id": call_id,
            "recipient": recipient,
            "messageId": message_id,
            "greenApiResponse": green_res,
            "attachments_sent": files_sent,
            "generated_message": message_text,
            "normalized_context": context
        }

        if call_id != "unknown_call":
            PROCESSED_POST_CALLS[idempotency_key] = result

        return result

    except Exception as e:
        logger.error(f"[WA] Error during post-call send: {str(e)}")
        raise
