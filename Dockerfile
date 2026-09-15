FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN useradd -r -u 10001 app && chown -R app /app
USER app
EXPOSE 8080
CMD ["uvicorn", "postmortem_pilot.app:app", "--host", "0.0.0.0", "--port", "8080"]
