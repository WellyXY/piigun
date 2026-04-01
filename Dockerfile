FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic \
    "redis[asyncio]" asyncpg httpx boto3

COPY . .

EXPOSE 8000

COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
