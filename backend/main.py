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
        <title>Eeum Logic - AI Care Management Platform</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            :root {
                --primary: #10b981;
                --primary-dark: #059669;
                --primary-light: #d1fae5;
                --text-primary: #111827;
                --text-secondary: #6b7280;
                --bg-light: #f9fafb;
                --border-color: #e5e7eb;
                --shadow: 0 1px 3px rgba(0,0,0,0.1);
                --shadow-lg: 0 10px 25px rgba(0,0,0,0.1);
            }

            html {
                scroll-behavior: smooth;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--text-primary);
                background: white;
                overflow-x: hidden;
            }

            /* Navigation */
            nav {
                position: fixed;
                top: 0;
                width: 100%;
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                z-index: 1000;
                border-bottom: 1px solid var(--border-color);
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
                letter-spacing: -0.5px;
            }

            .nav-links {
                display: flex;
                gap: 30px;
                list-style: none;
            }

            .nav-links a {
                color: var(--text-secondary);
                text-decoration: none;
                font-weight: 500;
                font-size: 14px;
                transition: color 0.3s;
            }

            .nav-links a:hover {
                color: var(--primary);
            }

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

            .cta-button:hover {
                background: var(--primary-dark);
            }

            /* Hero */
            .hero {
                margin-top: 64px;
                padding: 100px 20px;
                background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
                color: white;
                text-align: center;
                min-height: 600px;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                position: relative;
            }

            .hero::before {
                content: '';
                position: absolute;
                top: -50%;
                right: -10%;
                width: 500px;
                height: 500px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 50%;
            }

            .hero-content {
                max-width: 800px;
                z-index: 1;
                animation: slideUp 0.8s ease-out;
            }

            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .hero h1 {
                font-size: 56px;
                font-weight: 800;
                margin-bottom: 20px;
                line-height: 1.2;
                letter-spacing: -1px;
            }

            .hero-subtitle {
                font-size: 20px;
                margin-bottom: 40px;
                opacity: 0.95;
                line-height: 1.6;
            }

            .hero-buttons {
                display: flex;
                gap: 15px;
                justify-content: center;
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
                cursor: pointer;
                display: inline-block;
            }

            .btn-primary {
                background: white;
                color: var(--primary);
                box-shadow: var(--shadow-lg);
            }

            .btn-primary:hover {
                transform: translateY(-3px);
                box-shadow: 0 15px 35px rgba(0,0,0,0.2);
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

            /* Sections */
            .section {
                padding: 100px 20px;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
            }

            .section-header {
                text-align: center;
                margin-bottom: 60px;
            }

            .section-header h2 {
                font-size: 42px;
                font-weight: 700;
                margin-bottom: 20px;
                color: var(--text-primary);
            }

            .section-header p {
                font-size: 18px;
                color: var(--text-secondary);
                max-width: 600px;
                margin: 0 auto;
            }

            /* Features Grid */
            .features-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
                gap: 30px;
                margin-bottom: 60px;
            }

            .feature-card {
                padding: 40px 30px;
                border-radius: 12px;
                background: white;
                border: 1px solid var(--border-color);
                transition: all 0.3s;
            }

            .feature-card:hover {
                transform: translateY(-8px);
                box-shadow: var(--shadow-lg);
                border-color: var(--primary);
            }

            .feature-icon {
                font-size: 40px;
                margin-bottom: 20px;
                display: block;
            }

            .feature-card h3 {
                font-size: 20px;
                font-weight: 700;
                margin-bottom: 15px;
                color: var(--text-primary);
            }

            .feature-card p {
                color: var(--text-secondary);
                line-height: 1.7;
            }

            /* Alternate Sections */
            .section-dark {
                background: var(--bg-light);
            }

            /* Stats */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 30px;
                margin-top: 50px;
            }

            .stat-card {
                padding: 30px;
                background: white;
                border-radius: 12px;
                border: 1px solid var(--border-color);
                text-align: center;
            }

            .stat-number {
                font-size: 42px;
                font-weight: 800;
                color: var(--primary);
                margin-bottom: 10px;
            }

            .stat-label {
                color: var(--text-secondary);
                font-weight: 500;
            }

            /* Tech Stack */
            .tech-stack {
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                margin-top: 30px;
                justify-content: center;
            }

            .tech-badge {
                background: var(--primary-light);
                color: var(--primary-dark);
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: 600;
            }

            /* Product Card */
            .product-card {
                background: white;
                border: 1px solid var(--border-color);
                border-radius: 12px;
                padding: 40px;
                margin-bottom: 30px;
            }

            .product-card h3 {
                font-size: 28px;
                font-weight: 700;
                margin-bottom: 20px;
                color: var(--text-primary);
            }

            .product-description {
                font-size: 16px;
                color: var(--text-secondary);
                line-height: 1.8;
                margin-bottom: 30px;
            }

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

            .links {
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                margin-top: 20px;
            }

            .link-btn {
                color: var(--primary);
                text-decoration: none;
                font-weight: 600;
                padding: 10px 16px;
                border-radius: 6px;
                transition: all 0.3s;
                background: var(--primary-light);
            }

            .link-btn:hover {
                background: var(--primary);
                color: white;
            }

            /* Footer */
            footer {
                background: var(--text-primary);
                color: white;
                padding: 60px 20px 30px;
                border-top: 1px solid var(--border-color);
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
                letter-spacing: 0.5px;
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

            .footer-section a:hover {
                color: white;
            }

            .footer-bottom {
                border-top: 1px solid rgba(255,255,255,0.1);
                padding-top: 30px;
                text-align: center;
                font-size: 14px;
                opacity: 0.7;
            }

            /* Responsive */
            @media (max-width: 768px) {
                .nav-links {
                    display: none;
                }

                .hero h1 {
                    font-size: 36px;
                }

                .section {
                    padding: 60px 20px;
                }

                .section-header h2 {
                    font-size: 32px;
                }

                .hero-buttons {
                    flex-direction: column;
                    align-items: center;
                }

                .btn {
                    width: 100%;
                    max-width: 300px;
                }
            }
        </style>
    </head>
    <body>
        <!-- Navigation -->
        <nav>
            <div class="nav-container">
                <a href="/" class="logo">Eeum Logic</a>
                <ul class="nav-links">
                    <li><a href="#features">Features</a></li>
                    <li><a href="#products">Products</a></li>
                    <li><a href="#technology">Technology</a></li>
                    <li><a href="/docs" class="cta-button">API Docs</a></li>
                </ul>
            </div>
        </nav>

        <!-- Hero -->
        <section class="hero">
            <div class="hero-content">
                <h1>The Future of Care Management</h1>
                <p class="hero-subtitle">AI-powered solutions for modernizing elderly care in Korea.<br>Connecting caregivers, facilities, and families.</p>
                <div class="hero-buttons">
                    <a href="#products" class="btn btn-primary">Explore Products</a>
                    <a href="/docs" class="btn btn-secondary">Read Docs</a>
                </div>
            </div>
        </section>

        <!-- Features -->
        <section id="features" class="section">
            <div class="container">
                <div class="section-header">
                    <h2>Why Choose Eeum Logic</h2>
                    <p>We combine cutting-edge AI technology with deep healthcare expertise to solve real problems.</p>
                </div>

                <div class="features-grid">
                    <div class="feature-card">
                        <span class="feature-icon">🤖</span>
                        <h3>AI-Powered</h3>
                        <p>Advanced machine learning and voice recognition technology for intelligent care documentation.</p>
                    </div>
                    <div class="feature-card">
                        <span class="feature-icon">📱</span>
                        <h3>Mobile First</h3>
                        <p>Seamless experience on iOS and Android with offline capabilities for field workers.</p>
                    </div>
                    <div class="feature-card">
                        <span class="feature-icon">🔒</span>
                        <h3>Enterprise Security</h3>
                        <p>HIPAA-compliant infrastructure with end-to-end encryption and role-based access control.</p>
                    </div>
                    <div class="feature-card">
                        <span class="feature-icon">⚡</span>
                        <h3>Real-Time Sync</h3>
                        <p>Instant data synchronization across all devices and stakeholders with no latency.</p>
                    </div>
                    <div class="feature-card">
                        <span class="feature-icon">📊</span>
                        <h3>Advanced Analytics</h3>
                        <p>Comprehensive dashboards and insights for better decision-making and resource optimization.</p>
                    </div>
                    <div class="feature-card">
                        <span class="feature-icon">🔗</span>
                        <h3>Fully Integrated</h3>
                        <p>Seamless integration with existing healthcare systems and third-party services via REST API.</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- Stats -->
        <section class="section section-dark">
            <div class="container">
                <div class="section-header">
                    <h2>Growing Market Opportunity</h2>
                    <p>Addressing a massive and rapidly expanding market for elder care solutions.</p>
                </div>

                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">$65.8B</div>
                        <div class="stat-label">Total Addressable Market</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">10.6%</div>
                        <div class="stat-label">Annual Growth Rate</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">2026</div>
                        <div class="stat-label">Founded</div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Products -->
        <section id="products" class="section">
            <div class="container">
                <div class="section-header">
                    <h2>Our Platform</h2>
                    <p>Comprehensive solutions designed for the modern healthcare ecosystem.</p>
                </div>

                <div class="product-card">
                    <h3>dolbomcare Platform</h3>
                    <p class="product-description">
                        A unified care management platform that connects caregivers, facility managers, and families.
                        Streamlines documentation, billing, and communication with AI-driven insights.
                    </p>

                    <h4 style="font-size: 18px; font-weight: 700; margin-top: 30px; margin-bottom: 20px;">Core Features</h4>
                    <ul class="feature-list">
                        <li><strong>Voice-Based Recording</strong> - AI transcription for hands-free documentation</li>
                        <li><strong>Smart Billing</strong> - Automated charge calculation and reimbursement tracking</li>
                        <li><strong>Schedule Management</strong> - Intelligent scheduling and shift planning</li>
                        <li><strong>Resident Profiles</strong> - Comprehensive care history and medical records</li>
                        <li><strong>Role-Based Dashboards</strong> - Tailored views for caregivers, managers, and families</li>
                        <li><strong>Real-Time Notifications</strong> - Instant alerts for important events and changes</li>
                    </ul>

                    <div class="links">
                        <a href="/api/v1/health" class="link-btn">Health Status</a>
                        <a href="/docs" class="link-btn">API Documentation</a>
                        <a href="/openapi.json" class="link-btn">OpenAPI Schema</a>
                    </div>
                </div>
            </div>
        </section>

        <!-- Technology -->
        <section id="technology" class="section section-dark">
            <div class="container">
                <div class="section-header">
                    <h2>Built on Modern Tech</h2>
                    <p>Enterprise-grade technology stack for reliability, scalability, and performance.</p>
                </div>

                <div class="tech-stack">
                    <span class="tech-badge">FastAPI</span>
                    <span class="tech-badge">PostgreSQL</span>
                    <span class="tech-badge">React Native</span>
                    <span class="tech-badge">JWT Auth</span>
                    <span class="tech-badge">REST API</span>
                    <span class="tech-badge">Docker</span>
                    <span class="tech-badge">Render Cloud</span>
                    <span class="tech-badge">Cloudflare CDN</span>
                </div>
            </div>
        </section>

        <!-- CTA -->
        <section class="section" style="text-align: center; background: var(--primary-light);">
            <div class="container">
                <h2 style="color: var(--primary-dark); margin-bottom: 20px;">Ready to Transform Your Operations?</h2>
                <p style="color: var(--text-secondary); font-size: 18px; margin-bottom: 30px;">
                    Start integrating dolbomcare into your platform today with our comprehensive REST API.
                </p>
                <a href="/docs" class="btn btn-primary">Explore API</a>
            </div>
        </section>

        <!-- Footer -->
        <footer>
            <div class="footer-content">
                <div class="footer-section">
                    <h4>Product</h4>
                    <a href="/docs">Documentation</a>
                    <a href="/api/v1/health">API Status</a>
                    <a href="#features">Features</a>
                </div>
                <div class="footer-section">
                    <h4>Company</h4>
                    <a href="#about">About</a>
                    <a href="#technology">Technology</a>
                    <a href="#products">Products</a>
                </div>
                <div class="footer-section">
                    <h4>Resources</h4>
                    <a href="/docs">API Docs</a>
                    <a href="/openapi.json">OpenAPI Spec</a>
                    <a href="/">Home</a>
                </div>
                <div class="footer-section">
                    <h4>Legal</h4>
                    <a href="#">Privacy Policy</a>
                    <a href="#">Terms of Service</a>
                    <a href="#">Contact</a>
                </div>
            </div>
            <div class="footer-bottom">
                <p>© 2026 Eeum Logic. All rights reserved. | <a href="https://seniorcareinfo.kr" style="color: rgba(255,255,255,0.7); text-decoration: none;">seniorcareinfo.kr</a></p>
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
