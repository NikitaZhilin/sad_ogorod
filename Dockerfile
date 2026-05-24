FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY README.md ./

RUN mkdir -p /app/data /app/backups
VOLUME ["/app/data", "/app/backups"]

CMD ["python", "-m", "ogorodom_bot.bot"]
