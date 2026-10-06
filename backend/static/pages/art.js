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

// 기록 장면: 음성 기록 화면 맨 위. 펼친 일지, 펜, 마이크, 도장, 찻잔
ART.recordScene = `<svg class="art-scene" viewBox="0 0 480 160" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="480" height="160" rx="20" fill="#E8F0EA"/>
    <path d="M20 132 H460" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M150 42 H236 V126 H150 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M236 42 H322 V126 H236 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M236 42 V126" stroke="#1E2B26" stroke-width="2"/>
    <path d="M168 62 H218 M168 76 H218 M168 90 H204" stroke="#D9E0DA" stroke-width="3" stroke-linecap="round"/>
    <path d="M254 62 H304 M254 76 H304 M254 90 H290" stroke="#D9E0DA" stroke-width="3" stroke-linecap="round"/>
    <rect x="266" y="102" width="26" height="18" rx="3" fill="none" stroke="#B5532F" stroke-width="2.2" transform="rotate(-6 279 111)"/>
    <path d="M282 110 L290 102 L296 108 L288 116 Z" fill="none" stroke="#1E2B26" stroke-width="2" stroke-linejoin="round"/>
    <rect x="354" y="58" width="16" height="44" rx="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <path d="M346 82 V92 Q346 108 362 108 Q378 108 378 92 V82" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M362 108 V122 M352 122 H372" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M400 124 L410 80" stroke="#1E2B26" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M406 112 L420 104" stroke="#B5532F" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M60 132 V112 H96 V132 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M96 116 Q106 116 106 122 Q106 128 96 128" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M70 104 C66 98 74 96 70 90 M82 104 C78 98 86 96 82 90" fill="none" stroke="#B5532F" stroke-width="2" stroke-linecap="round"/>
</svg>`;

// 일정 장면: 나의 일정 맨 위. 달력 한 장, 핀, 벽시계, 화분
ART.scheduleScene = `<svg class="art-scene" viewBox="0 0 480 160" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="480" height="160" rx="20" fill="#E8F0EA"/>
    <path d="M20 132 H460" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="150" y="30" width="170" height="104" rx="6" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <rect x="150" y="30" width="170" height="24" rx="6" fill="#B5532F"/>
    <rect x="150" y="44" width="170" height="10" fill="#B5532F"/>
    <path d="M190 22 V38 M280 22 V38" stroke="#1E2B26" stroke-width="2.4" stroke-linecap="round"/>
    <rect x="168" y="66" width="14" height="10" fill="#D9E0DA"/><rect x="190" y="66" width="14" height="10" fill="#D9E0DA"/>
    <rect x="212" y="66" width="14" height="10" fill="#D9E0DA"/><rect x="234" y="66" width="14" height="10" fill="#D9E0DA"/>
    <rect x="256" y="66" width="14" height="10" fill="#D9E0DA"/><rect x="278" y="66" width="14" height="10" fill="#D9E0DA"/>
    <rect x="168" y="84" width="14" height="10" fill="#D9E0DA"/><rect x="190" y="84" width="14" height="10" fill="#B5532F"/>
    <rect x="212" y="84" width="14" height="10" fill="#D9E0DA"/><rect x="234" y="84" width="14" height="10" fill="#D9E0DA"/>
    <rect x="256" y="84" width="14" height="10" fill="#D9E0DA"/><rect x="278" y="84" width="14" height="10" fill="#D9E0DA"/>
    <rect x="168" y="102" width="14" height="10" fill="#D9E0DA"/><rect x="190" y="102" width="14" height="10" fill="#D9E0DA"/>
    <rect x="212" y="102" width="14" height="10" fill="#6F8F7E"/><rect x="234" y="102" width="14" height="10" fill="#D9E0DA"/>
    <circle cx="384" cy="62" r="26" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.5"/>
    <path d="M384 62 V48 M384 62 L394 68" stroke="#B5532F" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M56 132 V112 H92 V132 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M92 118 Q102 118 102 124 Q102 130 92 130" fill="none" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M430 132 V112 H460 V132 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M440 112 C436 104 444 102 440 94 M450 112 C446 104 454 102 450 94" fill="none" stroke="#6F8F7E" stroke-width="2" stroke-linecap="round"/>
</svg>`;

// 청구 장면: 나의 청부 맨 위. 영수증, 도장, 동전 더미, 펜
ART.billingScene = `<svg class="art-scene" viewBox="0 0 480 160" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="480" height="160" rx="20" fill="#E8F0EA"/>
    <path d="M20 132 H460" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M176 22 H290 V132 L282 124 L274 132 L266 124 L258 132 L250 124 L242 132 L234 124 L226 132 L218 124 L210 132 L202 124 L194 132 L186 124 L176 132 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M196 44 H270 M196 60 H270 M196 76 H254 M196 92 H270 M196 108 H240" stroke="#D9E0DA" stroke-width="3" stroke-linecap="round"/>
    <path d="M236 36 H270" stroke="#1E2B26" stroke-width="2" stroke-linecap="round"/>
    <rect x="236" y="96" width="30" height="30" rx="4" fill="none" stroke="#B5532F" stroke-width="2.4" transform="rotate(-6 251 111)"/>
    <path d="M244 111 L249 116 L258 104" fill="none" stroke="#B5532F" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" transform="rotate(-6 251 111)"/>
    <ellipse cx="346" cy="124" rx="34" ry="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <ellipse cx="346" cy="112" rx="34" ry="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <ellipse cx="346" cy="100" rx="34" ry="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <ellipse cx="346" cy="88" rx="34" ry="8" fill="#F2D7A8" stroke="#1E2B26" stroke-width="2.2"/>
    <path d="M400 132 L424 62" stroke="#1E2B26" stroke-width="2.6" stroke-linecap="round"/>
    <path d="M412 104 L430 96" stroke="#B5532F" stroke-width="2.6" stroke-linecap="round"/>
    <path d="M56 132 V122 H92 V132 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
</svg>`;

// 요약 칸 그림 (40px, 도장 테두리 + 사물 하나). 참고 구성: 요양사·이용자·금액·처리할 일
const METRIC_FRAME = (inner) => `<svg class="metric-art" viewBox="0 0 40 40" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="36" height="36" rx="9"/>${inner}</svg>`;
ART.metric = {
    bag: METRIC_FRAME('<rect x="11" y="15" width="18" height="14" rx="2"/><path d="M16 15 V12 Q16 10 18 10 H22 Q24 10 24 12 V15"/>'),
    plant: METRIC_FRAME('<path d="M14 26 H26 L24 33 H16 Z"/><path d="M20 26 V18 M20 18 C16 15 15 11 17 9 C19 11 20 14 20 18 Z M20 18 C24 15 25 11 23 9 C21 11 20 14 20 18 Z"/>'),
    wallet: METRIC_FRAME('<rect x="10" y="13" width="20" height="16" rx="3"/><path d="M10 18 H30 M26 23 H28"/>'),
    clipboard: METRIC_FRAME('<rect x="11" y="10" width="18" height="22" rx="2"/><path d="M16 8 H24 V12 H16 Z M15 19 L18 22 L24 16"/>'),
};

// 빈 상태 장면: 태블릿, 체크리스트, 달력, 화분 (사람 없음)
ART.tablet = `<svg class="art-scene" viewBox="0 0 320 180" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="320" height="180" rx="18" fill="#E8F0EA"/>
    <path d="M24 152 H296" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="112" y="38" width="96" height="116" rx="10" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/>
    <rect x="122" y="50" width="76" height="92" rx="3" fill="none" stroke="#D9E0DA" stroke-width="2"/>
    <path d="M132 70 L138 76 L150 64 M132 96 L138 102 L150 90 M132 122 L138 128 L150 116" fill="none" stroke="#B5532F" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M160 70 H184 M160 96 H184 M160 122 H178" stroke="#1E2B26" stroke-width="2.2" stroke-linecap="round"/>
    <rect x="206" y="44" width="80" height="66" rx="6" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2"/>
    <rect x="206" y="44" width="80" height="14" rx="6" fill="#B5532F"/>
    <rect x="206" y="52" width="80" height="6" fill="#B5532F"/>
    <rect x="216" y="66" width="10" height="8" fill="#D9E0DA"/><rect x="232" y="66" width="10" height="8" fill="#D9E0DA"/>
    <rect x="248" y="66" width="10" height="8" fill="#B5532F"/><rect x="264" y="66" width="10" height="8" fill="#D9E0DA"/>
    <rect x="216" y="82" width="10" height="8" fill="#D9E0DA"/><rect x="232" y="82" width="10" height="8" fill="#6F8F7E"/>
    <rect x="248" y="82" width="10" height="8" fill="#D9E0DA"/><rect x="264" y="82" width="10" height="8" fill="#D9E0DA"/>
    <circle cx="282" cy="124" r="16" fill="#FFFFFF" stroke="#B5532F" stroke-width="2.4"/>
    <path d="M274 124 L280 130 L291 118" fill="none" stroke="#B5532F" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M52 152 V128 H76 V152 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M64 128 C60 118 68 116 64 106 M74 128 C70 118 78 116 74 106" fill="none" stroke="#6F8F7E" stroke-width="2" stroke-linecap="round"/>
</svg>`;

// 평면 컬러 아이콘 (요약 칸용, 직접 그림): 색 타일 위에 사물 하나. 얼굴 없음.
const METRIC_FLAT = (tile, inner) => `<svg class="metric-art" viewBox="0 0 40 40" aria-hidden="true" focusable="false"><rect x="0" y="0" width="40" height="40" rx="10" fill="${tile}"/>${inner}</svg>`;
ART.metricFlat = {
    bag: METRIC_FLAT('#F6E4DC', '<path d="M15 16 V13 Q15 10 18 10 H22 Q25 10 25 13 V16" fill="none" stroke="#1E2B26" stroke-width="1.8"/><rect x="10" y="16" width="20" height="14" rx="3" fill="#B5532F"/><rect x="10" y="20" width="20" height="2" fill="#9A4425"/>'),
    plant: METRIC_FLAT('#E8F0EA', '<path d="M14 26 H26 L24 33 H16 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6" stroke-linejoin="round"/><path d="M20 26 V18" stroke="#1E2B26" stroke-width="1.6" stroke-linecap="round"/><path d="M20 18 C15 15 14 10 17 8 C19 11 20 14 20 18 Z" fill="#6F8F7E"/><path d="M20 18 C25 15 26 10 23 8 C21 11 20 14 20 18 Z" fill="#A9C2B3"/>'),
    wallet: METRIC_FLAT('#F2D7A8', '<rect x="9" y="12" width="22" height="17" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6"/><rect x="22" y="18" width="9" height="6" rx="2" fill="#B5532F"/><circle cx="25" cy="21" r="1.2" fill="#FFFFFF"/>'),
    clipboard: METRIC_FLAT('#E8F0EA', '<rect x="11" y="9" width="18" height="23" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6"/><rect x="16" y="7" width="8" height="4" rx="1.5" fill="#B5532F"/><path d="M15 19 L18 22 L24 16" fill="none" stroke="#B5532F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 27 H25" stroke="#D9E0DA" stroke-width="2" stroke-linecap="round"/>'),
};

// 평면 아이콘 세트 (직접 그림, 얼굴 없음). 같은 40px 타일 규칙.
const FLAT = (tile, inner) => `<svg class="flat-art" viewBox="0 0 40 40" aria-hidden="true" focusable="false"><rect x="0" y="0" width="40" height="40" rx="10" fill="${tile}"/>${inner}</svg>`;
ART.flat = {
    calendar: FLAT('#E8F0EA', '<rect x="9" y="11" width="22" height="20" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6"/><rect x="9" y="11" width="22" height="6" rx="3" fill="#B5532F"/><path d="M14 9 V13 M26 9 V13" stroke="#1E2B26" stroke-width="1.6" stroke-linecap="round"/><path d="M15 23 L18 26 L25 19" fill="none" stroke="#6F8F7E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'),
    clock: FLAT('#F6E4DC', '<circle cx="20" cy="20" r="10" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6"/><path d="M20 14 V20 L24 23" fill="none" stroke="#B5532F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'),
    doc: FLAT('#F6E4DC', '<path d="M13 9 H24 L28 13 V31 H13 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6" stroke-linejoin="round"/><path d="M24 9 V13 H28" fill="none" stroke="#1E2B26" stroke-width="1.6" stroke-linejoin="round"/><path d="M17 19 H24 M17 23 H24 M17 27 H21" stroke="#B5532F" stroke-width="2" stroke-linecap="round"/>'),
    group: FLAT('#E8F0EA', '<circle cx="15" cy="16" r="4" fill="#6F8F7E"/><path d="M8 29 Q8 22 15 22 Q22 22 22 29 Z" fill="#6F8F7E"/><circle cx="25" cy="18" r="4" fill="#B5532F"/><path d="M18 30 Q18 23 25 23 Q32 23 32 30 Z" fill="#B5532F"/>'),
    checklist: FLAT('#F6E4DC', '<rect x="11" y="9" width="18" height="23" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.6"/><rect x="16" y="7" width="8" height="4" rx="1.5" fill="#B5532F"/><path d="M14 19 L16 21 L20 17 M14 26 L16 28 L20 24" fill="none" stroke="#B5532F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M23 19 H27 M23 26 H27" stroke="#D9E0DA" stroke-width="2" stroke-linecap="round"/>'),
};
// 평면 빈 상태 장면: 태블릿과 체크 (얼굴 없음)
ART.tabletFlat = `<svg class="art-scene" viewBox="0 0 320 180" aria-hidden="true" focusable="false">
    <rect x="0" y="0" width="320" height="180" rx="18" fill="#E8F0EA"/>
    <path d="M24 152 H296" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="118" y="30" width="84" height="122" rx="12" fill="#1E2B26"/>
    <rect x="126" y="40" width="68" height="100" rx="5" fill="#FFFFFF"/>
    <circle cx="160" cy="146" r="3" fill="#6F8F7E"/>
    <path d="M136 62 L142 68 L154 56" fill="none" stroke="#B5532F" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M136 84 L142 90 L154 78" fill="none" stroke="#B5532F" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M136 106 L142 112 L154 100" fill="none" stroke="#B5532F" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M162 62 H184 M162 84 H184 M162 106 H178" stroke="#D9E0DA" stroke-width="3" stroke-linecap="round"/>
    <circle cx="246" cy="98" r="22" fill="#FFFFFF" stroke="#B5532F" stroke-width="3"/>
    <path d="M237 98 L243 104 L256 90" fill="none" stroke="#B5532F" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M50 152 V124 H82 V152 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M66 124 C60 110 70 106 66 92 C74 102 76 112 66 124 Z" fill="#6F8F7E"/>
</svg>`;

// 그림 아이콘 세트 (직접 그림, 얼굴 없음): 색 타일 위에 명암 두 단계, 얇은 테두리, 빛 표시, 아래 그림자
const ILLUS = (tile, shadow, inner) => `<svg class="illus-art" viewBox="0 0 40 40" aria-hidden="true" focusable="false"><rect x="0" y="0" width="40" height="40" rx="11" fill="${tile}"/><ellipse cx="20" cy="34" rx="11" ry="2" fill="${shadow}" opacity="0.5"/>${inner}</svg>`;
ART.illus = {
    calendar: ILLUS('#E8F0EA', '#55645D', '<rect x="8" y="10" width="24" height="22" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><path d="M8 17 H32 V14 A4 4 0 0 0 28 10 H12 A4 4 0 0 0 8 14 Z" fill="#B5532F"/><path d="M8 17 H32 V20 H8 Z" fill="#9A4425" opacity="0.35"/><rect x="13" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><rect x="24" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><path d="M14 25 L18 29 L26 21" fill="none" stroke="#6F8F7E" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M11 13 Q12 12 13 13" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round"/>'),
    clock: ILLUS('#F6E4DC', '#9A4425', '<circle cx="20" cy="19" r="11" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><circle cx="20" cy="19" r="9" fill="#F6E4DC" opacity="0.6"/><path d="M20 13 V19.5 L24.5 22.5" fill="none" stroke="#B5532F" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="20" cy="19.5" r="1.4" fill="#1E2B26"/><path d="M14.5 13 Q16 11 18 10.5" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round"/>'),
    doc: ILLUS('#F6E4DC', '#9A4425', '<path d="M11 8 H23 L29 14 V31 H11 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><path d="M23 8 V14 H29 Z" fill="#E8D9CF" stroke="#1E2B26" stroke-width="1.2" stroke-linejoin="round"/><rect x="14" y="19" width="12" height="2.2" rx="1.1" fill="#B5532F"/><rect x="14" y="23.5" width="12" height="2.2" rx="1.1" fill="#B5532F" opacity="0.7"/><rect x="14" y="28" width="7" height="2.2" rx="1.1" fill="#B5532F" opacity="0.5"/>'),
    group: ILLUS('#E8F0EA', '#55645D', '<circle cx="15" cy="15" r="4.5" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1.2"/><path d="M7 30 Q7 21 15 21 Q23 21 23 30 Z" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1.2" stroke-linejoin="round"/><circle cx="26" cy="17" r="4" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2"/><path d="M18 31 Q18 23 26 23 Q33 23 33 31 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2" stroke-linejoin="round"/><path d="M11 25 Q12 24 13 24.5" stroke="#FFFFFF" stroke-width="1.1" stroke-linecap="round"/>'),
    checklist: ILLUS('#F6E4DC', '#9A4425', '<rect x="10" y="8" width="20" height="25" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="15" y="5.5" width="10" height="5" rx="2" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2"/><circle cx="15" cy="17" r="2.2" fill="#B5532F"/><path d="M14.2 17 L14.8 17.7 L16 16.3" fill="none" stroke="#FFFFFF" stroke-width="0.9" stroke-linecap="round"/><circle cx="15" cy="24" r="2.2" fill="#6F8F7E"/><path d="M14.2 24 L14.8 24.7 L16 23.3" fill="none" stroke="#FFFFFF" stroke-width="0.9" stroke-linecap="round"/><rect x="20" y="15.5" width="6" height="2.2" rx="1.1" fill="#D9E0DA"/><rect x="20" y="22.5" width="6" height="2.2" rx="1.1" fill="#D9E0DA"/>'),
    wallet: ILLUS('#F2D7A8', '#9A4425', '<path d="M9 14 H28 V28 H9 Z" fill="#8A4A2B" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 14 L14 10 H28 V14" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2" stroke-linejoin="round"/><rect x="22" y="18" width="10" height="7" rx="2" fill="#B5532F" stroke="#1E2B26" stroke-width="1.2"/><circle cx="26.5" cy="21.5" r="1.2" fill="#F2D7A8"/><circle cx="29" cy="25" r="5" fill="#E8B04A" stroke="#1E2B26" stroke-width="1.1"/><text x="29" y="27.2" text-anchor="middle" font-size="6.5" font-weight="700" fill="#1E2B26" font-family="sans-serif">₩</text><path d="M11.5 16 H16" stroke="#FFFFFF" stroke-width="1.1" stroke-linecap="round" opacity="0.7"/>'),
};

// 집 아이콘 (이용자 칸): 지붕, 창문 불빛, 문
ART.illus.house = ILLUS('#E8F0EA', '#55645D', '<path d="M8 20 L20 9 L32 20 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><path d="M11 19 V31 H29 V19 L20 12 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.3" stroke-linejoin="round"/><rect x="11" y="23" width="6" height="5" rx="1" fill="#F2D7A8" stroke="#1E2B26" stroke-width="1"/><rect x="23" y="23" width="6" height="5" rx="1" fill="#F2D7A8" stroke="#1E2B26" stroke-width="1"/><rect x="17.5" y="24" width="5" height="7" rx="1" fill="#6F8F7E" stroke="#1E2B26" stroke-width="1"/><path d="M13 14 Q14 13 15 14" stroke="#FFFFFF" stroke-width="1.1" stroke-linecap="round"/>');

// 요양사 화면 제목 옆 그림: 직접 그림 (얼굴 없음). 페이지에서 <span class="sec-ico" data-ico="이름"></span>로 쓴다
ART.draw = {
    payslip: ILLUS('#E8F0EA', '#55645D', '<rect x="10" y="7" width="20" height="26" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="14" y="12" width="12" height="2.2" rx="1.1" fill="#B5532F"/><rect x="14" y="17" width="8" height="2" rx="1" fill="#6F8F7E"/><circle cx="24" cy="25" r="4.5" fill="#E8B04A" stroke="#1E2B26" stroke-width="1.1"/><text x="24" y="27" text-anchor="middle" font-size="6" font-weight="700" fill="#1E2B26" font-family="sans-serif">₩</text>'),
    calculator: ILLUS('#F6E4DC', '#9A4425', '<rect x="10" y="7" width="20" height="26" rx="3.5" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="13" y="10" width="14" height="6" rx="1.2" fill="#6F8F7E"/><circle cx="15.5" cy="21" r="1.6" fill="#B5532F"/><circle cx="20" cy="21" r="1.6" fill="#B5532F"/><circle cx="24.5" cy="21" r="1.6" fill="#B5532F"/><circle cx="15.5" cy="26" r="1.6" fill="#1E2B26"/><circle cx="20" cy="26" r="1.6" fill="#1E2B26"/><rect x="22.5" y="24.5" width="4" height="6" rx="1" fill="#B5532F"/>'),
    seal: ILLUS('#F6E4DC', '#9A4425', '<path d="M11 8 H23 L29 14 V31 H11 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><rect x="14" y="18" width="11" height="2.2" rx="1.1" fill="#6F8F7E"/><rect x="14" y="23" width="8" height="2.2" rx="1.1" fill="#6F8F7E" opacity="0.7"/><circle cx="25" cy="27" r="5" fill="#A8432A" stroke="#1E2B26" stroke-width="1"/><path d="M22.8 27 L24.3 28.5 L27.4 25.5" fill="none" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'),
    coins: ILLUS('#F2D7A8', '#9A4425', '<ellipse cx="20" cy="27" rx="9" ry="3.2" fill="#E8B04A" stroke="#1E2B26" stroke-width="1.1"/><path d="M11 24 V27 Q11 30.2 20 30.2 Q29 30.2 29 27 V24 Q29 27.2 20 27.2 Q11 27.2 11 24 Z" fill="#C98F2E"/><ellipse cx="20" cy="21" rx="9" ry="3.2" fill="#E8B04A" stroke="#1E2B26" stroke-width="1.1"/><ellipse cx="20" cy="15" rx="9" ry="3.2" fill="#F2C65C" stroke="#1E2B26" stroke-width="1.1"/><path d="M16.5 14.5 Q17.5 13.5 19 13.5" stroke="#FFFFFF" stroke-width="1" stroke-linecap="round"/>'),
    receipt: ILLUS('#E8F0EA', '#55645D', '<path d="M12 7 H28 V33 L25 31 L22 33 L20 31 L18 33 L15 31 L12 33 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4" stroke-linejoin="round"/><rect x="15" y="12" width="10" height="2.2" rx="1.1" fill="#B5532F"/><rect x="15" y="17" width="10" height="2.2" rx="1.1" fill="#6F8F7E"/><rect x="15" y="22" width="6" height="2.2" rx="1.1" fill="#6F8F7E" opacity="0.7"/>'),
    calendarDay: ILLUS('#E8F0EA', '#55645D', '<rect x="8" y="10" width="24" height="22" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><path d="M8 17 H32 V14 A4 4 0 0 0 28 10 H12 A4 4 0 0 0 8 14 Z" fill="#B5532F"/><rect x="13" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><rect x="24" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><circle cx="20" cy="25" r="3.6" fill="#6F8F7E"/><circle cx="20" cy="25" r="1.4" fill="#FFFFFF"/>'),
    calendarGrid: ILLUS('#E8F0EA', '#55645D', '<rect x="8" y="10" width="24" height="22" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><path d="M8 17 H32 V14 A4 4 0 0 0 28 10 H12 A4 4 0 0 0 8 14 Z" fill="#6F8F7E"/><rect x="13" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><rect x="24" y="7" width="2.6" height="6" rx="1.3" fill="#1E2B26"/><rect x="12" y="21" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="18" y="21" width="4" height="3" rx="0.8" fill="#B5532F"/><rect x="24" y="21" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="12" y="26" width="4" height="3" rx="0.8" fill="#D9E0DA"/><rect x="18" y="26" width="4" height="3" rx="0.8" fill="#D9E0DA"/>'),
    mic: ILLUS('#F6E4DC', '#9A4425', '<rect x="16" y="6" width="8" height="16" rx="4" fill="#B5532F" stroke="#1E2B26" stroke-width="1.3"/><path d="M11 18 Q11 26 20 26 Q29 26 29 18" fill="none" stroke="#1E2B26" stroke-width="1.6" stroke-linecap="round"/><path d="M20 26 V31" stroke="#1E2B26" stroke-width="1.6" stroke-linecap="round"/><path d="M15 32 H25" stroke="#1E2B26" stroke-width="1.6" stroke-linecap="round"/><path d="M18 10 V14" stroke="#FFFFFF" stroke-width="1" stroke-linecap="round" opacity="0.8"/>'),
    chart: ILLUS('#E8F0EA', '#55645D', '<rect x="8" y="8" width="24" height="24" rx="4" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="12" y="20" width="3.5" height="8" rx="1" fill="#6F8F7E"/><rect x="18" y="15" width="3.5" height="13" rx="1" fill="#B5532F"/><rect x="24" y="11" width="3.5" height="17" rx="1" fill="#6F8F7E"/>'),
    ledger: ILLUS('#F2D7A8', '#9A4425', '<rect x="11" y="7" width="18" height="26" rx="2.5" fill="#8A4A2B" stroke="#1E2B26" stroke-width="1.3"/><rect x="14" y="7" width="15" height="25" rx="1.5" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1"/><rect x="17" y="12" width="8" height="2" rx="1" fill="#B5532F"/><rect x="17" y="17" width="8" height="2" rx="1" fill="#6F8F7E"/><rect x="17" y="22" width="8" height="2" rx="1" fill="#6F8F7E" opacity="0.7"/><rect x="17" y="27" width="5" height="2" rx="1" fill="#6F8F7E" opacity="0.5"/>'),
};

// data-ico 속성이 있는 자리에 그림을 채운다
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-ico]').forEach(el => { el.innerHTML = ART.draw[el.dataset.ico] || ''; });
});

// 페이지 장면 (직접 그림, 얼굴 없음): 화면 맨 위 상단 제목 아래에 넣는다
const SCENE = (inner) => `<svg class="art-scene" viewBox="0 0 480 180" aria-hidden="true" focusable="false"><rect x="0" y="0" width="480" height="180" rx="20" fill="#E8F0EA"/><path d="M16 150 H464" stroke="#6F8F7E" stroke-width="2.5" stroke-linecap="round"/>${inner}</svg>`;
const COINS = (x, y) => `<ellipse cx="${x}" cy="${y + 12}" rx="30" ry="7" fill="#E8B04A" stroke="#1E2B26" stroke-width="2"/><ellipse cx="${x}" cy="${y}" rx="30" ry="7" fill="#E8B04A" stroke="#1E2B26" stroke-width="2"/><ellipse cx="${x}" cy="${y - 12}" rx="30" ry="7" fill="#F2C65C" stroke="#1E2B26" stroke-width="2"/>`;
const CALENDAR = (x, y) => `<rect x="${x}" y="${y}" width="160" height="108" rx="12" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><path d="M${x} ${y + 24} H${x + 160} V${y + 12} A12 12 0 0 0 ${x + 148} ${y} H${x + 12} A12 12 0 0 0 ${x} ${y + 12} Z" fill="#B5532F"/><rect x="${x + 44}" y="${y - 12}" width="6" height="22" rx="3" fill="#1E2B26"/><rect x="${x + 106}" y="${y - 12}" width="6" height="22" rx="3" fill="#1E2B26"/><rect x="${x + 16}" y="${y + 42}" width="20" height="14" rx="3" fill="#D9E0DA"/><rect x="${x + 44}" y="${y + 42}" width="20" height="14" rx="3" fill="#B5532F"/><rect x="${x + 72}" y="${y + 42}" width="20" height="14" rx="3" fill="#D9E0DA"/><rect x="${x + 100}" y="${y + 42}" width="20" height="14" rx="3" fill="#D9E0DA"/><rect x="${x + 16}" y="${y + 66}" width="20" height="14" rx="3" fill="#D9E0DA"/><rect x="${x + 44}" y="${y + 66}" width="20" height="14" rx="3" fill="#6F8F7E"/>`;
const LEDGER = (x, y) => `<rect x="${x}" y="${y}" width="92" height="110" rx="6" fill="#8A4A2B" stroke="#1E2B26" stroke-width="2.2"/><rect x="${x + 6}" y="${y + 4}" width="84" height="102" rx="3" fill="#FFFFFF" stroke="#1E2B26" stroke-width="1.4"/><rect x="${x + 16}" y="${y + 22}" width="60" height="7" rx="3.5" fill="#B5532F"/><rect x="${x + 16}" y="${y + 40}" width="60" height="6" rx="3" fill="#6F8F7E"/><rect x="${x + 16}" y="${y + 56}" width="46" height="6" rx="3" fill="#D9E0DA"/><rect x="${x + 16}" y="${y + 72}" width="54" height="6" rx="3" fill="#D9E0DA"/>`;
const SEAL = (x, y) => `<circle cx="${x}" cy="${y}" r="20" fill="#A8432A" stroke="#1E2B26" stroke-width="2"/><path d="M${x - 8} ${y} L${x - 2} ${y + 6} L${x + 10} ${y - 6}" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;

ART.pageScene = {
    salary: SCENE('<rect x="120" y="30" width="110" height="120" rx="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="138" y="52" width="74" height="8" rx="4" fill="#B5532F"/><rect x="138" y="72" width="60" height="6" rx="3" fill="#6F8F7E"/><rect x="138" y="88" width="70" height="6" rx="3" fill="#D9E0DA"/><rect x="138" y="102" width="50" height="6" rx="3" fill="#D9E0DA"/><circle cx="196" cy="128" r="14" fill="#E8B04A" stroke="#1E2B26" stroke-width="2"/><text x="196" y="133" text-anchor="middle" font-size="16" font-weight="700" fill="#1E2B26" font-family="sans-serif">₩</text><rect x="270" y="40" width="80" height="104" rx="10" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="284" y="54" width="52" height="20" rx="4" fill="#6F8F7E"/><circle cx="292" cy="92" r="5" fill="#B5532F"/><circle cx="310" cy="92" r="5" fill="#B5532F"/><circle cx="328" cy="92" r="5" fill="#B5532F"/><circle cx="292" cy="112" r="5" fill="#1E2B26"/><circle cx="310" cy="112" r="5" fill="#1E2B26"/><rect x="320" y="104" width="16" height="30" rx="4" fill="#B5532F"/>' + COINS(400, 140)),
    notify: SCENE('<path d="M150 118 V86 A44 44 0 0 1 238 86 V118 L252 134 H136 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4" stroke-linejoin="round"/><path d="M182 146 H206" stroke="#1E2B26" stroke-width="2.6" stroke-linecap="round"/><circle cx="240" cy="56" r="9" fill="#B5532F"/><rect x="290" y="70" width="110" height="72" rx="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><path d="M290 78 L345 116 L400 78" fill="none" stroke="#1E2B26" stroke-width="2.4" stroke-linejoin="round"/><circle cx="400" cy="70" r="10" fill="#B5532F"/>'),
    residents: SCENE('<path d="M120 92 L180 40 L240 92 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="2.4" stroke-linejoin="round"/><path d="M134 90 V142 H226 V90 L180 52 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4" stroke-linejoin="round"/><rect x="168" y="106" width="24" height="36" rx="3" fill="#6F8F7E" stroke="#1E2B26" stroke-width="2"/><rect x="144" y="106" width="16" height="14" rx="2" fill="#F2D7A8" stroke="#1E2B26" stroke-width="1.6"/><path d="M180 66 Q176 62 172 66 Q176 72 180 76 Q184 72 188 66 Q184 62 180 66 Z" fill="#E07A5F"/><rect x="286" y="50" width="110" height="100" rx="10" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="326" y="40" width="30" height="16" rx="5" fill="#B5532F" stroke="#1E2B26" stroke-width="2"/><path d="M300 84 L306 90 L318 78" fill="none" stroke="#6F8F7E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><rect x="326" y="82" width="54" height="6" rx="3" fill="#D9E0DA"/><path d="M300 112 L306 118 L318 106" fill="none" stroke="#6F8F7E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><rect x="326" y="110" width="44" height="6" rx="3" fill="#D9E0DA"/><rect x="414" y="122" width="28" height="22" rx="4" fill="#B5532F" stroke="#1E2B26" stroke-width="2"/><path d="M428 122 V100 M428 110 Q416 100 412 102 M428 104 Q440 94 444 96" fill="none" stroke="#6F8F7E" stroke-width="3" stroke-linecap="round"/>'),
    billing: SCENE('<rect x="130" y="34" width="120" height="104" rx="8" fill="#F2D7A8" stroke="#1E2B26" stroke-width="2.2"/><rect x="150" y="48" width="120" height="104" rx="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="168" y="70" width="84" height="8" rx="4" fill="#B5532F"/><rect x="168" y="90" width="70" height="7" rx="3.5" fill="#6F8F7E"/><rect x="168" y="108" width="80" height="7" rx="3.5" fill="#D9E0DA"/><rect x="168" y="122" width="56" height="7" rx="3.5" fill="#D9E0DA"/><circle cx="300" cy="104" r="26" fill="#A8432A" stroke="#1E2B26" stroke-width="2"/><circle cx="300" cy="104" r="19" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-dasharray="3 3"/><path d="M292 104 L298 110 L310 98" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>' + COINS(400, 128)),
    approval: SCENE(CALENDAR(120, 50) + '<circle cx="354" cy="104" r="34" fill="#6F8F7E" stroke="#1E2B26" stroke-width="2.4"/><path d="M338 104 L350 116 L372 92" fill="none" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'),
    staff: SCENE('<path d="M164 38 L180 28 L196 38" fill="none" stroke="#1E2B26" stroke-width="2"/><rect x="132" y="50" width="96" height="118" rx="10" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><circle cx="180" cy="100" r="16" fill="#F6E4DC" stroke="#1E2B26" stroke-width="1.6"/><path d="M160 144 Q160 124 180 124 Q200 124 200 144 Z" fill="#B5532F"/><rect x="236" y="50" width="150" height="104" rx="10" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="252" y="66" width="60" height="7" rx="3.5" fill="#B5532F"/><rect x="252" y="86" width="110" height="6" rx="3" fill="#D9E0DA"/><rect x="252" y="102" width="110" height="6" rx="3" fill="#D9E0DA"/><rect x="252" y="118" width="80" height="6" rx="3" fill="#D9E0DA"/><circle cx="372" cy="122" r="8" fill="#6F8F7E"/><rect x="400" y="80" width="46" height="64" rx="7" fill="#1E2B26"/><rect x="405" y="88" width="36" height="46" rx="3" fill="#FFFFFF"/><path d="M412 110 L418 116 L430 102" fill="none" stroke="#6F8F7E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'),
    settlement: SCENE(CALENDAR(120, 50).replace('#B5532F"/><rect x="164"', '#6F8F7E"/><rect x="164"') + LEDGER(310, 44) + COINS(432, 128)),
    profit: SCENE('<rect x="120" y="40" width="240" height="106" rx="12" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="146" y="98" width="28" height="36" rx="4" fill="#6F8F7E"/><rect x="190" y="82" width="28" height="52" rx="4" fill="#6F8F7E"/><rect x="234" y="66" width="28" height="68" rx="4" fill="#B5532F"/><rect x="278" y="54" width="28" height="80" rx="4" fill="#6F8F7E"/><path d="M146 100 L190 84 L234 68 L278 56" fill="none" stroke="#1E2B26" stroke-width="2" stroke-dasharray="4 4" stroke-linecap="round"/>' + COINS(400, 128)),
    guardian: SCENE('<path d="M240 34 L300 54 V100 Q300 140 240 162 Q180 140 180 100 V54 Z" fill="#6F8F7E" stroke="#1E2B26" stroke-width="2.4" stroke-linejoin="round"/><path d="M216 100 L240 78 L264 100 V122 H216 Z" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2"/><rect x="234" y="106" width="12" height="16" rx="2" fill="#B5532F"/><path d="M120 80 Q120 64 134 64 Q142 64 146 72 Q150 64 158 64 Q172 64 172 80 Q172 100 146 116 Q120 100 120 80 Z" fill="#B5532F" stroke="#1E2B26" stroke-width="2"/><circle cx="356" cy="92" r="14" fill="none" stroke="#1E2B26" stroke-width="5"/><path d="M368 92 H414 M400 92 V106 M410 92 V104" stroke="#1E2B26" stroke-width="5" stroke-linecap="round"/><circle cx="356" cy="92" r="4" fill="#E8B04A"/>'),
    statement: SCENE('<rect x="150" y="34" width="130" height="116" rx="8" fill="#FFFFFF" stroke="#1E2B26" stroke-width="2.4"/><rect x="170" y="56" width="90" height="8" rx="4" fill="#B5532F"/><rect x="170" y="76" width="70" height="7" rx="3.5" fill="#6F8F7E"/><rect x="170" y="94" width="86" height="7" rx="3.5" fill="#D9E0DA"/><rect x="170" y="110" width="60" height="7" rx="3.5" fill="#D9E0DA"/>' + SEAL(250, 130) + '<path d="M330 150 L300 120 L372 48 L400 76 Z" fill="#E8B04A" stroke="#1E2B26" stroke-width="2.2" stroke-linejoin="round"/><path d="M300 120 L290 146 L316 134 Z" fill="#F6E4DC" stroke="#1E2B26" stroke-width="2" stroke-linejoin="round"/>'),
};

// 페이지 장면을 상단(제목 아래)에 넣는다. 사이드바 레이아웃과 메인 레이아웃 둘 다 처리한다
ART.placeScene = (name) => {
    const wrap = document.createElement('div');
    wrap.className = 'page-scene';
    wrap.innerHTML = ART.pageScene[name];
    const layout = document.querySelector('.main-layout');
    if (layout) {
        layout.children[0].after(wrap);
    } else {
        document.querySelector('main > div:nth-child(2)').prepend(wrap);
    }
};
