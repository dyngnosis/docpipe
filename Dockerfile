FROM python:3.12-slim
RUN apt-get update && apt-get install -y pandoc && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data/uploads /data/outputs
ENV DATABASE_PATH=/data/docpipe.db \
    UPLOAD_DIR=/data/uploads \
    OUTPUT_DIR=/data/outputs \
    SECRET_KEY=change-me
EXPOSE 3005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3005"]
