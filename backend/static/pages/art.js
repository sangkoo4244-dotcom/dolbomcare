// 돌봄케어 선 그림 세트 (직접 그림, 외부 이미지·사진 없음)
// 규칙: 2px 선, 끝을 둥글게, 사람 얼굴 없음, 색은 테마의 세이지·먹색·감색만 쓴다.
// 사용: ART.sprout, ART.window 등 SVG 문자열을 innerHTML에 넣는다.
const ART = {
    // 새싹: 빈 상태 (오늘 방문 없음)
    sprout: `<svg class="art" viewBox="0 0 120 96" aria-hidden="true" focusable="false">
        <path d="M60 90 V50" fill="none" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M60 56 C40 56 30 44 30 28 C46 28 60 38 60 56Z" fill="none" stroke="#6F8F7E" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="M60 50 C74 50 88 40 90 22 C72 22 60 32 60 50Z" fill="none" stroke="#6F8F7E" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="M26 90 H94" stroke="#D9E0DA" stroke-width="2"/>
    </svg>`,

    // 가족: 보호자 연결 전 (이용자가 아직 없음) - 두 사람의 윤곽이 아닌 문과 집 모양
    home: `<svg class="art" viewBox="0 0 120 96" aria-hidden="true" focusable="false">
        <path d="M24 48 L60 18 L96 48" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
        <path d="M34 44 V84 H86 V44" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="M54 84 V64 H68 V84" fill="none" stroke="#B5532F" stroke-width="2.2" stroke-linejoin="round"/>
        <circle cx="76" cy="58" r="2" fill="#B5532F"/>
    </svg>`,

    // 말풍선: 메시지 없음
    message: `<svg class="art" viewBox="0 0 120 96" aria-hidden="true" focusable="false">
        <path d="M20 22 H100 V64 H58 L40 78 V64 H20 Z" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="M36 38 H84 M36 50 H66" stroke="#6F8F7E" stroke-width="2" stroke-linecap="round"/>
    </svg>`,

    // 일지와 도장: 기록 없음
    ledger: `<svg class="art" viewBox="0 0 120 96" aria-hidden="true" focusable="false">
        <path d="M30 14 H84 Q90 14 90 20 V80 Q90 86 84 86 H30 Z" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="M40 34 H78 M40 46 H78 M40 58 H66" stroke="#D9E0DA" stroke-width="2" stroke-linecap="round"/>
        <rect x="70" y="66" width="18" height="18" rx="3" fill="none" stroke="#B5532F" stroke-width="2"/>
        <path d="M74 75 H84" stroke="#B5532F" stroke-width="2" stroke-linecap="round"/>
    </svg>`,

    // 찻잔: 따뜻한 돌봄의 온기 (보호자 가입·연결 안내)
    cup: `<svg class="art" viewBox="0 0 120 96" aria-hidden="true" focusable="false">
        <path d="M38 44 H82 V66 Q82 76 72 76 H48 Q38 76 38 66 Z" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="M82 50 Q98 50 98 60 Q98 70 82 70" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
        <path d="M24 80 H96" stroke="#D9E0DA" stroke-width="2" stroke-linecap="round"/>
        <path d="M52 34 C48 28 56 26 52 20 M66 34 C62 28 70 26 66 20" fill="none" stroke="#B5532F" stroke-width="2" stroke-linecap="round"/>
    </svg>`,
};

// 장면 그림: 익숙한 사물(창문, 찻잔, 화분, 시계, 집)만 쓴다. 얼굴과 신체는 그리지 않는다.
ART.visitScene = `<svg class="art-scene" viewBox="0 0 480 320" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="480" height="320" rx="24" fill="#E8F0EA"/>
    <rect x="56" y="48" width="180" height="150" rx="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M146 48 V198 M56 123 H236" stroke="#1E2B26" stroke-width="2"/>
    <circle cx="200" cy="82" r="18" fill="#F2D7A8"/>
    <path d="M20 232 H460" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="386" cy="84" r="26" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M386 84 V68 M386 84 L398 90" stroke="#B5532F" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M280 150 V206 H316 M284 206 V232 M312 206 V232" fill="none" stroke="#1E2B26" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <ellipse cx="368" cy="206" rx="54" ry="8" fill="none" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M368 214 V232" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M352 178 H384 V196 Q384 204 376 204 H360 Q352 204 352 196 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M384 184 Q394 184 394 191 Q394 198 384 198" fill="none" stroke="#1E2B26" stroke-width="2.2"/>
    <path d="M362 170 C358 164 366 162 362 156 M374 170 C370 164 378 162 374 156" fill="none" stroke="#B5532F" stroke-width="2" stroke-linecap="round"/>
    <path d="M96 190 H140 L134 228 H102 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M118 190 C104 170 100 158 110 146 C120 158 122 172 118 190 Z" fill="#A9C2B3"/>
    <path d="M118 190 C130 172 140 164 152 166 C146 180 134 190 118 190 Z" fill="#6F8F7E"/>
    <path d="M118 190 C112 176 116 162 128 154 C130 168 126 182 118 190 Z" fill="#A9C2B3"/>
    <rect x="404" y="252" width="44" height="44" rx="6" fill="none" stroke="#B5532F" stroke-width="2.5" transform="rotate(-6 426 274)"/>
    <text x="426" y="282" text-anchor="middle" font-family="Gowun Batang, serif" font-size="22" font-weight="700" fill="#B5532F" transform="rotate(-6 426 274)">완</text>
</svg>`;

// 집 장면: 보호자 화면 맨 위. 붉은 지붕, 불 켜진 창, 나무, 길
ART.homeScene = `<svg class="art-scene" viewBox="0 0 480 200" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="480" height="200" rx="20" fill="#E8F0EA"/>
    <circle cx="410" cy="56" r="22" fill="#F2D7A8"/>
    <path d="M0 170 H480" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="150" y="78" width="180" height="92" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M136 82 L240 22 L344 82 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="2.5" stroke-linejoin="round"/>
    <rect x="226" y="118" width="28" height="52" fill="none" stroke="#1E2B26" stroke-width="2.2"/>
    <rect x="168" y="102" width="44" height="36" fill="#F2D7A8" stroke="#1E2B26" stroke-width="2"/>
    <path d="M190 102 V138" stroke="#1E2B26" stroke-width="2"/>
    <rect x="268" y="102" width="44" height="36" fill="#F2D7A8" stroke="#1E2B26" stroke-width="2"/>
    <path d="M290 102 V138" stroke="#1E2B26" stroke-width="2"/>
    <rect x="86" y="112" width="10" height="58" fill="#55645D"/>
    <circle cx="91" cy="96" r="30" fill="#A9C2B3"/>
    <rect x="372" y="118" width="10" height="52" fill="#55645D"/>
    <circle cx="377" cy="92" r="26" fill="#6F8F7E"/>
    <path d="M240 170 V176" stroke="#1E2B26" stroke-width="2.2"/>
</svg>`;

// 출근 장면: 요양보호사 대시보드 맨 위. 현관문, 가방, 벽시계, 일정 달력, 화분
ART.caregiverScene = `<svg class="art-scene" viewBox="0 0 480 180" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="480" height="180" rx="20" fill="#E8F0EA"/>
    <path d="M16 150 H464" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="40" y="26" width="92" height="124" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.5"/>
    <rect x="54" y="40" width="64" height="98" fill="none" stroke="#1E2B26" stroke-width="1.5" opacity="0.45"/>
    <circle cx="118" cy="98" r="3.5" fill="#B5532F"/>
    <rect x="150" y="104" width="56" height="46" rx="6" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <path d="M164 104 Q178 82 192 104" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M150 124 H206" stroke="#6F8F7E" stroke-width="2"/>
    <circle cx="296" cy="72" r="28" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M296 72 V56 M296 72 L308 80" stroke="#B5532F" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="346" y="34" width="100" height="84" rx="6" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <rect x="346" y="34" width="100" height="18" rx="6" fill="#B5532F"/>
    <rect x="346" y="46" width="100" height="6" fill="#B5532F"/>
    <rect x="358" y="62" width="10" height="8" fill="#D9E0DA"/><rect x="376" y="62" width="10" height="8" fill="#D9E0DA"/>
    <rect x="394" y="62" width="10" height="8" fill="#D9E0DA"/><rect x="412" y="62" width="10" height="8" fill="#B5532F"/>
    <rect x="358" y="78" width="10" height="8" fill="#D9E0DA"/><rect x="376" y="78" width="10" height="8" fill="#D9E0DA"/>
    <rect x="394" y="78" width="10" height="8" fill="#B5532F"/><rect x="412" y="78" width="10" height="8" fill="#D9E0DA"/>
    <rect x="358" y="94" width="10" height="8" fill="#D9E0DA"/><rect x="376" y="94" width="10" height="8" fill="#D9E0DA"/>
    <rect x="394" y="94" width="10" height="8" fill="#D9E0DA"/><rect x="412" y="94" width="10" height="8" fill="#D9E0DA"/>
    <path d="M238 124 H264 L260 150 H242 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M251 124 C240 108 238 98 246 90 C250 104 253 114 251 124 Z" fill="#A9C2B3"/>
    <path d="M251 124 C260 108 268 102 278 102 C276 114 266 122 251 124 Z" fill="#6F8F7E"/>
</svg>`;
