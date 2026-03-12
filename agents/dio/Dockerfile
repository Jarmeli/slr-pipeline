FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY agents/dio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY agents/dio/src/ ./src/

EXPOSE 7001

CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "7001"]
