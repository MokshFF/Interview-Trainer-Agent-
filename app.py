import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv

from services.agent_config import AGENT_INSTRUCTIONS
from services.interview_engine import InterviewEngine
from services.resume_parser import ResumeParser
from services.rag_service import RAGService
from services.score_service import ScoreService
from services.report_service import ReportService
from services.profile_store import ProfileStore
from services.orchestrate_client import OrchestrateClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "ibm-credentials.env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024

resume_parser = ResumeParser()
rag_service = RAGService(
    kb_path=BASE_DIR / "data" / "knowledge_base",
    collection_name=os.getenv("ORCHESTRATE_COLLECTION_NAME", "interview_knowledge"),
)
score_service = ScoreService()
profile_store = ProfileStore(BASE_DIR / "instance")
report_service = ReportService(BASE_DIR / "instance")
orchestrate_client = OrchestrateClient()
interview_engine = InterviewEngine(
    rag_service=rag_service,
    score_service=score_service,
    agent_instructions=AGENT_INSTRUCTIONS,
    orchestrate_client=orchestrate_client,
)


@app.route("/")
def index():
    profile = profile_store.load_profile()
    return render_template(
        "index.html",
        agent_instructions=AGENT_INSTRUCTIONS,
        profile=profile,
        dashboard=profile_store.load_dashboard(),
        sample_questions=interview_engine.sample_questions(profile),
    )


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(force=True)
    response = interview_engine.generate_response(payload)
    return jsonify(response)


@app.route("/resume/upload", methods=["POST"])
def upload_resume():
    uploaded = request.files.get("resume")
    if not uploaded:
        return jsonify({"error": "Resume file is required."}), 400

    parsed = resume_parser.parse(uploaded)
    profile_store.save_profile(parsed)
    return jsonify(parsed)


@app.route("/profile", methods=["POST"])
def save_profile():
    profile = request.get_json(force=True)
    saved = profile_store.save_profile(profile)
    return jsonify(saved)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    payload = request.get_json(force=True)
    evaluation = interview_engine.evaluate_answer(payload)
    return jsonify(evaluation)


@app.route("/report", methods=["GET"])
def report():
    profile = profile_store.load_profile()
    dashboard = profile_store.load_dashboard()
    report_data = report_service.build_report(profile, dashboard)
    return jsonify(report_data)


@app.route("/report/download", methods=["GET"])
def download_report():
    report_path = report_service.export_pdf(profile_store.load_profile(), profile_store.load_dashboard())
    return send_file(report_path, as_attachment=True, download_name="interview_readiness_report.pdf")


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify(
        {
            "status": "ok",
            "orchestrate_configured": orchestrate_client.configured,
            "orchestrate_can_invoke": orchestrate_client.can_invoke_agent,
            "rag_documents": rag_service.document_count(),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
