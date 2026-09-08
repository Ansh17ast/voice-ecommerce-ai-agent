# System Architecture & Technical Specifications

This document outlines the architectural design, component interactions, and state handling mechanisms powering the **Voice E-Commerce AI Agent & Lead Engine**.

---

## 1. High-Level System Overview

The system bridges conversational voice AI with asynchronous multi-channel lead engagement. When potential e-commerce clients receive an outbound call or place an inbound call, an AI voice agent conducts a multi-turn qualification conversation. Depending on buying signals detected during the call:
1. **HOT Leads** trigger an immediate mid-call WhatsApp message with an introduction and tailored overview while the customer is still on the phone.
2. **Post-Call Events** trigger context extraction, deterministic normalization, generation of an executive summary, and dispatch of collateral (architecture diagram, service capabilities, portfolio resume).
3. **WARM / COLD Leads** are routed to callback scheduling or lower-touch informational nurture workflows without aggressive closing.

```
                          +-------------------------+
                          |        CUSTOMER         |
                          | (Inbound/Outbound Call) |
                          +------------+------------+
                                       |
                                       v
                    +------------------------------------+
                    |     OmniDimension Voice Agent      |
                    |   - Sarvam / Deepgram STT (ASR)    |
                    |   - Cartesia / Sarvam TTS          |
                    |   - Multi-Turn Sales Prompt        |
                    +------------------+-----------------+
                                       |
                                       v
                    +------------------------------------+
                    |      Lead Temperature Engine       |
                    |      (HOT / WARM / COLD Eval)      |
                    +------------------+-----------------+
                                       |
           +---------------------------+---------------------------+
           | (Mid-Call HOT Trigger)                                | (Post-Call Completion)
           v                                                       v
+-----------------------+                               +-----------------------+
|  POST /webhook/hot-   |                               |  POST /webhook/post-  |
|         lead          |                               |         call          |
+-----------+-----------+                               +-----------+-----------+
            |                                                       |
            +---------------------------+---------------------------+
                                        |
                                        v
                    +------------------------------------+
                    |       FastAPI Lead Engine          |
                    |   - Context Normalizer             |
                    |   - Deduplication / Idempotency    |
                    |   - TRIAL_MODE Safety Router       |
                    +------------------+-----------------+
                                        |
                                        v
                    +------------------------------------+
                    |      Green API WhatsApp Engine     |
                    |     (or n8n Webhook Pipeline)      |
                    +------------------+-----------------+
                                        |
                                        v
                          +-------------------------+
                          |     WHATSAPP CLIENT     |
                          |  - Personalized Summary |
                          |  - Architecture Flow PNG|
                          |  - Solution PDF / Resume|
                          +-------------------------+
```

---

## 2. Component Breakdown

### A. Voice Telephony & Speech Layer (OmniDimension)
- **Automatic Speech Recognition (ASR):** Powered by Sarvam and Deepgram models supporting multilingual Indian English, Hindi, and code-mixed vernacular utterances.
- **Text-to-Speech (TTS):** Low-latency neural streaming synthesis (Sarvam / Cartesia) maintaining natural cadence and sub-second acoustic turn-taking.
- **Conversational Memory:** Preserves business category, catalogue size, development budget, timeline, and feature requirements across turns.
- **Turn Taking Rules:** Strict single-response-per-turn limit prevents duplicate bot utterances during customer speech pauses.

### B. Lead Qualification State Machine
The system categorizes leads into three distinct operational tiers:

| Tier | Buying Signal Criteria | Triggered Action |
|---|---|---|
| **HOT** | Stated requirements + budget + timeline + immediate readiness / next-step inquiry | Mid-call WhatsApp trigger while active on line |
| **WARM** | Clear requirement but constrained by an explicit barrier (budget approval, partner signoff, timing) | Callback scheduling workflow; no premature closure |
| **COLD** | Pure exploration, no business entity, or vague non-committal statements | Informational follow-up; zero pressure |

```
                       [ Incoming / Outbound Call ]
                                    |
                                    v
                         [ Context Gathering ]
                        /           |         \
                       /            |          \
                      v             v           v
                 [ HOT ]        [ WARM ]     [ COLD ]
                    |               |           |
             (No Barriers,     (Identified      (Vague /
             Ready to Act)       Barrier)      Exploring)
                    |               |           |
                    v               v           v
            POST /webhook/     Callback       Nurture /
               hot-lead        Scheduling     Follow-up
```

### C. FastAPI Lead Engine (`main.py` & `whatsapp_service.py`)
- **Endpoints:**
  - `POST /webhook/hot-lead`: Accepts mid-call lead alerts. Validates payload, verifies idempotency, and delivers introductory WhatsApp confirmation. Returns minimal status (`{"ok": true, "status": "sent"}`) to avoid prompt pollution.
  - `POST /webhook/post-call`: Accepts comprehensive post-call event webhooks. Extracts structured context, builds tailored message body, and dispatches media assets.
  - `GET /health`: Returns service operational status, Green API instance connectivity, and environment configuration checks.
  - `POST /test/whatsapp`: Internal diagnostic endpoint sending test messages to `DEV_RECIPIENT_CHAT_ID`.
- **Heuristic Context Normalization:**
  Extracts:
  - Product count ranges (e.g., `"around 500–600"`, `"50 products"`)
  - Budget figures (e.g., `"about ₹80,000"`, `"₹70k"`)
  - Timelines (e.g., `"next month"`, `"in 2 weeks"`)
  - Features (e.g., payments, inventory management, WhatsApp tracking, order tracking)
  - Distinguishes "planning to sell" from "currently selling" to prevent factual distortion.
- **Strict Anti-Hallucination:**
  Missing conversational fields are cleanly omitted from generated messages rather than populated with placeholder defaults or speculative estimates.

### D. WhatsApp Messaging Layer (Green API & n8n)
- **Direct HTTP Integration:** Uses Green API REST endpoints (`/sendMessage`, `/sendFileByUpload`) to transmit messages and media.
- **Optional n8n Pipeline:** An exportable, pre-configured n8n workflow (`workflows/n8n-automation.json`) allows routing WhatsApp delivery through visual enterprise automation pipelines.
- **Attachments:** Automatically uploads and attaches:
  1. `assets/system_architecture.png`: High-resolution architecture blueprint.
  2. `assets/sample_resume.pdf`: Professional engineering candidate profile.

---

## 3. Reliability, Concurrency & Idempotency

In production telephony systems, webhooks may be redelivered due to network retransmits or platform retries. The FastAPI lead engine incorporates multi-tier idempotency controls:

```
[ Incoming Webhook Request ]
             |
             v
+----------------------------+
| Extract call_id / phone    |
+------------+---------------+
             |
             v
+----------------------------+     YES     +------------------------------+
| In PROCESSED_CALLS Cache?  | ----------->| Return Cached 200 Response   |
+------------+---------------+             | ("status": "already_sent")   |
             | NO                          +------------------------------+
             v
+----------------------------+     YES     +------------------------------+
| In IN_FLIGHT_CALLS Set?    | ----------->| Return 200 Conflict Safe     |
+------------+---------------+             | ("status": "in_flight")      |
             | NO                          +------------------------------+
             v
+----------------------------+
| Add to IN_FLIGHT_CALLS     |
+------------+---------------+
             |
             v
+----------------------------+
| Process Message & Media    |
+------------+---------------+
             |
             v
+----------------------------+
| Add to PROCESSED_CALLS     |
| Remove from IN_FLIGHT      |
+----------------------------+
```

1. **In-Flight Lock (`IN_FLIGHT_HOT_CALLS`):** Detects concurrent duplicate webhook bursts arriving within milliseconds.
2. **Processed Cache (`PROCESSED_HOT_CALLS` / `PROCESSED_POST_CALLS`):** Caches completed transactions by `call_id` to ensure each call triggers at most one delivery.
3. **Idempotent Response Protocol:** Subsequent duplicates return HTTP 200 with `duplicate: true` and `status: "already_sent"`, preventing webhook retry storms while guaranteeing zero duplicate messages to users.

---

## 4. Safety & Privacy Controls

- **`TRIAL_MODE` Safety Interlock:** When enabled (`TRIAL_MODE=true`), all outbound WhatsApp messages are redirected to `TEST_WHATSAPP_NUMBER`, ensuring that real caller phone numbers are never contacted during testing or portfolio demonstrations.
- **Credential Hygiene:** Credentials (`OMNIDIM_API_KEY`, `GREEN_API_TOKEN`) are strictly managed through environment variables and never logged or serialized to disk.
- **Sanitized Logging:** All loggers strip keys matching `token`, `secret`, `key`, `auth`, or `password` before logging payloads to console or log streams.
