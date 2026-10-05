// 모든 API 요청에 로그인 토큰을 붙이고, 세션이 만료되면 로그인 화면으로 보낸다
(function () {
    const originalFetch = window.fetch.bind(window);
    const isApi = (url) => typeof url === 'string' && url.includes('/api/v1/');
    const isLogin = (url) => url.includes('/users/login') || url.includes('/auth/login');

    window.fetch = function (input, init = {}) {
        const url = typeof input === 'string' ? input : input.url;
        if (!isApi(url) || isLogin(url)) return originalFetch(input, init);

        const headers = new Headers(init.headers || {});
        const token = localStorage.getItem('access_token');
        if (token) headers.set('Authorization', 'Bearer ' + token);

        return originalFetch(input, { ...init, headers }).then((response) => {
            if (response.status === 401) {
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = './login.html';
            }
            return response;
        });
    };
})();

const SIDEBAR_MENUS = {
    caregiver: [
        { href: 'dashboard.html', icon: '📊', label: '대시보드' },
        { href: 'resident_management.html', icon: '👥', label: '이용자관리' },
        { href: 'voice_record.html', icon: '🎤', label: '음성 기록' },
        { href: 'caregiver_billing.html', icon: '📋', label: '나의 청부' },
        { href: 'my_salary.html', icon: '💵', label: '나의 급여' },
        { href: 'my_schedule.html', icon: '📅', label: '나의 일정' },
        { href: 'notifications.html', icon: '🔔', label: '알림' },
        { href: 'messages.html', icon: '💬', label: '보호자 소통' }
    ],
    guardian: [
        { href: 'guardian_home.html', icon: '🏠', label: '이용자 방문 기록' },
        { href: 'messages.html', icon: '💬', label: '센터와 메시지' }
    ],
    center_manager: [
        { href: 'dashboard.html', icon: '📊', label: '대시보드' },
        { href: 'resident_management.html', icon: '👥', label: '이용자관리' },
        { href: 'voice_record.html', icon: '🎤', label: '음성 기록' },
        { href: 'schedule_approval.html', icon: '📝', label: '방문계획 승인' },
        { href: 'billing_management.html', icon: '💰', label: '청부관리' },
        { href: 'staff_management.html', icon: '👔', label: '직원관리' },
        { href: 'monthly_settlement.html', icon: '📈', label: '월별정산' },
        { href: 'profit_analysis.html', icon: '📊', label: '수익분석' },
        { href: 'guardian_management.html', icon: '🤝', label: '보호자 관리' },
        { href: 'messages.html', icon: '💬', label: '보호자 소통' }
    ]
};

const SIDEBAR_STYLE = `
.side-brand { padding: 24px; border-bottom: 1px solid #374151; display: flex; align-items: center; gap: 12px; }
.side-logo { font-size: 30px; }
.side-title { font-size: 18px; font-weight: 700; }
.side-sub { font-size: 12px; color: #9ca3af; }
.side-item { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-radius: 8px; color: #d1d5db; font-size: 14px; text-decoration: none; cursor: pointer; transition: background 0.15s; }
.side-item:hover { background: #374151; color: #fff; }
.side-item.active { background: #059669; color: #fff; }
.side-icon { font-size: 16px; }
`;

function renderSidebar() {
    if (!document.getElementById('sideMenuStyle')) {
        const style = document.createElement('style');
        style.id = 'sideMenuStyle';
        style.textContent = SIDEBAR_STYLE;
        document.head.appendChild(style);
    }

    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const roleMenu = { caregiver: 'caregiver', guardian: 'guardian' }[user.role] || 'center_manager';
    const items = SIDEBAR_MENUS[roleMenu];
    const current = window.location.pathname.split('/').pop();
    const nav = document.querySelector('#navContent, .sidebar-nav');
    nav.style.padding = '16px';
    nav.innerHTML = items.map(item => `
        <a href="./${item.href}" class="side-item ${item.href === current ? 'active' : ''}">
            <span class="side-icon">${item.icon}</span>
            <span>${item.label}</span>
        </a>
    `).join('') + `
        <a class="side-item" style="margin-top: 32px;" onclick="logout()">
            <span class="side-icon">🚪</span>
            <span>로그아웃</span>
        </a>
    `;
    showUnreadMessageBadge();
}

// 보호자 소통 메뉴에 안 읽은 메시지 개수를 표시한다 (실패해도 메뉴는 그대로 둔다)
async function showUnreadMessageBadge() {
    try {
        const r = await fetch('/api/v1/messages/unread-count');
        if (!r.ok) return;
        const { unread_count } = await r.json();
        if (!unread_count) return;
        document.querySelectorAll('a[href$="messages.html"] .side-icon').forEach(icon => {
            const badge = document.createElement('span');
            badge.textContent = unread_count;
            badge.style.cssText = 'margin-left:auto;background:#dc2626;color:#fff;border-radius:999px;padding:1px 8px;font-size:12px;font-weight:700;';
            icon.parentElement.appendChild(badge);
        });
    } catch (e) {
        // 배지는 부가 기능이므로 실패해도 무시한다
    }
}
