FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 4001

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${ROUTER_PORT:-4001}"]
