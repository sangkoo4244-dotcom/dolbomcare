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
