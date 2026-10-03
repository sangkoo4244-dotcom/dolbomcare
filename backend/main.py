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
    return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>이음로직 - AI 기반 돌봄 관리 솔루션</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #10b981;
            --primary-dark: #059669;
            --primary-light: #ecfdf5;
            --text-primary: #111827;
            --text-secondary: #6b7280;
            --bg-light: #f9fafb;
            --border: #e5e7eb;
            --shadow: 0 1px 3px rgba(0,0,0,0.1);
            --shadow-lg: 0 10px 25px rgba(0,0,0,0.15);
        }
        html { scroll-behavior: smooth; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background: white;
        }
        nav {
            position: fixed;
            top: 0;
            width: 100%;
            background: rgba(255,255,255,0.97);
            backdrop-filter: blur(10px);
            z-index: 1000;
            border-bottom: 1px solid var(--border);
            box-shadow: var(--shadow);
        }
        .nav-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            height: 64px;
        }
        .logo {
            font-size: 24px;
            font-weight: 700;
            color: var(--primary);
            text-decoration: none;
        }
        .nav-links { display: flex; gap: 30px; list-style: none; }
        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
            transition: color 0.3s;
        }
        .nav-links a:hover { color: var(--primary); }
        .cta-button {
            background: var(--primary);
            color: white;
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.3s;
        }
        .cta-button:hover { background: var(--primary-dark); }
        .hero {
            margin-top: 64px;
            padding: 120px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-align: center;
            min-height: 600px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .hero h1 { font-size: 56px; font-weight: 800; margin-bottom: 20px; line-height: 1.2; }
        .hero-subtitle { font-size: 20px; margin-bottom: 40px; opacity: 0.95; }
        .hero-buttons { display: flex; gap: 15px; justify-content: center; flex-wrap: wrap; }
        .btn {
            padding: 14px 32px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            transition: all 0.3s;
            border: 2px solid transparent;
            display: inline-block;
        }
        .btn-primary {
            background: white;
            color: var(--primary);
            box-shadow: var(--shadow-lg);
        }
        .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 15px 35px rgba(0,0,0,0.2); }
        .btn-secondary {
            background: transparent;
            color: white;
            border-color: white;
        }
        .btn-secondary:hover { background: white; color: var(--primary); }
        .section { padding: 100px 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .section-header { text-align: center; margin-bottom: 60px; }
        .section-header h2 { font-size: 42px; font-weight: 700; margin-bottom: 20px; color: var(--text-primary); }
        .section-header p { font-size: 18px; color: var(--text-secondary); max-width: 600px; margin: 0 auto; }
        .section-dark { background: var(--bg-light); }
        .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px; margin-top: 40px; }
        .card {
            padding: 40px 30px;
            border-radius: 12px;
            background: white;
            border: 1px solid var(--border);
            transition: all 0.3s;
        }
        .card:hover { transform: translateY(-8px); box-shadow: var(--shadow-lg); border-color: var(--primary); }
        .card-icon { font-size: 40px; margin-bottom: 20px; }
        .card h3 { font-size: 20px; font-weight: 700; margin-bottom: 15px; color: var(--text-primary); }
        .card p { color: var(--text-secondary); line-height: 1.7; }
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 30px; margin-top: 50px; }
        .stat-card {
            padding: 30px;
            background: white;
            border-radius: 12px;
            border: 1px solid var(--border);
            text-align: center;
        }
        .stat-number { font-size: 42px; font-weight: 800; color: var(--primary); margin-bottom: 10px; }
        .stat-label { color: var(--text-secondary); font-weight: 500; }
        .tech-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 30px;
            justify-content: center;
        }
        .tech-tag {
            background: var(--primary-light);
            color: var(--primary-dark);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
        }
        .product-card {
            background: white;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 40px;
            margin-bottom: 30px;
        }
        .product-card h3 { font-size: 28px; font-weight: 700; margin-bottom: 20px; color: var(--text-primary); }
        .product-desc { font-size: 16px; color: var(--text-secondary); line-height: 1.8; margin-bottom: 30px; }
        .feature-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .feature-list li {
            list-style: none;
            padding-left: 30px;
            position: relative;
            color: var(--text-secondary);
        }
        .feature-list li:before {
            content: "✓";
            position: absolute;
            left: 0;
            color: var(--primary);
            font-weight: bold;
            font-size: 18px;
        }
        .links { display: flex; gap: 15px; flex-wrap: wrap; margin-top: 20px; }
        .link-btn {
            color: var(--primary);
            text-decoration: none;
            font-weight: 600;
            padding: 10px 16px;
            border-radius: 6px;
            background: var(--primary-light);
            transition: all 0.3s;
        }
        .link-btn:hover { background: var(--primary); color: white; }
        .cta-section { text-align: center; background: var(--primary-light); padding: 100px 20px; }
        .cta-section h2 { color: var(--primary-dark); margin-bottom: 20px; }
        .cta-section p { color: var(--text-secondary); font-size: 18px; margin-bottom: 30px; }
        footer {
            background: var(--text-primary);
            color: white;
            padding: 60px 20px 30px;
            border-top: 1px solid var(--border);
        }
        .footer-content {
            max-width: 1200px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 40px;
            margin-bottom: 40px;
        }
        .footer-section h4 {
            font-weight: 700;
            margin-bottom: 15px;
            font-size: 14px;
            text-transform: uppercase;
            opacity: 0.7;
        }
        .footer-section a {
            display: block;
            color: rgba(255,255,255,0.7);
            text-decoration: none;
            margin-bottom: 10px;
            font-size: 14px;
            transition: color 0.3s;
        }
        .footer-section a:hover { color: white; }
        .footer-bottom {
            border-top: 1px solid rgba(255,255,255,0.1);
            padding-top: 30px;
            text-align: center;
            font-size: 14px;
            opacity: 0.7;
        }
        @media (max-width: 768px) {
            .nav-links { display: none; }
            .hero h1 { font-size: 36px; }
            .section { padding: 60px 20px; }
            .section-header h2 { font-size: 32px; }
            .hero-buttons { flex-direction: column; }
            .btn { width: 100%; max-width: 300px; }
        }
    </style>
</head>
<body>
    <nav>
        <div class="nav-container">
            <a href="/" class="logo">이음로직</a>
            <ul class="nav-links">
                <li><a href="#features">기능</a></li>
                <li><a href="#products">제품</a></li>
                <li><a href="#tech">기술</a></li>
                <li><a href="/docs" class="cta-button">API 문서</a></li>
            </ul>
        </div>
    </nav>

    <section class="hero">
        <div>
            <h1>요양 관리의 미래를 만들고 있습니다</h1>
            <p class="hero-subtitle">AI 기반 솔루션으로 요양사, 센터, 보호자를 연결합니다<br>더 나은 돌봄 경험을 제공합니다</p>
            <div class="hero-buttons">
                <a href="#products" class="btn btn-primary">제품 알아보기</a>
                <a href="/docs" class="btn btn-secondary">문서 보기</a>
            </div>
        </div>
    </section>

    <section id="features" class="section">
        <div class="container">
            <div class="section-header">
                <h2>왜 이음로직을 선택할까요</h2>
                <p>최첨단 AI 기술과 깊이 있는 의료 전문성으로 실제 문제를 해결합니다</p>
            </div>
            <div class="grid-2">
                <div class="card">
                    <div class="card-icon">🤖</div>
                    <h3>AI 기반</h3>
                    <p>고급 머신러닝과 음성인식 기술로 지능형 돌봄 기록 시스템</p>
                </div>
                <div class="card">
                    <div class="card-icon">📱</div>
                    <h3>모바일 중심</h3>
                    <p>iOS와 Android에서 seamless한 경험과 오프라인 기능 지원</p>
                </div>
                <div class="card">
                    <div class="card-icon">🔒</div>
                    <h3>엔터프라이즈 보안</h3>
                    <p>의료 표준 준수, 엔드-투-엔드 암호화 및 역할 기반 접근 제어</p>
                </div>
                <div class="card">
                    <div class="card-icon">⚡</div>
                    <h3>실시간 동기화</h3>
                    <p>모든 기기와 이해관계자 간 지연 없는 즉각적인 데이터 동기화</p>
                </div>
                <div class="card">
                    <div class="card-icon">📊</div>
                    <h3>고급 분석</h3>
                    <p>포괄적인 대시보드와 인사이트로 더 나은 의사결정 지원</p>
                </div>
                <div class="card">
                    <div class="card-icon">🔗</div>
                    <h3>완전한 통합</h3>
                    <p>REST API를 통한 기존 의료 시스템과 타사 서비스 연동</p>
                </div>
            </div>
        </div>
    </section>

    <section class="section section-dark">
        <div class="container">
            <div class="section-header">
                <h2>성장하는 시장 기회</h2>
                <p>한국의 요양 관리 시장은 빠르게 성장하고 있습니다</p>
            </div>
            <div class="stat-grid">
                <div class="stat-card">
                    <div class="stat-number">65.8B</div>
                    <div class="stat-label">시장 규모 (USD)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">10.6%</div>
                    <div class="stat-label">연평균 성장률</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">2026</div>
                    <div class="stat-label">설립연도</div>
                </div>
            </div>
        </div>
    </section>

    <section id="products" class="section">
        <div class="container">
            <div class="section-header">
                <h2>우리의 플랫폼</h2>
                <p>현대 의료 생태계를 위해 설계된 포괄적인 솔루션</p>
            </div>
            <div class="product-card">
                <h3>dolbomcare 플랫폼</h3>
                <p class="product-desc">
                    요양사, 센터장, 보호자를 연결하는 통합 요양 관리 플랫폼입니다.
                    AI 기반 인사이트로 문서화, 청구, 의사소통을 효율화합니다.
                </p>
                <h4 style="font-size: 18px; font-weight: 700; margin: 30px 0 20px 0;">핵심 기능</h4>
                <ul class="feature-list">
                    <li><strong>음성 기반 기록</strong> - AI 음성 인식으로 hands-free 문서화</li>
                    <li><strong>스마트 청부 관리</strong> - 자동 청부 계산 및 정산 추적</li>
                    <li><strong>일정 관리</strong> - 지능형 스케줄링 및 근무 계획</li>
                    <li><strong>이용자 프로필</strong> - 포괄적인 돌봄 이력 및 의료 기록</li>
                    <li><strong>역할별 대시보드</strong> - 요양사, 관리자, 보호자를 위한 맞춤 뷰</li>
                    <li><strong>실시간 알림</strong> - 중요 사항 및 변경 즉시 알림</li>
                </ul>
                <div class="links">
                    <a href="/api/v1/health" class="link-btn">상태 확인</a>
                    <a href="/docs" class="link-btn">API 문서</a>
                    <a href="/openapi.json" class="link-btn">OpenAPI 명세</a>
                </div>
            </div>
        </div>
    </section>

    <section id="tech" class="section section-dark">
        <div class="container">
            <div class="section-header">
                <h2>최신 기술 스택</h2>
                <p>안정성, 확장성, 성능을 위한 엔터프라이즈급 기술</p>
            </div>
            <div class="tech-tags">
                <span class="tech-tag">FastAPI</span>
                <span class="tech-tag">PostgreSQL</span>
                <span class="tech-tag">React Native</span>
                <span class="tech-tag">JWT 인증</span>
                <span class="tech-tag">REST API</span>
                <span class="tech-tag">Docker</span>
                <span class="tech-tag">Render Cloud</span>
                <span class="tech-tag">Cloudflare CDN</span>
            </div>
        </div>
    </section>

    <section class="cta-section">
        <div class="container">
            <h2>지금 시작하세요</h2>
            <p>dolbomcare의 강력한 REST API로 플랫폼을 통합하세요</p>
            <a href="/docs" class="btn btn-primary">API 탐색하기</a>
        </div>
    </section>

    <footer>
        <div class="footer-content">
            <div class="footer-section">
                <h4>제품</h4>
                <a href="/docs">문서</a>
                <a href="/api/v1/health">API 상태</a>
                <a href="#features">기능</a>
            </div>
            <div class="footer-section">
                <h4>회사</h4>
                <a href="#about">소개</a>
                <a href="#tech">기술</a>
                <a href="#products">제품</a>
            </div>
            <div class="footer-section">
                <h4>리소스</h4>
                <a href="/docs">API 문서</a>
                <a href="/openapi.json">OpenAPI 명세</a>
                <a href="/">홈</a>
            </div>
            <div class="footer-section">
                <h4>법률</h4>
                <a href="#">개인정보 보호</a>
                <a href="#">서비스 약관</a>
                <a href="#">연락처</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>© 2026 이음로직. All rights reserved. | <a href="https://seniorcareinfo.kr" style="color: rgba(255,255,255,0.7); text-decoration: none;">seniorcareinfo.kr</a></p>
        </div>
    </footer>
</body>
</html>"""

# 라우터 포함 (StaticFiles 전에 등록해야 우선순위 획득)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(users.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(records.router, prefix="/api/v1/records", tags=["records"])
app.include_router(residents.router, prefix="/api/v1/residents", tags=["residents"])
app.include_router(salary.router, prefix="/api/v1/salary", tags=["salary"])
app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
