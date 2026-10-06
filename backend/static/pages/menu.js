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


// 메뉴 아이콘: 도장 테두리 안에 사물 하나. 색은 글자색을 따른다 (currentColor)
const MENU_ICONS = {
    dashboard: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M8 20 H24 M11 20 A5 5 0 0 1 21 20"/></svg>',
    residents: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M9 15 L16 9 L23 15 V23 H9 Z"/></svg>',
    voice: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M9 22 L10 18 L21 7 L25 11 L14 22 Z M19 9 L23 13"/></svg>',
    billing: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><rect x="9" y="8" width="14" height="16" rx="1.5"/><path d="M12 13 H20 M12 17 H18"/></svg>',
    salary: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M9 13 H23 V21 H9 Z M12 17 H20"/></svg>',
    schedule: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><rect x="8" y="9" width="16" height="14" rx="1.5"/><path d="M8 14 H24 M12 7 V11 M20 7 V11"/></svg>',
    notify: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M10 21 V15 A6 6 0 0 1 22 15 V21 L24 23 H8 Z M14 25 H18"/></svg>',
    messages: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M8 9 H24 V20 H15 L11 23 V20 H8 Z"/></svg>',
    home: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M8 15 L16 8 L24 15 V24 H8 Z M14 24 V19 H18 V24"/></svg>',
    guardian: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M9 14 H23 V19 A7 5 0 0 1 9 19 Z M23 15 Q26 15 26 17 Q26 19 23 19 M12 9 V11 M16 8 V11 M20 9 V11"/></svg>',
    schedule_check: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><rect x="8" y="8" width="16" height="16" rx="1.5"/><path d="M12 16 L15 19 L21 13"/></svg>',
    staff: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><rect x="9" y="8" width="14" height="16" rx="2"/><path d="M13 8 V6 H19 V8 M12 16 H20 M12 19 H17"/></svg>',
    settlement: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M16 8 V24 M9 12 H23 M9 12 L7 18 H13 Z M23 12 L21 18 H27 Z" transform="translate(-1 0)"/></svg>',
    profit: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><path d="M9 22 V18 M14 22 V14 M19 22 V11 M24 22 V9"/></svg>',
    stamp: '<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="28" height="28" rx="7"/><rect x="9" y="9" width="14" height="14" rx="2"/><path d="M13 16 L15.5 18.5 L20 13.5"/></svg>',
};

const SIDEBAR_MENUS = {
    caregiver: [
        { href: 'dashboard.html', icon: 'dashboard', label: '대시보드' },
        { href: 'resident_management.html', icon: 'residents', label: '이용자관리' },
        { href: 'voice_record.html', icon: 'voice', label: '음성 기록' },
        { href: 'caregiver_billing.html', icon: 'billing', label: '나의 청부' },
        { href: 'my_salary.html', icon: 'salary', label: '나의 급여' },
        { href: 'my_schedule.html', icon: 'schedule', label: '나의 일정' },
        { href: 'notifications.html', icon: 'notify', label: '알림' },
        { href: 'messages.html', icon: 'messages', label: '보호자 소통' }
    ],
    guardian: [
        { href: 'guardian_home.html', icon: 'home', label: '이용자 방문 기록' },
        { href: 'messages.html', icon: 'messages', label: '센터와 메시지' }
    ],
    center_manager: [
        { href: 'dashboard.html', icon: 'dashboard', label: '대시보드' },
        { href: 'resident_management.html', icon: 'residents', label: '이용자관리' },
        { href: 'voice_record.html', icon: 'voice', label: '음성 기록' },
        { href: 'schedule_approval.html', icon: 'schedule_check', label: '방문계획 승인' },
        { href: 'billing_management.html', icon: 'billing', label: '청부관리' },
        { href: 'staff_management.html', icon: 'staff', label: '직원관리' },
        { href: 'monthly_settlement.html', icon: 'settlement', label: '월별정산' },
        { href: 'profit_analysis.html', icon: 'profit', label: '수익분석' },
        { href: 'guardian_management.html', icon: 'guardian', label: '보호자 관리' },
        { href: 'statement_confirm.html', icon: 'stamp', label: '급여 확정' },
        { href: 'messages.html', icon: 'messages', label: '보호자 소통' }
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
            <span class="side-icon">${MENU_ICONS[item.icon] || item.icon}</span>
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
