FROM python:3.11-slim

WORKDIR /app/backend

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/ ./

EXPOSE $PORT

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
