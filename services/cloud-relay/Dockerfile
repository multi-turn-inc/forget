FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY relay.py .
ENV FORGET_RELAY_DB=/data/cloud-relay.sqlite3
EXPOSE 8080
CMD ["uvicorn", "relay:app", "--host", "0.0.0.0", "--port", "8080"]
