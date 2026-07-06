# IBM Watson Orchestrate Interview Trainer Agent

A Flask-based AI interview trainer that uses IBM watson Orchestrate, resume parsing, a retrieval-augmented knowledge base, mock interview flows, scoring, and downloadable readiness reports.

## Features

- Resume upload and parsing from PDF
- Candidate profile management
- AI chat interview assistant backed by IBM watson Orchestrate
- Mock interview engine for technical, HR, behavioral, and coding rounds
- Retrieval-augmented generation using an interview knowledge base
- Interview evaluation, scoring, and feedback
- Readiness dashboard and downloadable report
- Responsive Bootstrap 5 interface with dark/light mode

## Local Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your IBM Cloud values, or keep your existing `ibm-credentials.env` in the project root.
4. The app loads `ibm-credentials.env` automatically from the project root.
5. Run the app:

```bash
python app.py
```

6. Open `http://localhost:5000`.

## IBM watson Orchestrate Configuration

Set these variables in `.env`:

- `ORCHESTRATE_APIKEY`
- `ORCHESTRATE_IAM_APIKEY`
- `ORCHESTRATE_URL`
- `ORCHESTRATE_AUTH_TYPE`
- `ORCHESTRATE_AGENT_ID`
- `ORCHESTRATE_INVOKE_PATH`

The web app loads your Orchestrate credentials file and will use them when an invocation path is configured. If you only provide the credentials, the app still runs locally and explains what additional agent endpoint setting is needed.

## Deployment on IBM Cloud

1. Package the app as a Flask web app or containerize it with Docker.
2. Store secrets in IBM Cloud Code Engine environment variables or IBM Cloud Secrets Manager.
3. Point the app to your Orchestrate instance, agent ID, and invocation path.
4. Ensure uploaded resumes and generated reports are stored in a persistent object store if you need long-term retention.

## Customizing the Agent

Edit the `AGENT_INSTRUCTIONS` settings in `.env` to adjust:

- interview style
- tone
- difficulty level
- company-specific focus
- evaluation criteria
- safety rules
- personalization behavior

## Notes

This project includes a local knowledge base skeleton in `data/knowledge_base`. Replace it with your own curated interview guides, company playbooks, and technical content for better RAG quality.
