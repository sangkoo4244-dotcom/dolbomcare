// 공통 메뉴 필터링 스크립트
// 모든 페이지에서 이 파일을 로드해야 합니다

let currentUser = null;

// 권한별 메뉴 제어
function filterMenuByRole() {
    console.log('🔐 filterMenuByRole 호출:', currentUser?.role);

    if (!currentUser) {
        console.warn('⚠️ currentUser가 없음');
        return;
    }

    const role = currentUser.role;
    const isCaregiver = role === 'caregiver';
    const isManager = role === 'center_manager';

    const menuItems = {
        'menu-dashboard': !isCaregiver,
        'menu-residents': !isCaregiver,
        'menu-voice-records': isCaregiver,
        'menu-caregiver-billing': isCaregiver,
        'menu-billing-management': isManager,
        'menu-logout': true
    };

    Object.entries(menuItems).forEach(([id, shouldShow]) => {
        const el = document.getElementById(id);
        if (el) {
            if (shouldShow) {
                el.classList.remove('hidden');
            } else {
                el.classList.add('hidden');
            }
        }
    });
}

// 인증 확인
function checkAuth() {
    const token = localStorage.getItem('access_token');
    const user = JSON.parse(localStorage.getItem('user'));

    if (!token || !user) {
        window.location.href = './login.html';
        return false;
    }

    currentUser = user;

    // UI 업데이트
    const userName = document.getElementById('userName');
    const userRole = document.getElementById('userRole');
    const userAvatar = document.getElementById('userAvatar');

    if (userName) userName.textContent = user.full_name || '사용자';
    if (userRole) userRole.textContent = user.role === 'caregiver' ? '요양사' : user.role === 'center_manager' ? '센터장' : '사용자';
    if (userAvatar) userAvatar.textContent = (user.full_name || '사용자').charAt(0).toUpperCase();

    // 권한별 메뉴 필터링
    filterMenuByRole();
    return true;
}

// 로그아웃
function logout() {
    if (confirm('로그아웃 하시겠습니까?')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('user_role');
        window.location.href = './login.html';
    }
}

// 페이지 이동
function navigateTo(url) {
    window.location.href = url;
}

// 페이지 로드 시 초기화
function initializeMenu() {
    console.log('📄 메뉴 초기화 시작');
    checkAuth();
}

// DOMContentLoaded에서 즉시 인증 확인
document.addEventListener('DOMContentLoaded', initializeMenu);

// load 이벤트에서도 재확인
window.addEventListener('load', () => {
    if (!currentUser) {
        initializeMenu();
    }
});
