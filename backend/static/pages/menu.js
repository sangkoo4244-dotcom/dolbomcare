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


// 메뉴 아이콘: 색 타일 위에 그림 하나 (직접 그림, 얼굴 없음). 글자색과 무관하게 색을 가진다
const MENU_TILE = (tile, shadow, inner) => `<svg viewBox="0 0 40 40" width="24" height="24" aria-hidden="true" focusable="false"><rect x="0" y="0" width="40" height="40" rx="11" fill="${tile}"/><ellipse cx="20" cy="34" rx="11" ry="2" fill="${shadow}" opacity="0.5"/>${inner}</svg>`;
const MENU_ICONS = {
    dashboard: '<img src="assets/user_design/20_nav_dashboard_icon.png" width="24" height="24" alt="">',
    residents: '<img src="assets/user_design/21_nav_user_icon.png" width="24" height="24" alt="">',
    voice: '<img src="assets/user_design/22_nav_voice_icon.png" width="24" height="24" alt="">',
    billing: '<img src="assets/user_design/24_nav_billing_icon.png" width="24" height="24" alt="">',
    salary: '<img src="assets/user_design/25_nav_statistics_icon.png" width="24" height="24" alt="">',
    schedule: '<img src="assets/user_design/23_nav_service_plan_icon.png" width="24" height="24" alt="">',
    notify: '<img src="assets/user_design/26_nav_notice_icon.png" width="24" height="24" alt="">',
    settings: '<img src="assets/user_design/27_nav_settings_icon.png" width="24" height="24" alt="">',
    messages: MENU_TILE('#E8F0EA', '#55645D', '<path d="M9 11 H24 V20 H16 L12 23 V20 H9 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><path d="M18 17 H31 V26 H29 V29 L26 26 H18 Z" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1.2" stroke-linejoin="round"/>'),
    home: MENU_TILE('#F6E4DC', '#9A4425', '<path d="M8 20 L20 9 L32 20 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><path d="M11 19 V31 H29 V19 L20 12 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><rect x="17.5" y="24" width="5" height="7" rx="1" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1"/>'),
    schedule_check: MENU_TILE('#E8F0EA', '#55645D', '<rect x="10" y="8" width="20" height="25" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="15" y="5.5" width="10" height="5" rx="2" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2"/><path d="M14 20 L17 23 L23 17" fill="none" stroke="#6F8F7E" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><rect x="14" y="27" width="12" height="2.2" rx="1.1" fill="#D9E0DA"/>'),
    staff: MENU_TILE('#E8F0EA', '#55645D', '<path d="M17 9 L20 5 L23 9" fill="none" stroke="#1E2B26" stroke-width="1.2"/><rect x="12" y="9" width="16" height="22" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><circle cx="20" cy="18" r="3.2" fill="#6F8F7E"/><path d="M15 27 Q15 23 20 23 Q25 23 25 27 Z" fill="#B5532F"/>'),
    settlement: MENU_TILE('#F6E4DC', '#9A4425', '<rect x="8" y="10" width="24" height="22" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><path d="M8 17 H32 V14 A4 4 0 0 0 28 10 H12 A4 4 0 0 0 8 14 Z" fill="#6F8F7E"/><rect x="12" y="21" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="18" y="21" width="4" height="3" rx="0.8" fill="#B5532F"/><rect x="24" y="21" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="12" y="26" width="4" height="3" rx="0.8" fill="#D9E0DA"/>'),
    profit: MENU_TILE('#E8F0EA', '#55645D', '<rect x="8" y="8" width="24" height="24" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="12" y="20" width="3.5" height="8" rx="1" fill="#6F8F7E"/><rect x="18" y="15" width="3.5" height="13" rx="1" fill="#B5532F"/><rect x="24" y="11" width="3.5" height="17" rx="1" fill="#6F8F7E"/>'),
    guardian: MENU_TILE('#E8F0EA', '#55645D', '<path d="M20 7 L30 11 V19 Q30 27 20 32 Q10 27 10 19 V11 Z" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><path d="M15 20 L20 15 L25 20 V25 H15 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1"/>'),
    stamp: MENU_TILE('#F6E4DC', '#9A4425', '<path d="M11 8 H23 L29 14 V31 H11 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><rect x="14" y="18" width="11" height="2.2" rx="1.1" fill="#6F8F7E"/><rect x="14" y="23" width="8" height="2.2" rx="1.1" fill="#6F8F7E" opacity="0.7"/><circle cx="25" cy="27" r="5" fill="#A8432A" stroke="#1E2B26" stroke-width="1"/><path d="M22.8 27 L24.3 28.5 L27.4 25.5" fill="none" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'),
};

const SIDEBAR_MENUS = {
    caregiver: [
        { href: 'dashboard.html', icon: 'dashboard', label: '대시보드' },
        { href: 'resident_management.html', icon: 'residents', label: '이용자 관리' },
        { href: 'voice_record.html', icon: 'voice', label: '음성 기록' },
        { href: 'my_schedule.html', icon: 'schedule', label: '서비스 계획' },
        { href: 'caregiver_billing.html', icon: 'billing', label: '청구 관리' },
        { href: 'my_salary.html', icon: 'salary', label: '통계 현황' },
        { href: 'notifications.html', icon: 'notify', label: '공지사항' },
        { href: 'messages.html', icon: 'messages', label: '보호자 소통' },
        { href: '#', icon: 'settings', label: '설정' }
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
.side-icon svg { display: block; width: 24px; height: 24px; }
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
            <span class="side-icon">${MENU_TILE('#E8F0EA', '#55645D', '<rect x="10" y="8" width="18" height="25" rx="2" fill="#8A4A2B" stroke="#1E2B26" stroke-width="1.4"/><circle cx="24" cy="21" r="1.6" fill="#E8B04A"/><path d="M24 20 H33 M30 16 L34 20 L30 24" fill="none" stroke="#B5532F" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')}</span>
            <span>로그아웃</span>
        </a>
    `;
    if (roleMenu === 'caregiver') nav.insertAdjacentHTML('beforeend', '<img class="side-land" src="assets/user_design/19_sidebar_bottom_landscape.png" alt="" style="display:block;width:100%;margin-top:24px;pointer-events:none;">');
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
