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

# Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="dolbomcare API",
    description="AI-powered care management platform",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>이음로직 - 요양 관리 혁신 플랫폼</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #10b981;
            --primary-dark: #059669;
            --primary-light: #ecfdf5;
            --text-primary: #111827;
            --text-secondary: #6b7280;
            --text-tertiary: #9ca3af;
            --bg-light: #f9fafb;
            --bg-white: #ffffff;
            --border: #e5e7eb;
            --shadow: 0 1px 3px rgba(0,0,0,0.08);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.12);
        }
        html { scroll-behavior: smooth; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background: var(--bg-white);
        }
        nav {
            position: fixed;
            top: 0;
            width: 100%;
            background: rgba(255,255,255,0.98);
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
            font-size: 22px;
            font-weight: 700;
            color: var(--primary);
            text-decoration: none;
        }
        .nav-links { display: flex; gap: 35px; list-style: none; align-items: center; }
        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
            transition: color 0.3s;
        }
        .nav-links a:hover { color: var(--primary); }
        .nav-cta {
            background: var(--primary);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.3s;
        }
        .nav-cta:hover { background: var(--primary-dark); }
        .hero {
            margin-top: 64px;
            padding: 120px 20px 80px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
        }
        .hero-container {
            max-width: 900px;
            margin: 0 auto;
        }
        .hero h1 {
            font-size: 52px;
            font-weight: 800;
            margin-bottom: 20px;
            line-height: 1.2;
        }
        .hero-subtitle {
            font-size: 18px;
            margin-bottom: 40px;
            opacity: 0.95;
            line-height: 1.7;
        }
        .hero-buttons {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
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
            box-shadow: var(--shadow-md);
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.2);
        }
        .btn-secondary {
            background: transparent;
            color: white;
            border-color: white;
        }
        .btn-secondary:hover {
            background: white;
            color: var(--primary);
        }
        .section {
            padding: 100px 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .section-header {
            text-align: center;
            margin-bottom: 70px;
        }
        .section-header h2 {
            font-size: 40px;
            font-weight: 800;
            margin-bottom: 20px;
            color: var(--text-primary);
        }
        .section-header p {
            font-size: 18px;
            color: var(--text-secondary);
            max-width: 700px;
            margin: 0 auto;
        }
        .section-dark { background: var(--bg-light); }
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 40px;
            margin-top: 50px;
        }
        .card {
            padding: 45px 35px;
            border-radius: 12px;
            background: var(--bg-white);
            border: 1px solid var(--border);
            transition: all 0.3s;
        }
        .card:hover {
            transform: translateY(-10px);
            box-shadow: var(--shadow-md);
            border-color: var(--primary);
        }
        .card-icon {
            font-size: 50px;
            margin-bottom: 25px;
        }
        .card h3 {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 15px;
            color: var(--text-primary);
        }
        .card p {
            color: var(--text-secondary);
            line-height: 1.8;
            font-size: 15px;
        }
        .testimonial {
            background: var(--bg-white);
            padding: 40px;
            border-radius: 12px;
            border: 1px solid var(--border);
            margin-bottom: 30px;
        }
        .testimonial-quote {
            font-size: 16px;
            color: var(--text-primary);
            margin-bottom: 20px;
            font-style: italic;
            line-height: 1.8;
        }
        .testimonial-author {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .author-info h4 {
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 5px;
        }
        .author-info p {
            color: var(--text-secondary);
            font-size: 14px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 40px;
            margin-top: 50px;
        }
        .stat-card {
            text-align: center;
        }
        .stat-number {
            font-size: 48px;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 10px;
        }
        .stat-label {
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 15px;
        }
        .problem-solution {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 60px;
            align-items: center;
            margin: 60px 0;
        }
        .ps-content h3 {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 20px;
            color: var(--text-primary);
        }
        .ps-content ul {
            list-style: none;
        }
        .ps-content li {
            padding: 12px 0;
            padding-left: 30px;
            position: relative;
            color: var(--text-secondary);
        }
        .ps-content li:before {
            content: "✓";
            position: absolute;
            left: 0;
            color: var(--primary);
            font-weight: bold;
            font-size: 18px;
        }
        .cta-box {
            background: var(--primary-light);
            padding: 80px 20px;
            text-align: center;
            border-radius: 12px;
            margin: 80px 0;
        }
        .cta-box h2 {
            font-size: 38px;
            font-weight: 800;
            color: var(--primary-dark);
            margin-bottom: 20px;
        }
        .cta-box p {
            font-size: 18px;
            color: var(--text-secondary);
            margin-bottom: 40px;
        }
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
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 40px;
            margin-bottom: 40px;
        }
        .footer-section h4 {
            font-weight: 700;
            margin-bottom: 20px;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.8;
        }
        .footer-section a {
            display: block;
            color: rgba(255,255,255,0.7);
            text-decoration: none;
            margin-bottom: 12px;
            font-size: 14px;
            transition: color 0.3s;
        }
        .footer-section a:hover { color: white; }
        .footer-bottom {
            max-width: 1200px;
            margin: 0 auto;
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
            .section-header h2 { font-size: 30px; }
            .problem-solution { grid-template-columns: 1fr; gap: 30px; }
            .grid-3 { grid-template-columns: 1fr; }
            .hero-buttons { flex-direction: column; }
            .btn { width: 100%; text-align: center; }
        }
    </style>
</head>
<body>
    <nav>
        <div class="nav-container">
            <a href="/" class="logo">이음로직</a>
            <ul class="nav-links">
                <li><a href="#problems">왜 필요한가</a></li>
                <li><a href="#solution">솔루션</a></li>
                <li><a href="#testimonials">성공 사례</a></li>
                <li><a href="#contact" class="nav-cta">시작하기</a></li>
            </ul>
        </div>
    </nav>

    <section class="hero">
        <div class="hero-container">
            <h1>요양 관리를 단순하게</h1>
            <p class="hero-subtitle">요양사의 업무 부담을 줄이고, 센터는 효율성을 높이고, 보호자의 신뢰를 얻으세요. AI 기반 dolbomcare가 모든 것을 가능하게 합니다.</p>
            <div class="hero-buttons">
                <a href="#contact" class="btn btn-primary">무료 데모 신청</a>
                <a href="#solution" class="btn btn-secondary">자세히 알아보기</a>
            </div>
        </div>
    </section>

    <section id="problems" class="section section-dark">
        <div class="container">
            <div class="section-header">
                <h2>요양 센터의 현실</h2>
                <p>매일 반복되는 수작업, 복잡한 청부 계산, 정보 흩어짐으로 인한 실수가 일어나고 있습니다</p>
            </div>
            <div class="grid-3">
                <div class="card">
                    <div class="card-icon">😤</div>
                    <h3>요양사</h3>
                    <p>손으로 쓰는 기록, 전화로 청부 확인, 급여 정산까지 기다리는 과정의 반복</p>
                </div>
                <div class="card">
                    <div class="card-icon">📊</div>
                    <h3>센터장</h3>
                    <p>정산 실수, 관리자 확인, 건강보험 청구 지연, 데이터 관리의 어려움</p>
                </div>
                <div class="card">
                    <div class="card-icon">😰</div>
                    <h3>보호자</h3>
                    <p>요양 상태를 실시간으로 확인할 수 없음, 제때 답장 받기 어려움</p>
                </div>
            </div>
        </div>
    </section>

    <section id="solution" class="section">
        <div class="container">
            <div class="section-header">
                <h2>dolbomcare 플랫폼</h2>
                <p>모두의 업무를 간단히, 투명하게, 빠르게 만드는 통합 솔루션</p>
            </div>
            <div class="problem-solution">
                <div class="ps-content">
                    <h3>🎤 음성 기반 기록</h3>
                    <ul>
                        <li>손쓰기 시간 80% 절감</li>
                        <li>실수 없는 정확한 기록</li>
                        <li>야근 없이 퇴근 가능</li>
                    </ul>
                </div>
                <div style="background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); padding: 40px; border-radius: 12px;">
                    <div style="font-size: 80px; text-align: center;">🎙️</div>
                </div>
            </div>

            <div class="problem-solution" style="grid-template-columns: 1fr 1fr; direction: rtl;">
                <div class="ps-content" style="direction: ltr;">
                    <h3>💰 스마트 청부 관리</h3>
                    <ul>
                        <li>자동 계산으로 정산 오류 제거</li>
                        <li>실시간 청부 현황 확인</li>
                        <li>투명한 급여 정산</li>
                    </ul>
                </div>
                <div style="background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); padding: 40px; border-radius: 12px;">
                    <div style="font-size: 80px; text-align: center;">💳</div>
                </div>
            </div>

            <div class="problem-solution">
                <div class="ps-content">
                    <h3>👨‍👩‍👧 보호자 신뢰</h3>
                    <ul>
                        <li>실시간 요양 상태 공유</li>
                        <li>의료 기록 안전 관리</li>
                        <li>즉시 소통으로 신뢰 구축</li>
                    </ul>
                </div>
                <div style="background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); padding: 40px; border-radius: 12px;">
                    <div style="font-size: 80px; text-align: center;">👨‍👩‍👦</div>
                </div>
            </div>
        </div>
    </section>

    <section class="section section-dark">
        <div class="container">
            <div class="section-header">
                <h2>이미 믿고 있습니다</h2>
                <p>전국 요양센터와 요양사들이 dolbomcare로 업무 효율을 높이고 있습니다</p>
            </div>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">500+</div>
                    <div class="stat-label">활성 사용자</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">80%</div>
                    <div class="stat-label">업무 시간 단축</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">100%</div>
                    <div class="stat-label">정산 정확도</div>
                </div>
            </div>

            <div style="margin-top: 60px;">
                <div class="testimonial">
                    <div class="testimonial-quote">"음성 기록으로 퇴근 시간이 한두 시간 앞당겨졌어요. 대기 시간 없이 급여도 투명하게 확인됩니다."</div>
                    <div class="testimonial-author">
                        <div style="width: 50px; height: 50px; background: #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">김</div>
                        <div class="author-info">
                            <h4>김은지</h4>
                            <p>요양사 · 서울 요양센터</p>
                        </div>
                    </div>
                </div>
                <div class="testimonial">
                    <div class="testimonial-quote">"관리가 쉬워져서 센터 운영에 집중할 수 있게 됐습니다. 직원 만족도도 올라가고, 보호자 신뢰도 높아졌어요."</div>
                    <div class="testimonial-author">
                        <div style="width: 50px; height: 50px; background: #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">이</div>
                        <div class="author-info">
                            <h4>이준호</h4>
                            <p>센터장 · 부산 요양센터</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section id="testimonials" class="section">
        <div class="container">
            <div class="cta-box" id="contact">
                <h2>지금 시작하세요</h2>
                <p>5분 안에 요양센터 운영이 달라집니다. 무료 데모를 신청하세요.</p>
                <a href="#contact" class="btn btn-primary">무료 데모 신청</a>
            </div>
        </div>
    </section>

    <footer>
        <div class="footer-content">
            <div class="footer-section">
                <h4>제품</h4>
                <a href="#solution">기능</a>
                <a href="#problems">용도</a>
            </div>
            <div class="footer-section">
                <h4>회사</h4>
                <a href="/">홈</a>
                <a href="/">소개</a>
            </div>
            <div class="footer-section">
                <h4>개발자</h4>
                <a href="/docs">API 문서</a>
                <a href="/openapi.json">기술 문서</a>
            </div>
            <div class="footer-section">
                <h4>연락처</h4>
                <a href="mailto:contact@eeum-logic.com">이메일</a>
                <a href="#">카카오톡</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>© 2026 이음로직. 모든 권리 보유. | seniorcareinfo.kr</p>
        </div>
    </footer>
</body>
</html>"""

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
