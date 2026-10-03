FROM python:3.11-slim

WORKDIR /app

# 복사: requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 복사: 모든 파일
COPY . .

# 작업 디렉토리 변경
WORKDIR /app/backend

# 실행 (PORT 환경 변수 사용)
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
