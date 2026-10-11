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


// "오늘 날짜"는 항상 이걸로 구한다. new Date().toISOString().slice(0,10)은 UTC 기준이라
// 한국 시간 자정~오전 9시 사이에는 실제로는 오늘인데 어제 날짜를 돌려준다 (실제 버그였음 - 2026-10-12
// 아침에 음성기록 기본 방문일시가 전날로 잡히고, "오늘 방문 예정" 패널이 비어보이는 문제로 발견됨).
function todayLocal(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// 메뉴 아이콘: 색 타일 위에 그림 하나 (직접 그림, 얼굴 없음). 글자색과 무관하게 색을 가진다
const MENU_TILE = (tile, shadow, inner) => `<svg viewBox="0 0 40 40" width="24" height="24" aria-hidden="true" focusable="false"><rect x="0" y="0" width="40" height="40" rx="11" fill="${tile}"/><ellipse cx="20" cy="34" rx="11" ry="2" fill="${shadow}" opacity="0.5"/>${inner}</svg>`;
const MENU_ICONS = {
    dashboard: '<img src="assets/user_design/icon_menu_dashboard.png" width="24" height="24" alt="">',
    residents: '<img src="assets/user_design/icon_menu_user.png" width="24" height="24" alt="">',
    voice: '<img src="assets/user_design/icon_menu_voice.png" width="24" height="24" alt="">',
    billing: '<img src="assets/user_design/icon_menu_document.png" width="24" height="24" alt="">',
    salary: '<img src="assets/user_design/icon_menu_payment.png" width="24" height="24" alt="">',
    schedule: MENU_TILE('#E8F0EA', '#55645D', '<rect x="8" y="10" width="24" height="22" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><path d="M8 17 H32 V14 A4 4 0 0 0 28 10 H12 A4 4 0 0 0 8 14 Z" fill="#B5532F"/><rect x="13" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><rect x="24" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><circle cx="20" cy="25" r="3.6" fill="#6F8F7E"/><circle cx="20" cy="25" r="1.4" fill="#FFFFFF"/>'),
    notify: MENU_TILE('#F6E4DC', '#9A4425', '<path d="M12 26 V19 A8 8 0 0 1 28 19 V26 L30 28 H10 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><path d="M17 31 H23" stroke="#1E2B26" stroke-width="1.6" stroke-linecap="round"/><circle cx="29" cy="11" r="3" fill="#B5532F"/>'),
    messages: MENU_TILE('#E8F0EA', '#55645D', '<path d="M9 11 H24 V20 H16 L12 23 V20 H9 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><path d="M18 17 H31 V26 H29 V29 L26 26 H18 Z" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1.2" stroke-linejoin="round"/>'),
    home: MENU_TILE('#F6E4DC', '#9A4425', '<path d="M8 20 L20 9 L32 20 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><path d="M11 19 V31 H29 V19 L20 12 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><rect x="17.5" y="24" width="5" height="7" rx="1" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1"/>'),
    schedule_check: MENU_TILE('#E8F0EA', '#55645D', '<rect x="10" y="8" width="20" height="25" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="15" y="5.5" width="10" height="5" rx="2" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2"/><path d="M14 20 L17 23 L23 17" fill="none" stroke="#6F8F7E" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><rect x="14" y="27" width="12" height="2.2" rx="1.1" fill="#D9E0DA"/>'),
    staff: MENU_TILE('#E8F0EA', '#55645D', '<path d="M17 9 L20 5 L23 9" fill="none" stroke="#1E2B26" stroke-width="1.2"/><rect x="12" y="9" width="16" height="22" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><circle cx="20" cy="18" r="3.2" fill="#6F8F7E"/><path d="M15 27 Q15 23 20 23 Q25 23 25 27 Z" fill="#B5532F"/>'),
    settlement: MENU_TILE('#F6E4DC', '#9A4425', '<rect x="8" y="10" width="24" height="22" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><path d="M8 17 H32 V14 A4 4 0 0 0 28 10 H12 A4 4 0 0 0 8 14 Z" fill="#6F8F7E"/><rect x="12" y="21" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="18" y="21" width="4" height="3" rx="0.8" fill="#B5532F"/><rect x="24" y="21" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="12" y="26" width="4" height="3" rx="0.8" fill="#D9E0DA"/>'),
    profit: MENU_TILE('#E8F0EA', '#55645D', '<rect x="8" y="8" width="24" height="24" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="12" y="20" width="3.5" height="8" rx="1" fill="#6F8F7E"/><rect x="18" y="15" width="3.5" height="13" rx="1" fill="#B5532F"/><rect x="24" y="11" width="3.5" height="17" rx="1" fill="#6F8F7E"/>'),
    guardian: MENU_TILE('#E8F0EA', '#55645D', '<path d="M20 7 L30 11 V19 Q30 27 20 32 Q10 27 10 19 V11 Z" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><path d="M15 20 L20 15 L25 20 V25 H15 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1"/>'),
    stamp: MENU_TILE('#F6E4DC', '#9A4425', '<path d="M11 8 H23 L29 14 V31 H11 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><rect x="14" y="18" width="11" height="2.2" rx="1.1" fill="#6F8F7E"/><rect x="14" y="23" width="8" height="2.2" rx="1.1" fill="#6F8F7E" opacity="0.7"/><circle cx="25" cy="27" r="5" fill="#A8432A" stroke="#1E2B26" stroke-width="1"/><path d="M22.8 27 L24.3 28.5 L27.4 25.5" fill="none" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'),
    center: MENU_TILE('#F6E4DC', '#9A4425', '<rect x="9" y="11" width="22" height="21" rx="2" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="13" y="15" width="4" height="4" fill="#6F8F7E"/><rect x="23" y="15" width="4" height="4" fill="#6F8F7E"/><rect x="13" y="22" width="4" height="4" fill="#6F8F7E"/><rect x="23" y="22" width="4" height="4" fill="#B5532F"/><rect x="17" y="6" width="6" height="7" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.2"/>'),
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
        { href: 'ltci_guide.html', icon: 'stamp', label: '장기요양 신청 안내' },
        { href: 'notifications.html', icon: 'notify', label: '알림' },
        { href: 'messages.html', icon: 'messages', label: '센터와 메시지' }
    ],
    center_manager: [
        { href: 'dashboard.html', icon: 'dashboard', label: '대시보드' },
        { href: 'resident_management.html', icon: 'residents', label: '이용자관리' },
        { href: 'guardian_management.html', icon: 'guardian', label: '보호자 관리' },
        { href: 'voice_record.html', icon: 'voice', label: '음성 기록' },
        { href: 'schedule_approval.html', icon: 'schedule_check', label: '방문계획 승인' },
        { href: 'billing_management.html', icon: 'billing', label: '청부관리' },
        { href: 'copay_management.html', icon: 'billing', label: '본인부담금' },
        { href: 'audit_prep.html', icon: 'billing', label: '평가 준비 자료' },
        { href: 'staff_management.html', icon: 'staff', label: '직원관리' },
        { href: 'center_settings.html', icon: 'center', label: '센터 정보' },
        { href: 'monthly_settlement.html', icon: 'settlement', label: '월별정산' },
        { href: 'profit_analysis.html', icon: 'profit', label: '수익분석' },
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
    nav.style.overflowY = 'auto';
    nav.style.flex = '1 1 auto';
    nav.style.minHeight = '0';
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
    showUnreadMessageBadge();

    // groupSidebar()가 #navContent 안쪽을 통째로 다시 그리므로, 거기 휩쓸리지 않게 nav 바깥(aside)에 따로 붙인다
    if (!document.getElementById('sideCredit') && nav.parentElement) {
        const credit = document.createElement('div');
        credit.id = 'sideCredit';
        credit.style.cssText = 'flex: 0 0 auto; padding: 12px 16px 16px; border-top: 1px solid #374151; font-size: 11px; line-height: 1.8;';
        credit.innerHTML = `
            <a href="https://seniorcareinfo.kr/" target="_blank" rel="noopener" style="display:block; color: #9ca3af; text-decoration: none; font-weight: 700;">이음로직</a>
            <a href="https://seniorcareinfo.kr/" target="_blank" rel="noopener" style="display:block; color: #6b7280; text-decoration: none;">https://seniorcareinfo.kr</a>
        `;
        nav.parentElement.appendChild(credit);
    }

    showAdminConsoleLinkIfOperator();
    initProfileMenu();
}

// 이음로직 운영자 계정으로 로그인했을 때만 사이드바 하단에 운영자 콘솔 링크를 보여준다.
// 일반 센터장/요양사 계정에는 평생 안 보인다 (요청이 403이면 그냥 조용히 넘어간다).
async function showAdminConsoleLinkIfOperator() {
    if (document.getElementById('adminConsoleLink')) return;
    try {
        const res = await fetch('/api/v1/admin/is-admin');
        if (!res.ok) return;
        const credit = document.getElementById('sideCredit');
        if (!credit) return;
        const link = document.createElement('a');
        link.id = 'adminConsoleLink';
        link.href = './admin_alimtalk.html';
        link.textContent = '운영자 콘솔';
        link.style.cssText = 'display:block; margin-top: 10px; color: #fbbf24; text-decoration: none; font-weight: 700;';
        credit.appendChild(link);
    } catch (e) { /* 네트워크 오류는 무시 - 없어도 메뉴는 정상 동작해야 한다 */ }
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

// ===== 내 프로필 (상단 이름/아바타 클릭 시 열림) - 모든 역할 공통, menu.js가 모든 화면에 로드되므로 여기 한 번만 구현한다 =====
let profileMenuInitialized = false;
let pmPendingImage = null;
const PROFILE_ROLE_LABEL = { caregiver: '요양보호사', center_manager: '센터장', guardian: '보호자' };

function initProfileMenu() {
    if (profileMenuInitialized) return;
    profileMenuInitialized = true;
    injectProfileModal();

    const attachClick = (el) => {
        if (!el) return;
        el.style.cursor = 'pointer';
        el.title = '내 프로필 수정';
        el.addEventListener('click', openProfileModal);
    };
    attachClick(document.getElementById('userName'));
    attachClick(document.getElementById('userAvatar'));
}

function injectProfileModal() {
    if (document.getElementById('profileModalBackdrop')) return;

    const style = document.createElement('style');
    style.textContent = `
        .pm-backdrop { display:none; position:fixed; inset:0; background:rgba(20,40,63,0.45); z-index:3000; align-items:center; justify-content:center; }
        .pm-backdrop.open { display:flex; }
        .pm-box { background:#fff; border-radius:14px; padding:28px; width:380px; max-width:90vw; font-family:'Pretendard','Noto Sans KR',-apple-system,system-ui,sans-serif; }
        .pm-box h3 { margin:0 0 18px; font-size:17px; color:#14283F; }
        .pm-avatar-row { display:flex; align-items:center; gap:14px; margin-bottom:18px; }
        .pm-avatar-row img { width:64px; height:64px; border-radius:50%; object-fit:cover; background:#F1F5F9; }
        .pm-field { margin-bottom:12px; }
        .pm-field label { display:block; font-size:12px; font-weight:700; color:#64748B; margin-bottom:4px; }
        .pm-field input { width:100%; box-sizing:border-box; padding:8px 10px; border:2px solid #E2E8F0; border-radius:8px; font-size:13px; }
        .pm-field input:disabled { background:#F8FAFC; color:#94A3B8; }
        .pm-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:18px; }
        .pm-btn-outline { padding:8px 16px; border-radius:9px; font-size:13px; font-weight:700; border:1.5px solid #E2E8F0; background:#fff; color:#243247; cursor:pointer; }
        .pm-btn-solid { padding:8px 16px; border-radius:9px; font-size:13px; font-weight:700; border:none; background:#0F8B80; color:#fff; cursor:pointer; }
        .pm-msg { font-size:12px; margin-top:8px; display:none; }
        .pm-msg.ok { color:#15803D; display:block; }
        .pm-msg.err { color:#DC2626; display:block; }
    `;
    document.head.appendChild(style);

    const box = document.createElement('div');
    box.className = 'pm-backdrop';
    box.id = 'profileModalBackdrop';
    box.innerHTML = `
        <div class="pm-box">
            <h3>내 프로필</h3>
            <div class="pm-avatar-row">
                <img id="pmAvatarPreview" src="assets/user_design/29_top_profile_icon.png" alt="">
                <label class="pm-btn-outline" style="cursor:pointer;">
                    사진 변경
                    <input type="file" accept="image/*" id="pmPhotoInput" style="display:none;" onchange="handleProfilePhotoChange(event)">
                </label>
            </div>
            <div class="pm-field"><label>이름</label><input id="pmFullName"></div>
            <div class="pm-field"><label>연락처</label><input id="pmPhone"></div>
            <div class="pm-field"><label>이메일</label><input id="pmEmail" disabled></div>
            <div class="pm-field"><label>역할</label><input id="pmRole" disabled></div>
            <div class="pm-msg" id="pmMsg"></div>
            <div class="pm-actions">
                <button type="button" class="pm-btn-outline" onclick="closeProfileModal()">취소</button>
                <button type="button" class="pm-btn-solid" onclick="saveProfile()">저장</button>
            </div>
        </div>
    `;
    document.body.appendChild(box);
}

async function openProfileModal() {
    document.getElementById('profileModalBackdrop').classList.add('open');
    document.getElementById('pmMsg').className = 'pm-msg';
    pmPendingImage = null;
    try {
        const r = await fetch('/api/v1/users/me');
        if (!r.ok) throw new Error();
        const d = await r.json();
        document.getElementById('pmFullName').value = d.full_name || '';
        document.getElementById('pmPhone').value = d.phone || '';
        document.getElementById('pmEmail').value = d.email || '';
        document.getElementById('pmRole').value = PROFILE_ROLE_LABEL[d.role] || d.role;
        document.getElementById('pmAvatarPreview').src = d.profile_image || 'assets/user_design/29_top_profile_icon.png';
    } catch (e) {
        // 조회 실패해도 모달은 열어 두고 빈 값으로 둔다
    }
}

function closeProfileModal() {
    document.getElementById('profileModalBackdrop').classList.remove('open');
}

function pmResizeImageFile(file, maxDim = 480, quality = 0.8) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const img = new Image();
            img.onload = () => {
                let { width, height } = img;
                if (width > maxDim || height > maxDim) {
                    const scale = maxDim / Math.max(width, height);
                    width = Math.round(width * scale);
                    height = Math.round(height * scale);
                }
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                canvas.getContext('2d').drawImage(img, 0, 0, width, height);
                resolve(canvas.toDataURL('image/jpeg', quality));
            };
            img.onerror = reject;
            img.src = reader.result;
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function handleProfilePhotoChange(event) {
    const file = event.target.files[0];
    if (!file) return;
    try {
        pmPendingImage = await pmResizeImageFile(file);
        document.getElementById('pmAvatarPreview').src = pmPendingImage;
    } catch (e) {
        alert('사진을 불러오지 못했습니다');
    }
}

async function saveProfile() {
    const body = {
        full_name: document.getElementById('pmFullName').value,
        phone: document.getElementById('pmPhone').value,
    };
    if (pmPendingImage) body.profile_image = pmPendingImage;

    const msg = document.getElementById('pmMsg');
    try {
        const r = await fetch('/api/v1/users/me', {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.detail || '저장에 실패했습니다');

        const user = JSON.parse(localStorage.getItem('user') || '{}');
        user.full_name = d.data.full_name;
        user.phone = d.data.phone;
        user.profile_image = d.data.profile_image;
        localStorage.setItem('user', JSON.stringify(user));

        msg.textContent = '저장되었습니다';
        msg.className = 'pm-msg ok';
        setTimeout(() => window.location.reload(), 600);
    } catch (e) {
        msg.textContent = e.message;
        msg.className = 'pm-msg err';
    }
}
