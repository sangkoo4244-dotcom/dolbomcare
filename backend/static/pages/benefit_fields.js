/* 방문 급여 종류(방문요양·방문목욕·방문간호) 입력칸 - 방문 기록, 계획 제안, 반복 일정 화면이 같이 쓴다.
   센터가 방문목욕·방문간호를 제공 급여로 고르지 않았으면 아무것도 그리지 않는다(방문요양만 쓰는 센터는 화면이 그대로다).
   수가표는 서버(/api/v1/benefits)가 내려준 것을 쓰고, 화면에 숫자를 따로 복사해 두지 않는다. */
const BenefitFields = (() => {
    const API = '/api/v1';
    const LABELS = { home_care: '방문요양', home_bath: '방문목욕', home_nursing: '방문간호' };
    const BATH_LABELS = { vehicle_in: '차량 내 목욕', vehicle_home: '가정 내 목욕 (방문목욕차량 이용)', no_vehicle: '방문목욕차량 미이용' };
    const DURATIONS = { home_care: [30, 60, 90, 120, 180, 240], home_bath: [30, 60, 90, 120, 180, 240], home_nursing: [15, 30, 45, 60, 90, 120, 180, 240] };
    const DEFAULT_DURATION = { home_care: 60, home_bath: 60, home_nursing: 30 };
    let info = null, staff = [], loadPromise = null;

    function load(centerId) {
        if (!loadPromise) {
            loadPromise = (async () => {
                try { const r = await fetch(`${API}/benefits`); if (r.ok) info = await r.json(); } catch (e) { /* 못 받으면 방문요양만 쓴다 */ }
                if (usable().length > 1 && centerId) {
                    try { const r = await fetch(`${API}/users/?role=caregiver&center_id=${centerId}`); if (r.ok) staff = (await r.json()).users || []; } catch (e) { /* 동행자 목록 없음 */ }
                }
            })();
        }
        return loadPromise;
    }

    // 이 센터가 고르고 기능도 만들어진 방문 급여. 방문요양은 항상 쓸 수 있다.
    function usable() {
        const on = new Set((info && info.enabled) || []);
        const ready = new Set(((info && info.programs) || []).flatMap(p => p.benefits).filter(b => b.implemented).map(b => b.code));
        return ['home_care', 'home_bath', 'home_nursing'].filter(c => c === 'home_care' || (on.has(c) && ready.has(c)));
    }

    function label(code) { return LABELS[code] || LABELS.home_care; }

    // 직종에 맞는 급여만 고르게 한다: 방문간호는 간호직만, 방문목욕은 요양보호사만(서버도 같은 규칙으로 막는다)
    const NURSING_JOBS = ['간호사', '간호조무사', '치과위생사'];
    function allowedFor(userId) {
        const all = usable();
        const me = staff.find(u => u.id === Number(userId));
        if (!me) return all;
        const nurse = NURSING_JOBS.includes(me.job_type);
        return all.filter(c => (c !== 'home_nursing' || nurse) && (c !== 'home_bath' || !nurse));
    }

    function ensureStyle() {
        if (document.getElementById('bf-style')) return;
        const st = document.createElement('style');
        st.id = 'bf-style';
        st.textContent = '.bf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;}'
            + '.bf-grid label{display:flex;flex-direction:column;gap:4px;font-size:13px;font-weight:700;color:#374151;}'
            + '.bf-grid select,.bf-grid input{padding:8px 10px;border:2px solid #E5E7EB;border-radius:8px;font:inherit;font-weight:400;background:#fff;}'
            + '.bf-note{grid-column:1/-1;}';
        document.head.appendChild(st);
    }

    // 급여 종류에 맞게 제공 시간 선택지를 바꾼다(방문간호는 15분부터). 고른 값이 남아 있으면 유지한다.
    function applyDurations(selectEl, benefit) {
        if (!selectEl) return;
        const options = DURATIONS[benefit] || DURATIONS.home_care;
        const keep = Number(selectEl.value);
        selectEl.innerHTML = options.map(m => `<option value="${m}">${m}분</option>`).join('');
        selectEl.value = String(options.includes(keep) ? keep : DEFAULT_DURATION[benefit] || 60);
    }

    // 미리보기용 급여비용 총액(공단 수가표). 값을 알 수 없으면 null.
    function fee(benefit, minutes, mode) {
        const t = info && info.visit_fees;
        if (!t) return null;
        if (benefit === 'home_bath') { const row = t.home_bath.find(r => r.mode === mode); return row ? row.fee : null; }
        if (benefit === 'home_nursing') { const row = t.home_nursing.find(r => minutes >= r.min && (r.max === null || minutes < r.max)); return row ? row.fee : null; }
        const rows = t.home_care.filter(r => minutes >= r.min);
        return rows.length ? rows[rows.length - 1].fee : null;
    }

    /* el에 입력칸을 그린다. opts: { selfId(기록·계획의 주 요양보호사), withNote(방문간호지시서 메모), locked(급여 종류 고정), durationEl, onChange(benefit) }
       반환: { benefit(), value(), set(v), setSelf(id) } */
    function mount(el, opts = {}) {
        const codes = usable();
        const empty = { benefit: () => 'home_care', value: () => ({ benefit_type: null, bath_mode: null, co_caregiver_id: null, nursing_order_note: null }), set() {}, setSelf() {} };
        if (!el) return empty;
        if (codes.length < 2) { el.innerHTML = ''; el.style.display = 'none'; return empty; }
        ensureStyle();
        el.style.display = '';
        el.innerHTML = `<div class="bf-grid">
            <label>급여 종류<select data-bf="benefit"></select></label>
            <label data-bf-show="home_bath">목욕 방식<select data-bf="mode"><option value="">방식을 고르세요</option>${Object.entries(BATH_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
            <label data-bf-show="home_bath">함께 가는 요양보호사 (2인 이상 제공)<select data-bf="co"></select></label>
            ${opts.withNote ? '<label data-bf-show="home_nursing" class="bf-note">방문간호지시서 확인 메모<input data-bf="note" maxlength="200" placeholder="예: 지시서 발급일·번호"></label>' : ''}
        </div>`;
        const q = (k) => el.querySelector(`[data-bf="${k}"]`);
        let selfId = opts.selfId || null;

        function renderBenefits() {
            const sel = q('benefit'), keep = sel.value;
            const allowed = opts.locked ? [opts.locked] : allowedFor(selfId);
            sel.innerHTML = allowed.map(c => `<option value="${c}">${label(c)}</option>`).join('');
            if (allowed.includes(keep)) sel.value = keep;
        }

        function renderCo(keep) {
            const sel = q('co');
            sel.innerHTML = '<option value="">요양보호사를 고르세요</option>'
                + staff.filter(u => u.id !== selfId && !NURSING_JOBS.includes(u.job_type)).map(u => `<option value="${u.id}">${u.full_name}</option>`).join('');
            if (keep && [...sel.options].some(o => o.value === String(keep))) sel.value = String(keep);
        }
        function refresh() {
            const b = q('benefit').value;
            el.querySelectorAll('[data-bf-show]').forEach(row => { row.style.display = row.dataset.bfShow === b ? '' : 'none'; });
            if (opts.durationEl) applyDurations(opts.durationEl, b);
            if (opts.onChange) opts.onChange(b);
        }
        renderBenefits();
        q('benefit').addEventListener('change', refresh);
        ['mode', 'co', 'note'].forEach(k => { const x = q(k); if (x) x.addEventListener('change', () => opts.onChange && opts.onChange(q('benefit').value)); });
        renderCo();
        refresh();
        if (opts.locked) { q('benefit').value = opts.locked; q('benefit').disabled = true; refresh(); }

        return {
            benefit: () => q('benefit').value,
            value() {
                const b = q('benefit').value;
                const note = q('note');
                return {
                    benefit_type: b === 'home_care' ? null : b,
                    bath_mode: b === 'home_bath' && q('mode').value ? q('mode').value : null,
                    co_caregiver_id: b === 'home_bath' && q('co').value ? Number(q('co').value) : null,
                    nursing_order_note: b === 'home_nursing' && note && note.value.trim() ? note.value.trim() : null,
                };
            },
            set(v) {
                v = v || {};
                if (v.benefit_type && [...q('benefit').options].some(o => o.value === v.benefit_type)) q('benefit').value = v.benefit_type;
                refresh();
                if (v.bath_mode) q('mode').value = v.bath_mode;
                renderCo(v.co_caregiver_id);
                const note = q('note');
                if (note) note.value = v.nursing_order_note || '';
            },
            setSelf(id) { selfId = id ? Number(id) : null; renderBenefits(); renderCo(q('co').value); refresh(); },
        };
    }

    return { load, usable, label, mount, fee, applyDurations, BATH_LABELS };
})();
