FROM mcr.microsoft.com/playwright/python:v1.53.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
ENV TZ=Asia/Kolkata

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
