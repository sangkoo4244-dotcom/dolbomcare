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
        'menu-dashboard': true,                      // 모두 볼 수 있음 (역할별 다른 데이터 표시)
        'menu-residents': true,                      // 모두 볼 수 있음 (요양사는 조회만)

        // 요양사 전용 메뉴
        'menu-voice-records': isCaregiver,           // 요양사 - 음성 기록
        'menu-caregiver-billing': isCaregiver,       // 요양사 - 나의 청부
        'menu-notifications': isCaregiver,           // 요양사 - 알림/공지
        'menu-my-schedule': isCaregiver,             // 요양사 - 나의 일정 (휴무 신청, 스케줄)
        'menu-my-salary': isCaregiver,               // 요양사 - 나의 급여 (정산 현황)
        'menu-resident-family-comm': isCaregiver,    // 요양사 - 담당자 소통

        // 센터장 전용 메뉴
        'menu-billing-management': isManager,        // 센터장 - 청부 관리 (전체)
        'menu-staff': isManager,                     // 센터장 - 직원 관리 (전체)
        'menu-schedule': isManager,                  // 센터장 - 스케줄 관리 (전체 근무표)
        'menu-guardian-comm': isManager,             // 센터장 - 보호자 소통 (센터 공지)
        'menu-profit': isManager,                    // 센터장 - 손익 분석 (급여정보 통합)
        'menu-roadmap': isManager,                   // 센터장 - 성장 로드맵 (12개월 계획)
        'menu-settings': isManager,                  // 센터장 - 설정

        // 공용
        'menu-logout': true                          // 항상
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
