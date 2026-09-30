FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY web_app.py web_config.py web_storage.py quiz_core.py prompts.py ./
COPY static ./static
RUN useradd --create-home quiz
USER quiz
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
