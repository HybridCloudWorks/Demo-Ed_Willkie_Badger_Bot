# Container image for Cloud Run. `agents-cli deploy` (or `gcloud run deploy --source .`)
# builds this with Cloud Build and runs it on Cloud Run.
FROM python:3.12-slim

WORKDIR /code

COPY pyproject.toml README.md ./
COPY app ./app
COPY frontend ./frontend

# "-e" keeps the code at /code so the agent can find ./frontend and ./app.
RUN pip install --no-cache-dir -e ".[tts]"

EXPOSE 8080

CMD ["uvicorn", "app.fast_api_app:app", "--host", "0.0.0.0", "--port", "8080"]
