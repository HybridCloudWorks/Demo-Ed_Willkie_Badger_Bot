# Shortcuts for the Career Day demo. See README.md for details.

.PHONY: install dev test check deploy

install:        ## Install the app and the no-key tests
	pip install -e ".[dev]"

dev:            ## Start the chatbot at http://localhost:8000
	uvicorn app.fast_api_app:app --host 127.0.0.1 --port 8000 --reload

test:           ## Tests that need NO API key
	pytest -q

check:          ## Live Career Day scenarios (needs a Gemini key or Vertex AI)
	python scripts/career_day_check.py

deploy:         ## Deploy to Cloud Run with the Agents CLI
	agents-cli deploy
