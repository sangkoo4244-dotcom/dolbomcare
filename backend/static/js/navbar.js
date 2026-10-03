// 공통 네비게이션 컴포넌트
// 모든 페이지에서 사용

function renderNavbar() {
    const user = JSON.parse(localStorage.getItem('user'));
    const userRole = localStorage.getItem('user_role');

    if (!user) {
        window.location.href = './login.html';
        return;
    }

    // 역할별 메뉴 정의
    const menuItems = {
        caregiver: [
            { icon: '🏠', label: '대시보드', url: './dashboard.html' },
            { icon: '🎙️', label: '음성 기록', url: './voice_record.html' },
            { icon: '👤', label: '이용자 관리', url: './resident_management.html' },
            { icon: '📊', label: '나의 청부', url: './caregiver_billing.html' },
            { icon: '💳', label: '청부 조회', url: './salary.html' },
            { icon: '📢', label: '공지사항', url: './announcements.html', comingSoon: true },
        ],
        center_manager: [
            { icon: '🏠', label: '대시보드', url: './dashboard.html' },
            { icon: '👥', label: '직원 관리', url: './staff_management.html' },
            { icon: '👤', label: '이용자 관리', url: './resident_management.html' },
            { icon: '📅', label: '일정 관리', url: './scheduling.html', comingSoon: true },
            { icon: '🎙️', label: '음성 기록', url: './voice_record.html' },
            { icon: '💳', label: '청구 관리', url: './billing_management.html', comingSoon: true },
            { icon: '📊', label: '보고서', url: './reports.html', comingSoon: true },
        ]
    };

    const currentMenu = menuItems[userRole] || menuItems.caregiver;

    // 네비게이션 HTML 생성
    const navHTML = `
        <nav class="navbar">
            <div class="navbar-header">
                <div class="logo">
                    <span class="logo-text">💚 dolbomcare</span>
                </div>
            </div>

            <div class="navbar-menu">
                <div class="user-info">
                    <div class="user-avatar">${user.full_name.charAt(0)}</div>
                    <div class="user-details">
                        <div class="user-name">${user.full_name}</div>
                        <div class="user-role">${userRole === 'center_manager' ? '센터장' : '요양사'}</div>
                    </div>
                </div>

                <div class="menu-divider"></div>

                <ul class="menu-list">
                    ${currentMenu.map((item, index) => `
                        <li class="menu-item ${item.comingSoon ? 'coming-soon' : ''}">
                            <a href="${item.url}" onclick="${item.comingSoon ? 'return false;' : ''}">
                                <span class="menu-icon">${item.icon}</span>
                                <span class="menu-label">${item.label}</span>
                                ${item.comingSoon ? '<span class="soon-badge">준비 중</span>' : ''}
                            </a>
                        </li>
                    `).join('')}
                </ul>

                <div class="menu-divider"></div>

                <ul class="menu-list">
                    <li class="menu-item">
                        <a href="./settings.html" class="menu-link">
                            <span class="menu-icon">⚙️</span>
                            <span class="menu-label">설정</span>
                        </a>
                    </li>
                    <li class="menu-item">
                        <a href="#" onclick="logout()" class="menu-link logout">
                            <span class="menu-icon">🚪</span>
                            <span class="menu-label">로그아웃</span>
                        </a>
                    </li>
                </ul>
            </div>
        </nav>

        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                display: flex;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
                background: #f5f5f5;
            }

            .navbar {
                width: 250px;
                height: 100vh;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                position: fixed;
                left: 0;
                top: 0;
                overflow-y: auto;
                box-shadow: 2px 0 10px rgba(0,0,0,0.1);
                z-index: 1000;
            }

            .navbar-header {
                padding: 20px;
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }

            .logo {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .logo-text {
                font-size: 20px;
                font-weight: 700;
                letter-spacing: -0.5px;
            }

            .navbar-menu {
                padding: 20px 0;
            }

            .user-info {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 0 16px 16px;
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }

            .user-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: rgba(255,255,255,0.2);
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                font-size: 18px;
            }

            .user-details {
                flex: 1;
                min-width: 0;
            }

            .user-name {
                font-size: 14px;
                font-weight: 600;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .user-role {
                font-size: 12px;
                opacity: 0.9;
                margin-top: 2px;
            }

            .menu-divider {
                height: 1px;
                background: rgba(255,255,255,0.1);
                margin: 8px 0;
            }

            .menu-list {
                list-style: none;
            }

            .menu-item {
                margin: 0;
            }

            .menu-item a {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                color: rgba(255,255,255,0.85);
                text-decoration: none;
                font-size: 14px;
                transition: all 0.2s ease;
                cursor: pointer;
                position: relative;
            }

            .menu-item a:hover:not(.menu-item.coming-soon a) {
                background: rgba(255,255,255,0.15);
                color: white;
                padding-left: 20px;
            }

            .menu-item.coming-soon a {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .menu-icon {
                font-size: 18px;
                width: 24px;
                text-align: center;
            }

            .menu-label {
                flex: 1;
            }

            .soon-badge {
                font-size: 11px;
                background: rgba(255,255,255,0.2);
                padding: 2px 8px;
                border-radius: 12px;
                white-space: nowrap;
            }

            .menu-item.logout a {
                color: #ff6b6b;
            }

            .menu-item.logout a:hover {
                background: rgba(255,107,107,0.2);
                color: #ff8787;
            }

            main {
                margin-left: 250px;
                flex: 1;
                padding: 20px;
                width: calc(100% - 250px);
                min-height: 100vh;
            }

            /* 모바일 반응형 */
            @media (max-width: 768px) {
                .navbar {
                    width: 100%;
                    height: auto;
                    position: relative;
                    min-height: 60px;
                    display: flex;
                    align-items: center;
                }

                main {
                    margin-left: 0;
                    width: 100%;
                }

                .navbar-menu {
                    display: none;
                }

                .navbar-header {
                    border-bottom: none;
                    border-right: 1px solid rgba(255,255,255,0.2);
                    padding: 0 20px;
                }

                .logo-text {
                    font-size: 16px;
                }
            }
        </style>
    `;

    // DOM에 추가
    const navContainer = document.getElementById('navbar-container') || document.body.insertBefore(
        document.createElement('div'),
        document.body.firstChild
    );
    navContainer.id = 'navbar-container';
    navContainer.innerHTML = navHTML;
}

function logout() {
    if (confirm('정말 로그아웃 하시겠습니까?')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('user_role');
        window.location.href = './login.html';
    }
}

// 페이지 로드 시 네비게이션 렌더링
document.addEventListener('DOMContentLoaded', renderNavbar);
