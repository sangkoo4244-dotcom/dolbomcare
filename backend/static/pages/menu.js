// 📋 역할별 메뉴 필터링 시스템

function filterMenuByRole() {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const role = user.role || 'caregiver';

    // 모든 메뉴 항목 숨김
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.add('hidden');
    });

    // 공통 메뉴
    const commonMenus = ['menu-dashboard', 'menu-logout'];
    commonMenus.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('hidden');
    });

    // 역할별 메뉴
    if (role === 'caregiver') {
        // 요양사 메뉴
        const caregiverMenus = [
            'menu-residents',      // 이용자 관리 (담당자만)
            'menu-voice-records',  // 음성 기록 (자신의)
            'menu-caregiver-billing',  // 나의 청부
            'menu-my-salary',      // 나의 급여
            'menu-my-schedule'     // 나의 일정
        ];
        caregiverMenus.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.remove('hidden');
        });
    } else if (role === 'center_manager') {
        // 센터장 메뉴 (실제 dashboard.html의 ID와 일치)
        const managerMenus = [
            'menu-residents',              // 이용자 관리 (전체)
            'menu-voice-records',          // 음성 기록 (센터 전체)
            'menu-billing-management',     // 청부 관리
            'menu-staff',                  // 직원 관리
            'menu-profit',                 // 수익 분석
            'menu-roadmap'                 // 성과 로드맵
        ];
        managerMenus.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.remove('hidden');
        });
    }
}

// 역할별 메뉴 ID 매핑
const MENU_IDS = {
    dashboard: 'menu-dashboard',
    residents: 'menu-residents',
    voice: 'menu-voice-records',
    caregiverBilling: 'menu-caregiver-billing',
    mySalary: 'menu-my-salary',
    mySchedule: 'menu-my-schedule',
    billingMgmt: 'menu-billing-mgmt',
    salaryMgmt: 'menu-salary-mgmt',
    scheduleMgmt: 'menu-schedule-mgmt',
    logout: 'menu-logout'
};

// 현재 사용자의 역할 확인
function getCurrentUserRole() {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    return user.role || 'caregiver';
}

// 현재 사용자의 ID 확인
function getCurrentUserId() {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    return user.id;
}

// 현재 사용자의 센터 ID 확인
function getCurrentCenterId() {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    return user.center_id;
}

// 페이지 이동
function navigateTo(url) {
    window.location.href = url;
}

// 로그아웃
function logout() {
    if (confirm('로그아웃 하시겠습니까?')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = './login.html';
    }
}

// 페이지 로드 시 메뉴 필터링
document.addEventListener('DOMContentLoaded', () => {
    // 약간의 지연 후 필터링 (DOM 준비 완료 후)
    setTimeout(() => {
        filterMenuByRole();
    }, 0);
});

// 메뉴 항목 활성화 상태 설정
function setActiveMenu(menuId) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    const activeMenu = document.getElementById(menuId);
    if (activeMenu) {
        activeMenu.classList.add('active');
    }
}
