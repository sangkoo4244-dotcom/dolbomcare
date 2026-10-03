from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from app.api import health
from app.api import users
from app.api import billing
from app.api import records
from app.api import residents
from app.api import salary
from app.api import schedule
from app.database import Base, engine
import os
from pathlib import Path

# Base.metadata.create_all(bind=engine)  # PostgreSQL 연결 실패 시 서버 시작 불가 → 비활성화

app = FastAPI(
    title="dolbomcare API",
    description="AI-powered care management platform",
    version="0.1.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root path - 이음로직 회사 소개 페이지
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>이음로직 - AI 기반 돌봄 관리 솔루션</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f5f7fa;
            }
            header {
                background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
                color: white;
                padding: 20px 0;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 20px;
            }
            .header-content {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .logo {
                font-size: 28px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            nav a {
                color: white;
                margin-left: 30px;
                text-decoration: none;
                transition: opacity 0.3s;
            }
            nav a:hover {
                opacity: 0.8;
            }
            .hero {
                background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
                color: white;
                padding: 100px 0;
                text-align: center;
            }
            .hero h1 {
                font-size: 48px;
                margin-bottom: 20px;
            }
            .hero p {
                font-size: 20px;
                margin-bottom: 30px;
                opacity: 0.95;
            }
            .btn {
                display: inline-block;
                background: white;
                color: #4CAF50;
                padding: 12px 30px;
                border-radius: 5px;
                text-decoration: none;
                font-weight: bold;
                transition: transform 0.3s, box-shadow 0.3s;
                margin: 10px;
            }
            .btn:hover {
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            }
            .btn-secondary {
                background: transparent;
                color: white;
                border: 2px solid white;
            }
            .btn-secondary:hover {
                background: white;
                color: #4CAF50;
            }
            .section {
                padding: 80px 0;
                background: white;
                border-bottom: 1px solid #eee;
            }
            .section:nth-child(even) {
                background: #f9f9f9;
            }
            .section h2 {
                font-size: 36px;
                margin-bottom: 30px;
                text-align: center;
                color: #4CAF50;
            }
            .features {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 30px;
                margin-top: 40px;
            }
            .feature-card {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                text-align: center;
                transition: transform 0.3s;
            }
            .feature-card:hover {
                transform: translateY(-10px);
            }
            .feature-card h3 {
                color: #4CAF50;
                margin-bottom: 15px;
                font-size: 22px;
            }
            .feature-card p {
                color: #666;
                line-height: 1.8;
            }
            .icon {
                font-size: 48px;
                margin-bottom: 15px;
            }
            .project {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                margin-bottom: 30px;
            }
            .project h3 {
                color: #4CAF50;
                margin-bottom: 10px;
                font-size: 24px;
            }
            .project p {
                color: #666;
                margin-bottom: 15px;
                line-height: 1.8;
            }
            .project-links {
                display: flex;
                gap: 15px;
            }
            .project-links a {
                color: #4CAF50;
                text-decoration: none;
                font-weight: bold;
                transition: opacity 0.3s;
            }
            .project-links a:hover {
                opacity: 0.7;
            }
            footer {
                background: #333;
                color: white;
                text-align: center;
                padding: 30px 0;
            }
            footer p {
                margin-bottom: 10px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 30px;
                margin-top: 40px;
                text-align: center;
            }
            .stat {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .stat-number {
                font-size: 36px;
                color: #4CAF50;
                font-weight: bold;
            }
            .stat-label {
                color: #666;
                margin-top: 10px;
                font-size: 14px;
            }
            @media (max-width: 768px) {
                .header-content {
                    flex-direction: column;
                    gap: 20px;
                }
                nav a {
                    margin-left: 15px;
                    font-size: 14px;
                }
                .hero h1 {
                    font-size: 32px;
                }
                .hero p {
                    font-size: 16px;
                }
            }
        </style>
    </head>
    <body>
        <header>
            <div class="container">
                <div class="header-content">
                    <div class="logo">🔗 이음로직</div>
                    <nav>
                        <a href="#about">소개</a>
                        <a href="#projects">프로젝트</a>
                        <a href="#api">API</a>
                        <a href="#docs">문서</a>
                    </nav>
                </div>
            </div>
        </header>

        <section class="hero">
            <div class="container">
                <h1>이음로직</h1>
                <p>AI 기반 돌봄 관리 솔루션으로<br>더 나은 요양 케어 경험을 제공합니다</p>
                <a href="#projects" class="btn">프로젝트 보기</a>
                <a href="/docs" class="btn btn-secondary">API 문서</a>
            </div>
        </section>

        <section id="about" class="section">
            <div class="container">
                <h2>회사 소개</h2>
                <p style="font-size: 18px; color: #666; text-align: center; margin-bottom: 30px;">
                    이음로직은 최신 AI 기술을 활용하여 한국의 요양 관리 시스템을 혁신하는 개발사입니다.<br>
                    요양사의 독립성, 의료기관의 효율성, 보호자의 신뢰를 모두 확보하는 것을 목표로 합니다.
                </p>
                <div class="stats">
                    <div class="stat">
                        <div class="stat-number">10.6%</div>
                        <div class="stat-label">연평균 성장률</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">65.8B</div>
                        <div class="stat-label">요양 관리 시장</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">2026</div>
                        <div class="stat-label">설립년도</div>
                    </div>
                </div>
            </div>
        </section>

        <section id="projects" class="section">
            <div class="container">
                <h2>우리의 프로젝트</h2>
                <div class="features">
                    <div class="feature-card">
                        <div class="icon">📱</div>
                        <h3>dolbomcare</h3>
                        <p>AI 기반 요양 관리 플랫폼. 요양사, 센터장, 보호자를 위한 통합 솔루션입니다.</p>
                    </div>
                    <div class="feature-card">
                        <div class="icon">🎤</div>
                        <h3>음성 기록 시스템</h3>
                        <p>자동 음성인식을 통한 돌봄 기록. 업무 효율성을 획기적으로 증대합니다.</p>
                    </div>
                    <div class="feature-card">
                        <div class="icon">📊</div>
                        <h3>청구 관리 시스템</h3>
                        <p>자동화된 청구 워크플로우. 정확한 정산과 투명한 급여 관리를 지원합니다.</p>
                    </div>
                </div>

                <h2 style="margin-top: 60px;">dolbomcare 플랫폼</h2>
                <div class="project">
                    <h3>🏥 AI 기반 돌봄 관리 플랫폼</h3>
                    <p>
                        <strong>dolbomcare</strong>는 한국의 요양 관리 시스템을 혁신하기 위해 설계된 통합 플랫폼입니다.<br><br>
                        <strong>핵심 기능:</strong><br>
                        ✓ 음성 기반 자동 기록 (AI 음성인식)<br>
                        ✓ 스마트 청부 관리 (자동 계산 및 정산)<br>
                        ✓ 일정 관리 및 알림<br>
                        ✓ 이용자 정보 통합 관리<br>
                        ✓ 요양사/센터장/보호자 대시보드<br><br>
                        <strong>기술 스택:</strong><br>
                        FastAPI (Backend) | PostgreSQL (Database) | React Native (Mobile) | JWT (Authentication)
                    </p>
                    <div class="project-links">
                        <a href="/api/v1/health">→ API Health Check</a>
                        <a href="/docs">→ API 문서</a>
                    </div>
                </div>
            </div>
        </section>

        <section id="api" class="section">
            <div class="container">
                <h2>API 서비스</h2>
                <p style="font-size: 18px; color: #666; text-align: center; margin-bottom: 40px;">
                    dolbomcare는 RESTful API로 모든 기능을 제공합니다.<br>
                    안전한 JWT 인증과 완전한 API 문서를 통해 쉬운 통합이 가능합니다.
                </p>
                <div class="features">
                    <div class="feature-card">
                        <div class="icon">✅</div>
                        <h3>Health Check</h3>
                        <p><code>/api/v1/health</code><br>서비스 상태 확인</p>
                    </div>
                    <div class="feature-card">
                        <div class="icon">📚</div>
                        <h3>Swagger 문서</h3>
                        <p><code>/docs</code><br>완전한 API 명세 및 테스트</p>
                    </div>
                    <div class="feature-card">
                        <div class="icon">🔐</div>
                        <h3>JWT 인증</h3>
                        <p>안전한 토큰 기반 인증<br>모든 API 요청 보호</p>
                    </div>
                </div>
            </div>
        </section>

        <section id="docs" class="section">
            <div class="container">
                <h2>빠른 시작</h2>
                <div class="project">
                    <h3>🚀 API 사용 방법</h3>
                    <p>
                        <strong>1. API 상태 확인:</strong><br>
                        <code style="background: #f5f5f5; padding: 10px; border-radius: 4px; display: block; margin: 10px 0;">
                            GET /api/v1/health
                        </code>
                        <strong>응답:</strong>
                        <code style="background: #f5f5f5; padding: 10px; border-radius: 4px; display: block; margin: 10px 0;">
                            {"status":"healthy","service":"dolbomcare-api"}
                        </code>
                    </p>
                    <p style="margin-top: 20px;">
                        <strong>2. API 문서 보기:</strong><br>
                        <a href="/docs" class="btn" style="display: inline-block; margin-top: 10px;">Swagger UI 열기</a>
                    </p>
                </div>
            </div>
        </section>

        <footer>
            <div class="container">
                <p><strong>이음로직</strong> - AI 기반 돌봄 관리 솔루션</p>
                <p>📱 dolbomcare Platform | 🌐 https://seniorcareinfo.kr</p>
                <p>© 2026 이음로직. All rights reserved.</p>
            </div>
        </footer>
    </body>
    </html>
    """

# 라우터 포함 (StaticFiles 전에 등록해야 우선순위 획득)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(users.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(records.router, prefix="/api/v1/records", tags=["records"])
app.include_router(residents.router, prefix="/api/v1/residents", tags=["residents"])
app.include_router(salary.router, prefix="/api/v1/salary", tags=["salary"])
app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"])

# API는 자동으로 /docs와 /openapi.json 엔드포인트 제공

# 정적 파일 마운트 비활성화 (API 우선순위 문제 해결)
# scratchpad_path = str(Path(__file__).parent.parent / "scratchpad")
# if Path(scratchpad_path).exists():
#     app.mount("/", StaticFiles(directory=scratchpad_path, html=True), name="scratchpad")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
