FROM python:3.11-slim

# 서비스 시각은 한국 시간 기준 (시간대 데이터가 없는 이미지에서도 동작하도록 tzdata를 설치)
ENV TZ=Asia/Seoul
RUN (apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*) || true

WORKDIR /app

# 복사: requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 복사: 모든 파일
COPY . .

# 작업 디렉토리 변경
WORKDIR /app/backend

# 실행 (PORT 환경 변수 사용)
CMD sh -c "python init_db.py && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
