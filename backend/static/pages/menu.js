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

function renderSidebar() {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const items = SIDEBAR_MENUS[user.role === 'caregiver' ? 'caregiver' : 'center_manager'];
    const current = window.location.pathname.split('/').pop();
    const nav = document.querySelector('.sidebar-nav');
    nav.innerHTML = items.map(item => `
        <a href="./${item.href}" class="nav-item ${item.href === current ? 'active' : ''}">
            <span>${item.icon}</span>
            <span>${item.label}</span>
        </a>
    `).join('') + `
        <a class="nav-item" style="margin-top: 30px;" onclick="logout()">
            <span>🚪</span>
            <span>로그아웃</span>
        </a>
    `;
}
