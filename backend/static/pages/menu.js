const SIDEBAR_MENUS = {
    caregiver: [
        { href: 'dashboard.html', icon: '📊', label: '대시보드' },
        { href: 'resident_management.html', icon: '👥', label: '이용자관리' },
        { href: 'voice_record.html', icon: '🎤', label: '음성 기록' },
        { href: 'caregiver_billing.html', icon: '📋', label: '나의 청부' },
        { href: 'my_salary.html', icon: '💵', label: '나의 급여' },
        { href: 'my_schedule.html', icon: '📅', label: '나의 일정' }
    ],
    center_manager: [
        { href: 'dashboard.html', icon: '📊', label: '대시보드' },
        { href: 'resident_management.html', icon: '👥', label: '이용자관리' },
        { href: 'billing_management.html', icon: '💰', label: '청부관리' },
        { href: 'staff_management.html', icon: '👔', label: '직원관리' },
        { href: 'monthly_settlement.html', icon: '📈', label: '월별정산' },
        { href: 'profit_analysis.html', icon: '📊', label: '수익분석' }
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
    const items = SIDEBAR_MENUS[user.role === 'caregiver' ? 'caregiver' : 'center_manager'];
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
}
