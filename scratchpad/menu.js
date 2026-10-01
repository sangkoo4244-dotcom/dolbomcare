// 공통 메뉴 필터링 스크립트
// 각 페이지의 기존 checkAuth() 이후에만 실행됨

// 권한별 메뉴 제어 (각 페이지에서 checkAuth() 후 호출)
function filterMenuByRole() {
    // currentUser는 각 페이지의 checkAuth()에서 설정됨
    if (typeof currentUser === 'undefined' || !currentUser) {
        console.warn('⚠️ currentUser가 아직 설정되지 않음');
        setTimeout(() => filterMenuByRole(), 100);  // 재시도
        return;
    }

    console.log('🔐 filterMenuByRole 호출:', currentUser.role);

    const role = currentUser.role;
    const isCaregiver = role === 'caregiver';
    const isManager = role === 'center_manager';

    const menuItems = {
        'menu-dashboard': true,                    // 모두 볼 수 있음 (역할별 다른 데이터 표시)
        'menu-residents': isManager,               // 센터장만
        'menu-voice-records': isCaregiver,         // 요양사만
        'menu-caregiver-billing': isCaregiver,     // 요양사만
        'menu-billing-management': isManager,      // 센터장만
        'menu-logout': true                        // 항상
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

// DOMContentLoaded에서 메뉴 필터링 준비
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOMContentLoaded: 메뉴 필터링 준비');
    // 각 페이지의 checkAuth()가 호출될 때까지 대기
});

// load 이벤트에서 최종 필터링
window.addEventListener('load', () => {
    console.log('🔍 load 이벤트: 메뉴 필터링 실행');
    if (typeof currentUser !== 'undefined' && currentUser) {
        filterMenuByRole();
    }
});
