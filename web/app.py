"""Gamma Chatbot – Flask web application."""

import sys
from pathlib import Path
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from web.db import (
    init_db, create_user, verify_user, get_user_by_id,
    save_chat, get_user_chats,
    create_data_deletion_request,
    record_interaction, get_dashboard_metrics_snapshot,
)
from rag.sunbird import SunbirdClient, SunbirdError
from web.whatsapp_meta import (
    extract_inbound_text_messages,
    extract_inbound_image_messages,
    download_whatsapp_media,
    is_whatsapp_configured,
    load_whatsapp_config,
    send_whatsapp_text,
    send_whatsapp_image,
    send_whatsapp_interactive_list,
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")

def initialize_database() -> bool:
    try:
        init_db()
        return True
    except Exception:
        app.logger.exception("Database initialization failed during startup")
        return False


db_ready = initialize_database()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Pipeline (loaded once)
pipeline = None
sunbird = SunbirdClient()

SUPPORTED_SUNBIRD_TRANSLATION_LANGS = {"eng", "ach", "teo", "lug", "lgg", "nyn"}
SUPPORTED_LLM_TRANSLATION_LANGS = {"swa"}
SUNBIRD_DETECTED_LANGUAGE_REMAP = {"keo": "lug"}
_WHATSAPP_DEDUPE_TTL_SECONDS = 600
_processed_whatsapp_message_ids: dict[str, float] = {}

# Track WhatsApp contacts who have already received the welcome message
_known_whatsapp_contacts: set[str] = set()

WELCOME_MESSAGE = (
    "Hello! I can answer questions about UCU using official university documents. "
    "What would you like to know?"
)

FALLBACK_PREFIX = "i'm not fully confident in the answer based on the available documents"

# ── Campus information (events & clubs) used by web slider and WhatsApp ──
CAMPUS_INFO = {
    "events": {
        "title": "What's going on around Campus",
        "subtitle": "Stay connected with events, festivals & campus life",
        "image": "/static/images/campus_events.png",
        "items": [
            {
                "name": "Africa Day Celebrations",
                "date": "Coming Soon",
                "description": "A vibrant celebration of African culture with music, dance, food and art from across the continent.",
            },
            {
                "name": "UCU Music Festival",
                "date": "Coming Soon",
                "description": "Live performances by student bands, solo artists and guest musicians on the main campus grounds.",
            },
            {
                "name": "Career Fair 2026",
                "date": "Coming Soon",
                "description": "Connect with top employers, attend workshops and explore internship opportunities.",
            },
        ],
    },
    "tribes": {
        "title": "Find your Tribe",
        "subtitle": "Join a student club or group today",
        "image": "/static/images/find_your_tribe.png",
        "items": [
            {
                "name": "Launch Padders",
                "category": "Innovation & Tech",
                "description": "A community of student innovators building startups and tech projects together.",
            },
            {
                "name": "Debate Society",
                "category": "Academic",
                "description": "Sharpen your public speaking and critical thinking through competitive debates.",
            },
            {
                "name": "Campus Voices",
                "category": "Music & Arts",
                "description": "UCU's premier music group — choir, band and solo performances.",
            },
            {
                "name": "Tech/Coding Club",
                "category": "Technology",
                "description": "Weekly coding sessions, hackathons and tech talks for aspiring developers.",
            },
            {
                "name": "Sports Teams",
                "category": "Athletics",
                "description": "Football, basketball, volleyball, athletics and more — compete or play for fun.",
            },
        ],
    },
}


def get_public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")


def should_initialize_rag_for_whatsapp() -> bool:
    return os.getenv("WHATSAPP_INIT_PIPELINE", "false").strip().lower() in {"1", "true", "yes", "on"}


def should_process_whatsapp_message(message_id: str) -> bool:
    if not message_id:
        return True

    now = time.time()

    expired = [
        key
        for key, timestamp in _processed_whatsapp_message_ids.items()
        if now - timestamp > _WHATSAPP_DEDUPE_TTL_SECONDS
    ]
    for key in expired:
        _processed_whatsapp_message_ids.pop(key, None)

    if message_id in _processed_whatsapp_message_ids:
        return False

    _processed_whatsapp_message_ids[message_id] = now
    return True


def is_fallback_response(answer: str) -> bool:
    text = (answer or "").strip().lower()
    if text.startswith(FALLBACK_PREFIX):
        return True
    _FALLBACK_PHRASES = [
        "i don't have enough information",
        "i do not have enough information",
        "does not provide information",
        "does not contain enough information",
        "no information provided",
        "i'm not able to understand",
        "i'm not sure what",
        "not appear to be a question",
        "there is no information about",
        "there is no context about",
        "unfortunately, the provided context",
        "unfortunately, there is no information",
    ]
    return any(phrase in text for phrase in _FALLBACK_PHRASES)


def get_pipeline():
    global pipeline
    if pipeline is None:
        from rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()
    return pipeline


def build_answer(question: str) -> str:
    """Run retrieval + generation for one question."""
    from rag.fallback import build_fallback_response

    try:
        from rag.generator import generate_answer

        pipe = get_pipeline()
        context = pipe.retrieve(question)
    except Exception:
        app.logger.exception("Failed to retrieve context for question")
        return build_fallback_response(question)

    if not context:
        return build_fallback_response(question)

    try:
        answer = generate_answer(question, context, pipe.config.llm_model)
        return answer or build_fallback_response(question)
    except Exception:
        app.logger.exception("Failed to generate model answer; returning fallback")
        return build_fallback_response(question)


def build_whatsapp_answer(question: str) -> str:
    if should_initialize_rag_for_whatsapp():
        return build_answer(question)

    try:
        from pathlib import Path as _Path
        from rag.config import load_config
        from rag.lexical_search import lexical_search
        from rag.generator import generate_answer
        from rag.vector_store import RetrievedChunk

        config = load_config()
        lexical_lines = lexical_search(question, config)
        context = []
        for text, metadata in lexical_lines[:4]:
            source = metadata.get("source", "")
            title = _Path(source).stem.replace("_", " ").replace("-", " ").strip() if source else ""
            context.append(
                RetrievedChunk(text=text, metadata={"source": source, "title": title}, distance=0.0)
            )
        if context:
            return generate_answer(question, context, config.llm_model)
    except Exception:
        app.logger.exception("Failed to build lexical WhatsApp answer")

    from rag.fallback import build_fallback_response

    return build_fallback_response(question)


class User(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.role = user_dict["role"]


@login_manager.user_loader
def load_user(user_id):
    data = get_user_by_id(int(user_id))
    if data:
        return User(data)
    return None


# ── Auth routes ──────────────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("dashboard"))
        return redirect(url_for("chat"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_data = verify_user(username, password)
        if user_data:
            login_user(User(user_data))
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        role = "student"
        if not username or not password:
            flash("Username and password are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user_id = create_user(username, password, role)
            if user_id:
                user_data = get_user_by_id(user_id)
                login_user(User(user_data))
                return redirect(url_for("index"))
            else:
                flash("Username already taken.", "error")
    return render_template("signup.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── Public legal/compliance pages ───────────────────────────────

@app.route("/terms")
def terms_of_service():
    base_url = get_public_base_url()
    return render_template("terms.html", base_url=base_url)


@app.route("/privacy")
def privacy_policy():
    base_url = get_public_base_url()
    return render_template("privacy.html", base_url=base_url)


@app.route("/data-deletion", methods=["GET", "POST"])
def data_deletion():
    base_url = get_public_base_url()
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        contact_email = (request.form.get("contact_email") or "").strip()
        whatsapp_number = (request.form.get("whatsapp_number") or "").strip()
        details = (request.form.get("details") or "").strip()

        if not full_name or not contact_email:
            flash("Full name and email are required.", "error")
            return render_template("data_deletion.html", base_url=base_url), 400

        try:
            create_data_deletion_request(full_name, contact_email, whatsapp_number, details)
            flash("Your data deletion request has been received. We will contact you by email.")
            return redirect(url_for("data_deletion"))
        except Exception:
            app.logger.exception("Failed to save data deletion request")
            flash("Could not submit request right now. Please try again.", "error")
            return render_template("data_deletion.html", base_url=base_url), 503

    return render_template("data_deletion.html", base_url=base_url)


# ── Student chat ─────────────────────────────────────────────────

@app.route("/chat")
@login_required
def chat():
    history = get_user_chats(current_user.id)
    return render_template("chat.html", history=history)


@app.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    request_started = time.perf_counter()
    data = request.get_json(silent=True) or {}
    original_question = (data.get("question") or "").strip()
    if not original_question:
        return jsonify({"error": "Empty question"}), 400

    # The frontend may pass an explicit language code (e.g. "lug", "ach")
    explicit_language = (data.get("language") or "").strip().lower()

    retrieval_question = original_question
    source_language = "eng"

    if sunbird.is_configured():
        # If the user explicitly chose a non-English language, use it directly
        if explicit_language and explicit_language != "eng":
            if explicit_language in SUPPORTED_SUNBIRD_TRANSLATION_LANGS:
                source_language = explicit_language
                try:
                    translated = sunbird.translate(original_question, explicit_language, "eng")
                    translated_text = (translated.get("text") or "").strip()
                    if translated_text:
                        retrieval_question = translated_text
                except SunbirdError:
                    app.logger.exception("Sunbird translation failed for inbound question (explicit lang)")
            elif explicit_language:
                source_language = explicit_language
                from rag.generator import llm_translate
                translated_text = llm_translate(original_question, "English")
                if translated_text:
                    retrieval_question = translated_text
        elif not explicit_language or explicit_language == "auto":
            # Auto-detect language
            try:
                detected = sunbird.detect_language(original_question)
                if detected and detected != "eng":
                    translated_source = SUNBIRD_DETECTED_LANGUAGE_REMAP.get(detected, detected)
                    if translated_source in SUPPORTED_SUNBIRD_TRANSLATION_LANGS:
                        if translated_source != detected:
                            app.logger.info(
                                "Sunbird detected unsupported source '%s'; remapped to '%s'",
                                detected, translated_source,
                            )
                        translated = sunbird.translate(original_question, translated_source, "eng")
                        translated_text = (translated.get("text") or "").strip()
                        if translated_text:
                            retrieval_question = translated_text
                            source_language = translated_source
                    else:
                        from rag.generator import llm_translate
                        translated_text = llm_translate(original_question, "English")
                        if translated_text:
                            retrieval_question = translated_text
                            source_language = detected
            except SunbirdError:
                app.logger.exception("Sunbird language detection/translation failed for inbound question")

    translated_inbound = retrieval_question.strip().lower() != original_question.strip().lower()

    answer = build_answer(retrieval_question)

    final_answer = answer
    if source_language != "eng":
        if sunbird.is_configured() and source_language in SUPPORTED_SUNBIRD_TRANSLATION_LANGS:
            try:
                translated_answer = sunbird.translate(answer, "eng", source_language)
                translated_text = (translated_answer.get("text") or "").strip()
                if translated_text:
                    final_answer = translated_text
            except SunbirdError:
                app.logger.warning(
                    "Sunbird outbound translation failed for %s. Falling back to LLM translation.",
                    source_language,
                )
                from rag.generator import llm_translate
                lang_map = {"swa": "Swahili", "lug": "Luganda", "ach": "Acholi", "teo": "Ateso", "lgg": "Lugbara", "nyn": "Runyankole"}
                target = lang_map.get(source_language, source_language)
                translated_text = llm_translate(answer, target)
                if translated_text:
                    final_answer = translated_text
        else:
            from rag.generator import llm_translate
            lang_map = {"swa": "Swahili", "lug": "Luganda", "ach": "Acholi", "teo": "Ateso", "lgg": "Lugbara", "nyn": "Runyankole", "keo": "Kakwa"}
            target = lang_map.get(source_language, source_language)
            translated_text = llm_translate(answer, target)
            if translated_text:
                final_answer = translated_text

    translated_outbound = final_answer != answer
    fallback_used = is_fallback_response(answer)

    try:
        save_chat(current_user.id, original_question, final_answer)
    except Exception:
        app.logger.exception("Failed to persist chat history")

    latency_ms = round((time.perf_counter() - request_started) * 1000.0, 2)
    try:
        record_interaction(
            channel="web",
            user_ref=f"user:{current_user.id}",
            question_text=original_question,
            answer_text=final_answer,
            source_language=source_language,
            translated_inbound=translated_inbound,
            translated_outbound=translated_outbound,
            success=not fallback_used,
            fallback_used=fallback_used,
            latency_ms=latency_ms,
            error_type="generation_fallback" if fallback_used else "",
        )
    except Exception:
        app.logger.exception("Failed to persist web interaction analytics")

    # Check for building images to include
    from rag.buildings import find_building_images
    building_images = find_building_images(question + " " + final_answer)

    response = {"answer": final_answer, "language": source_language}
    if building_images:
        response["images"] = building_images
    return jsonify(response)



@app.route("/api/ask-image", methods=["POST"])
@login_required
def api_ask_image():
    """Handle image + question uploads for vision-based Q&A."""
    request_started = time.perf_counter()

    question = (request.form.get("question") or "").strip()
    if not question:
        question = "What can you tell me about this image?"

    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        return jsonify({"error": "No image uploaded"}), 400

    # Validate mime type
    allowed_mime = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    mime = image_file.content_type or "image/jpeg"
    if mime not in allowed_mime:
        return jsonify({"error": f"Unsupported image type: {mime}"}), 400

    # Read image (limit 10MB)
    image_bytes = image_file.read(10 * 1024 * 1024 + 1)
    if len(image_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "Image too large (max 10MB)"}), 400

    from rag.vision import analyse_image, detect_scenario, get_rag_context_for_scenario

    scenario = detect_scenario(question)

    # Get relevant RAG context to ground the vision response
    try:
        pip = get_pipeline()
    except Exception:
        pip = None
    rag_context = get_rag_context_for_scenario(scenario, question, pip)

    try:
        answer = analyse_image(
            image_bytes=image_bytes,
            question=question,
            rag_context=rag_context,
            scenario=scenario,
            mime_type=mime,
        )
    except Exception:
        app.logger.exception("Vision analysis failed")
        answer = "I wasn\'t able to analyse the image right now. Please try again later."

    fallback_used = is_fallback_response(answer)

    try:
        save_chat(current_user.id, f"[Image] {question}", answer)
    except Exception:
        app.logger.exception("Failed to persist image chat history")

    latency_ms = round((time.perf_counter() - request_started) * 1000.0, 2)
    try:
        record_interaction(
            channel="web",
            user_ref=f"user:{current_user.id}",
            question_text=f"[Image] {question}",
            answer_text=answer,
            source_language="eng",
            translated_inbound=False,
            translated_outbound=False,
            success=not fallback_used,
            fallback_used=fallback_used,
            latency_ms=latency_ms,
            error_type="vision_error" if "wasn\'t able to analyse" in answer else "",
        )
    except Exception:
        app.logger.exception("Failed to persist image interaction analytics")

    from rag.buildings import find_building_images
    building_images = find_building_images(question + " " + answer)

    response = {"answer": answer, "scenario": scenario}
    if building_images:
        response["images"] = building_images
    return jsonify(response)

@app.route("/api/campus-info")
def campus_info():
    """Return events and clubs data for the web slider / WhatsApp."""
    return jsonify(CAMPUS_INFO)


@app.route("/api/whatsapp/status")
def whatsapp_status():
    cfg = load_whatsapp_config()
    return jsonify(
        {
            "configured": is_whatsapp_configured(),
            "base_url": cfg["base_url"],
            "phone_number_id": cfg["phone_number_id"],
            "api_version": cfg["api_version"],
        }
    )


@app.route("/api/sunbird/status")
@login_required
def sunbird_status():
    cfg = sunbird.config
    return jsonify(
        {
            "configured": sunbird.is_configured(),
            "base_url": cfg.base_url,
            "translate_endpoint": cfg.translate_endpoint,
            "tts_endpoint": cfg.tts_endpoint,
            "stt_endpoint": cfg.stt_endpoint,
        }
    )


@app.route("/api/sunbird/translate", methods=["POST"])
@login_required
def sunbird_translate():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    source_language = (data.get("source_language") or "").strip()
    target_language = (data.get("target_language") or "").strip()

    if not text or not source_language or not target_language:
        return jsonify({"error": "text, source_language, and target_language are required."}), 400

    try:
        result = sunbird.translate(text, source_language, target_language)
        return jsonify({"text": result["text"], "raw": result["raw"]})
    except SunbirdError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/sunbird/tts", methods=["POST"])
@login_required
def sunbird_tts():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required."}), 400

    speaker_id = int(data.get("speaker_id", 248))
    response_mode = (data.get("response_mode") or "url").strip()
    temperature = data.get("temperature")
    max_new_audio_tokens = data.get("max_new_audio_tokens")

    try:
        result = sunbird.text_to_speech(
            text=text,
            speaker_id=speaker_id,
            response_mode=response_mode,
            temperature=float(temperature) if temperature is not None else None,
            max_new_audio_tokens=int(max_new_audio_tokens)
            if max_new_audio_tokens is not None
            else None,
        )
        return jsonify({"audio_url": result["audio_url"], "raw": result["raw"]})
    except ValueError:
        return jsonify({"error": "speaker_id, temperature, or max_new_audio_tokens has invalid type."}), 400
    except SunbirdError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/sunbird/stt", methods=["POST"])
@login_required
def sunbird_stt():
    audio = request.files.get("audio")
    if audio is None:
        return jsonify({"error": "audio file is required."}), 400

    language = (request.form.get("language") or "").strip() or None
    adapter = (request.form.get("adapter") or "").strip() or None

    whisper_raw = (request.form.get("whisper") or "").strip().lower()
    recognise_raw = (request.form.get("recognise_speakers") or "").strip().lower()

    whisper = None if whisper_raw == "" else whisper_raw in {"1", "true", "yes", "on"}
    recognise_speakers = (
        None if recognise_raw == "" else recognise_raw in {"1", "true", "yes", "on"}
    )

    try:
        result = sunbird.speech_to_text(
            audio_bytes=audio.read(),
            filename=audio.filename or "audio",
            content_type=audio.content_type or "application/octet-stream",
            language=language,
            adapter=adapter,
            whisper=whisper,
            recognise_speakers=recognise_speakers,
        )
        transcript = result.get("text") or ""
        detected_lang = ""
        if transcript and sunbird.is_configured():
            try:
                detected_lang = sunbird.detect_language(transcript)
            except SunbirdError:
                app.logger.debug("Language detection failed for STT transcript")
        return jsonify({"text": transcript, "language": detected_lang, "raw": result["raw"]})
    except SunbirdError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/webhooks/meta/whatsapp", methods=["GET"])
def meta_whatsapp_webhook_verify():
    cfg = load_whatsapp_config()
    mode = request.args.get("hub.mode", "").strip()
    token = request.args.get("hub.verify_token", "").strip()
    challenge = request.args.get("hub.challenge", "")

    if mode == "subscribe" and cfg["verify_token"] and token == cfg["verify_token"]:
        return challenge, 200
    return jsonify({"error": "Verification failed"}), 403


@app.route("/webhooks/meta/whatsapp", methods=["POST"])
def meta_whatsapp_webhook_receive():
    expected_token = os.getenv("META_WHATSAPP_WEBHOOK_TOKEN", "").strip()
    if expected_token:
        provided = request.headers.get("X-Webhook-Token", "").strip()
        if provided != expected_token:
            return jsonify({"error": "Unauthorized webhook token"}), 401

    if not is_whatsapp_configured():
        return jsonify({"error": "WhatsApp integration not configured"}), 500

    payload = request.get_json(silent=True) or {}
    inbound = extract_inbound_text_messages(payload)
    inbound_images = extract_inbound_image_messages(payload)
    if not inbound and not inbound_images:
        return jsonify({"status": "ignored", "reason": "no text or image messages"}), 200

    processed = []

    # ── Process image messages ──
    for msg in inbound_images:
        message_id = msg.get("id", "")
        if not should_process_whatsapp_message(message_id):
            processed.append({"id": message_id, "to": msg.get("from", ""), "status_code": 200, "ok": True, "provider": {"status": "duplicate_ignored"}})
            continue

        recipient = msg["from"]
        caption = msg.get("caption", "") or "What is in this image?"
        mime_type = msg.get("mime_type", "image/jpeg")
        media_id = msg["media_id"]

        # Send welcome on first contact
        is_first_contact = recipient not in _known_whatsapp_contacts
        if is_first_contact:
            _known_whatsapp_contacts.add(recipient)
            try:
                send_whatsapp_text(recipient, WELCOME_MESSAGE)
            except Exception:
                app.logger.exception("Failed to send WhatsApp welcome message")

        message_started = time.perf_counter()

        # Download image from Meta
        image_bytes, downloaded_mime = download_whatsapp_media(media_id)
        if not image_bytes:
            reply = "Sorry, I couldn't download that image. Please try sending it again."
            try:
                status_code, provider_response = send_whatsapp_text(recipient, reply)
            except Exception:
                status_code, provider_response = 502, {"error": "send failed"}
            processed.append({"id": message_id, "to": recipient, "status_code": status_code, "ok": 200 <= status_code < 300, "provider": provider_response})
            continue

        # Analyse image with vision module
        try:
            from rag.vision import analyse_image, detect_scenario, get_rag_context_for_scenario
            scenario = detect_scenario(caption)
            rag_context = get_rag_context_for_scenario(scenario, caption)
            answer = analyse_image(image_bytes, caption, rag_context=rag_context, scenario=scenario, mime_type=downloaded_mime or mime_type)
        except Exception:
            app.logger.exception("Vision analysis failed for WhatsApp image")
            answer = "Sorry, I couldn't analyse that image right now. Please try again later."

        fallback_used = is_fallback_response(answer)
        latency_ms = round((time.perf_counter() - message_started) * 1000.0, 2)

        try:
            status_code, provider_response = send_whatsapp_text(recipient, answer)
        except Exception:
            app.logger.exception("Failed to send WhatsApp image answer")
            status_code, provider_response = 502, {"error": "Failed to send"}

        delivery_ok = 200 <= status_code < 300
        try:
            record_interaction(
                channel="whatsapp_meta",
                user_ref=recipient,
                question_text=f"[Image] {caption}",
                answer_text=answer,
                source_language="eng",
                translated_inbound=False,
                translated_outbound=False,
                success=(delivery_ok and not fallback_used),
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                error_type="" if delivery_ok else "delivery_failed",
            )
        except Exception:
            app.logger.exception("Failed to persist WhatsApp image interaction analytics")

        processed.append({"id": message_id, "to": recipient, "status_code": status_code, "ok": delivery_ok, "provider": provider_response})

    # ── Process text messages ──
    for msg in inbound:
        message_id = msg.get("id", "")
        if not should_process_whatsapp_message(message_id):
            processed.append(
                {
                    "id": message_id,
                    "to": msg.get("from", ""),
                    "status_code": 200,
                    "ok": True,
                    "provider": {"status": "duplicate_ignored"},
                }
            )
            continue

        question = msg["text"]
        recipient = msg["from"]

        # Send welcome message + interactive list on first contact
        is_first_contact = recipient not in _known_whatsapp_contacts
        if is_first_contact:
            _known_whatsapp_contacts.add(recipient)
            try:
                send_whatsapp_text(recipient, WELCOME_MESSAGE)
            except Exception:
                app.logger.exception("Failed to send WhatsApp welcome message")
            try:
                send_whatsapp_interactive_list(recipient)
            except Exception:
                app.logger.exception("Failed to send WhatsApp interactive list")

        message_started = time.perf_counter()

        # ── Multilingual: detect, translate inbound, generate, translate outbound ──
        wa_source_language = "eng"
        wa_retrieval_question = question
        wa_translated_inbound = False
        wa_translated_outbound = False

        if sunbird.is_configured():
            try:
                detected = sunbird.detect_language(question)
                if detected and detected != "eng":
                    translated_source = SUNBIRD_DETECTED_LANGUAGE_REMAP.get(detected, detected)
                    if translated_source in SUPPORTED_SUNBIRD_TRANSLATION_LANGS:
                        try:
                            translated = sunbird.translate(question, translated_source, "eng")
                            translated_text = (translated.get("text") or "").strip()
                            if translated_text:
                                wa_retrieval_question = translated_text
                                wa_source_language = translated_source
                                wa_translated_inbound = True
                        except SunbirdError:
                            app.logger.exception("Sunbird inbound translation failed for WhatsApp")
                    elif translated_source in SUPPORTED_LLM_TRANSLATION_LANGS or detected:
                        from rag.generator import llm_translate
                        translated_text = llm_translate(question, "English")
                        if translated_text:
                            wa_retrieval_question = translated_text
                            wa_source_language = detected
                            wa_translated_inbound = True
            except SunbirdError:
                app.logger.exception("Sunbird language detection failed for WhatsApp")

        answer_generation_failed = False
        try:
            answer = build_whatsapp_answer(wa_retrieval_question)
        except Exception:
            app.logger.exception("Failed to generate WhatsApp answer")
            from rag.fallback import build_fallback_response
            answer = build_fallback_response(wa_retrieval_question)
            answer_generation_failed = True

        # Translate answer back to the user's language
        final_wa_answer = answer
        if wa_source_language != "eng" and not answer_generation_failed:
            if sunbird.is_configured() and wa_source_language in SUPPORTED_SUNBIRD_TRANSLATION_LANGS:
                try:
                    translated_answer = sunbird.translate(answer, "eng", wa_source_language)
                    translated_text = (translated_answer.get("text") or "").strip()
                    if translated_text:
                        final_wa_answer = translated_text
                        wa_translated_outbound = True
                except SunbirdError:
                    app.logger.warning("Sunbird outbound translation failed for WhatsApp (%s)", wa_source_language)
                    from rag.generator import llm_translate
                    lang_map = {"swa": "Swahili", "lug": "Luganda", "ach": "Acholi", "teo": "Ateso", "lgg": "Lugbara", "nyn": "Runyankole"}
                    target = lang_map.get(wa_source_language, wa_source_language)
                    translated_text = llm_translate(answer, target)
                    if translated_text:
                        final_wa_answer = translated_text
                        wa_translated_outbound = True
            else:
                from rag.generator import llm_translate
                lang_map = {"swa": "Swahili", "lug": "Luganda", "ach": "Acholi", "teo": "Ateso", "lgg": "Lugbara", "nyn": "Runyankole"}
                target = lang_map.get(wa_source_language, wa_source_language)
                translated_text = llm_translate(answer, target)
                if translated_text:
                    final_wa_answer = translated_text
                    wa_translated_outbound = True

        try:
            status_code, provider_response = send_whatsapp_text(recipient, final_wa_answer)
        except Exception:
            app.logger.exception("Failed to send WhatsApp answer")
            status_code, provider_response = 502, {"error": "Failed to send WhatsApp message"}

        delivery_ok = 200 <= status_code < 300

        # Send building images if the answer mentions any UCU buildings
        try:
            from rag.buildings import find_building_images
            building_imgs = find_building_images(question + " " + answer)
            base_url = os.getenv("RENDER_EXTERNAL_URL", request.url_root.rstrip("/"))
            sent = 0
            for bldg in building_imgs[:2]:
                for img_url in bldg["images"][:2]:
                    img_public_url = f"{base_url}{img_url}"
                    send_whatsapp_image(recipient, img_public_url, caption=bldg["name"])
                    sent += 1
                    if sent >= 3:
                        break
                if sent >= 3:
                    break
        except Exception:
            app.logger.debug("Could not send building images via WhatsApp")
        error_type = ""
        if answer_generation_failed:
            error_type = "generation_error"
        if not delivery_ok:
            error_type = f"{error_type};delivery_failed" if error_type else "delivery_failed"

        latency_ms = round((time.perf_counter() - message_started) * 1000.0, 2)
        try:
            record_interaction(
                channel="whatsapp_meta",
                user_ref=recipient,
                question_text=question,
                answer_text=final_wa_answer,
                source_language=wa_source_language,
                translated_inbound=wa_translated_inbound,
                translated_outbound=wa_translated_outbound,
                success=(delivery_ok and not answer_generation_failed),
                fallback_used=is_fallback_response(answer),
                latency_ms=latency_ms,
                error_type=error_type,
            )
        except Exception:
            app.logger.exception("Failed to persist WhatsApp interaction analytics")

        processed.append(
            {
                "id": message_id,
                "to": recipient,
                "status_code": status_code,
                "ok": delivery_ok,
                "provider": provider_response,
            }
        )

    return jsonify({"status": "processed", "count": len(processed), "results": processed}), 200


# ── Admin dashboard ──────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role != "admin":
        flash("Access denied.", "error")
        return redirect(url_for("chat"))

    metrics = get_dashboard_metrics_snapshot(days=30, top_n=15)
    return render_template("dashboard.html", metrics=metrics)


@app.route("/api/dashboard/metrics")
@login_required
def dashboard_metrics():
    if current_user.role != "admin":
        return jsonify({"error": "Access denied."}), 403

    try:
        metrics = get_dashboard_metrics_snapshot(days=30, top_n=15)
        return jsonify(metrics)
    except Exception:
        app.logger.exception("Failed to load dashboard metrics")
        return jsonify({"error": "Could not load dashboard metrics right now."}), 503


if __name__ == "__main__":
    print("Loading pipeline...")
    get_pipeline()
    print("Pipeline ready. Starting Gamma Chatbot...")
    app.run(host="0.0.0.0", port=7860, debug=False)
