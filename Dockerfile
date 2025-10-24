# Dockerfile (im Ordner backend)
FROM python:3.11-slim

WORKDIR /app

# deps zuerst für besseren Cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# nur den Code aus dem Unterordner "app" in /app kopieren
COPY app/ .

ENV HOST=0.0.0.0 PORT=8080
EXPOSE 8080
CMD ["python", "server.py"]
