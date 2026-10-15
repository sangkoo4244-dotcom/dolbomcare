/* 방문 급여 종류(방문요양·방문목욕·방문간호)와 함께 가는 요양보호사 입력칸 - 방문 기록, 계획 제안, 반복 일정 화면이 같이 쓴다.
   - 계획 화면(withNote 없음): 센터가 방문목욕·방문간호를 제공 급여로 고르지 않았으면 아무것도 그리지 않는다.
   - 기록 화면(withNote): 방문요양만 쓰는 센터에도 "2인 동시 제공"(고시 제19조 ⑦) 체크 한 줄이 나온다.
   수가표와 시간별 감액 규칙은 서버(/api/v1/benefits)가 내려준 것을 쓰고, 화면에 숫자를 따로 복사해 두지 않는다. */
const BenefitFields = (() => {
    const API = '/api/v1';
    const LABELS = { home_care: '방문요양', home_bath: '방문목욕', home_nursing: '방문간호' };
    const BATH_LABELS = { vehicle_in: '차량 내 목욕', vehicle_home: '가정 내 목욕 (방문목욕차량 이용)', no_vehicle: '방문목욕차량 미이용' };
    const DURATIONS = { home_care: [30, 60, 90, 120, 180, 240], home_bath: [30, 60, 90, 120, 180, 240], home_nursing: [15, 30, 45, 60, 90, 120, 180, 240] };
    const DEFAULT_DURATION = { home_care: 60, home_bath: 60, home_nursing: 30 };
    const NURSING_JOBS = ['간호사', '간호조무사', '치과위생사'];
    let info = null, staff = [], loadPromise = null;

    function load(centerId) {
        if (!loadPromise) {
            loadPromise = (async () => {
                try { const r = await fetch(`${API}/benefits`); if (r.ok) info = await r.json(); } catch (e) { /* 못 받으면 방문요양만 쓴다 */ }
                if (centerId) {
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
            + '.bf-grid select,.bf-grid input[type=text],.bf-grid textarea{padding:8px 10px;border:2px solid #E5E7EB;border-radius:8px;font:inherit;font-weight:400;background:#fff;}'
            + '.bf-grid label.bf-check{flex-direction:row;align-items:flex-start;gap:8px;font-weight:600;}'
            + '.bf-grid label.bf-check input{margin-top:3px;}'
            + '.bf-wide{grid-column:1/-1;}'
            + '.bf-hint{grid-column:1/-1;font-size:12.5px;color:#B45309;}';
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

    // 미리보기용 급여비용 총액(공단 수가표). 값을 알 수 없거나 청구할 수 없는 시간이면 null.
    // 방문목욕은 60분 이상 전액, 40~60분 80%, 40분 미만 불가, 1인 몸 씻기 예외는 80%/70%(고시 제26조).
    function fee(benefit, minutes, mode, solo) {
        const t = info && info.visit_fees;
        if (!t) return null;
        if (benefit === 'home_bath') {
            const row = t.home_bath.find(r => r.mode === mode);
            const rules = t.home_bath_rules;
            if (!row || !rules || minutes < rules.min) return null;
            const reduced = minutes < rules.full_min;
            if (solo) return mode === rules.solo_mode ? Math.floor(row.fee * rules.solo_percent[reduced ? 'reduced' : 'full'] / 100) : null;
            return reduced ? Math.floor(row.fee * rules.reduced_percent / 100) : row.fee;
        }
        if (benefit === 'home_nursing') { const row = t.home_nursing.find(r => minutes >= r.min && (r.max === null || minutes < r.max)); return row ? row.fee : null; }
        const rows = t.home_care.filter(r => minutes >= r.min);
        return rows.length ? rows[rows.length - 1].fee : null;
    }

    /* el에 입력칸을 그린다. opts: { selfId(기록·계획의 주 요양보호사), withNote(기록 화면: 지시서 메모·산정 사유·2인 동시 제공), locked(급여 종류 고정),
       durationEl, onChange(benefit) }
       반환: { benefit(), value(), set(v), setSelf(id), updateHint() } */
    function mount(el, opts = {}) {
        const record = !!opts.withNote;
        const codes = usable();
        const empty = { benefit: () => 'home_care', value: () => ({ benefit_type: null, bath_mode: null, co_caregiver_id: null, nursing_order_note: null, special_note: null, bath_solo_exception: false }), set() {}, setSelf() {}, updateHint() {} };
        if (!el) return empty;
        const multi = codes.length > 1;
        if (!multi && !record) { el.innerHTML = ''; el.style.display = 'none'; return empty; }
        ensureStyle();
        el.style.display = '';
        el.innerHTML = `<div class="bf-grid">
            ${multi ? '<label>급여 종류<select data-bf="benefit"></select></label>' : ''}
            <label data-bf-show="home_bath">목욕 방식<select data-bf="mode"><option value="">방식을 고르세요</option>${Object.entries(BATH_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
            <label data-bf-show="home_bath">함께 가는 요양보호사 (2인 이상 제공)<select data-bf="co"></select></label>
            ${record ? `
            <label class="bf-check bf-wide" data-bf-show="home_bath" data-bf-solo-row><input type="checkbox" data-bf="solo"><span>수치심 등으로 <b>몸 씻기만 1인</b>이 제공했습니다 (방문목욕차량 미이용일 때만, 사유 필수 · 급여비용의 80%/70%)</span></label>
            <label class="bf-check bf-wide" data-bf-show="home_care"><input type="checkbox" data-bf="pair"><span>요양보호사 <b>2인이 동시에</b> 제공했습니다 (수급자 상태상 불가피한 경우만 · 요양보호사별로 각각 청구)</span></label>
            <label data-bf-show="home_care" data-bf-pair-row>함께 제공한 요양보호사<select data-bf="pairCo"></select></label>
            <label data-bf-show="home_nursing" class="bf-wide">방문간호지시서 확인 메모<input type="text" data-bf="note" maxlength="200" placeholder="예: 지시서 발급일·번호"></label>
            <label class="bf-wide" data-bf-reason-row>산정 사유 (공단 기록지에 적는 내용)<textarea data-bf="reason" rows="2" maxlength="300" placeholder="2인 동시 제공: 수급자 동의 내용과 당시 상태 / 방문목욕: 1인 몸 씻기 사유, 같은 주 2회 이상이면 변실금·요실금 등 불가피한 사유"></textarea></label>
            <div class="bf-hint" data-bf="hint"></div>` : ''}
        </div>`;
        const q = (k) => el.querySelector(`[data-bf="${k}"]`);
        const benefitSel = q('benefit');
        let selfId = opts.selfId || null;

        const benefit = () => (benefitSel ? benefitSel.value : 'home_care');
        const choices = () => staff.filter(u => u.id !== selfId && !NURSING_JOBS.includes(u.job_type));
        function fillStaff(sel, keep) {
            if (!sel) return;
            sel.innerHTML = '<option value="">요양보호사를 고르세요</option>' + choices().map(u => `<option value="${u.id}">${u.full_name}</option>`).join('');
            if (keep && [...sel.options].some(o => o.value === String(keep))) sel.value = String(keep);
        }
        function renderBenefits() {
            if (!benefitSel) return;
            const keep = benefitSel.value;
            const allowed = opts.locked ? [opts.locked] : allowedFor(selfId);
            benefitSel.innerHTML = allowed.map(c => `<option value="${c}">${label(c)}</option>`).join('');
            if (allowed.includes(keep)) benefitSel.value = keep;
        }
        function minutes() { return opts.durationEl ? Number(opts.durationEl.value) : null; }
        function updateHint() {
            const hint = q('hint');
            if (!hint) return;
            const b = benefit(), m = minutes(), rules = info && info.visit_fees && info.visit_fees.home_bath_rules;
            let text = '';
            if (b === 'home_bath' && rules && m !== null) {
                if (m < rules.min) text = `방문목욕은 ${rules.min}분 이상 제공해야 청구할 수 있습니다.`;
                else if (m < rules.full_min) text = `${rules.full_min}분 미만이라 급여비용의 ${rules.reduced_percent}%만 청구됩니다. 방문목욕은 주 1회까지 청구할 수 있습니다.`;
                else text = '방문목욕은 주 1회까지 청구할 수 있습니다 (변실금·요실금 등 불가피하면 사유를 적어 주세요).';
            } else if (b === 'home_care' && q('pair') && q('pair').checked) {
                text = '2인 동시 제공은 요양보호사별로 같은 금액을 각각 청구하며, 함께 제공한 요양보호사에게도 같은 기록이 만들어집니다.';
            }
            hint.textContent = text;
        }
        function refresh() {
            const b = benefit();
            const pair = q('pair'), solo = q('solo'), mode = q('mode');
            el.querySelectorAll('[data-bf-show]').forEach(row => { row.style.display = row.dataset.bfShow === b ? '' : 'none'; });
            const soloRow = el.querySelector('[data-bf-solo-row]');
            if (soloRow && b === 'home_bath') {
                const ok = mode.value === 'no_vehicle';  // 1인 예외는 차량을 쓰지 않은 목욕에만 해당한다
                soloRow.style.display = ok ? '' : 'none';
                if (!ok && solo) solo.checked = false;
            }
            const pairRow = el.querySelector('[data-bf-pair-row]');
            if (pairRow && b === 'home_care') pairRow.style.display = pair && pair.checked ? '' : 'none';
            const reasonRow = el.querySelector('[data-bf-reason-row]');
            if (reasonRow) reasonRow.style.display = (b === 'home_bath' || (b === 'home_care' && pair && pair.checked)) ? '' : 'none';
            if (opts.durationEl && multi) applyDurations(opts.durationEl, b);
            updateHint();
            if (opts.onChange) opts.onChange(b);
        }
        renderBenefits();
        fillStaff(q('co')); fillStaff(q('pairCo'));
        if (benefitSel) benefitSel.addEventListener('change', refresh);
        ['mode', 'co', 'note', 'solo', 'pair', 'pairCo', 'reason'].forEach(k => { const x = q(k); if (x) x.addEventListener('change', refresh); });
        refresh();
        if (opts.locked && benefitSel) { benefitSel.value = opts.locked; benefitSel.disabled = true; refresh(); }

        return {
            benefit,
            updateHint,
            value() {
                const b = benefit();
                const val = (k) => { const x = q(k); return x ? x.value : ''; };
                const pair = q('pair'), solo = q('solo');
                let co = null;
                if (b === 'home_bath' && val('co')) co = Number(val('co'));
                if (b === 'home_care' && pair && pair.checked && val('pairCo')) co = Number(val('pairCo'));
                const reasonVisible = el.querySelector('[data-bf-reason-row]') && el.querySelector('[data-bf-reason-row]').style.display !== 'none';
                return {
                    benefit_type: b === 'home_care' ? null : b,
                    bath_mode: b === 'home_bath' && val('mode') ? val('mode') : null,
                    co_caregiver_id: co,
                    nursing_order_note: b === 'home_nursing' && val('note').trim() ? val('note').trim() : null,
                    special_note: reasonVisible && val('reason').trim() ? val('reason').trim() : null,
                    bath_solo_exception: b === 'home_bath' && !!(solo && solo.checked),
                };
            },
            set(v) {
                v = v || {};
                if (benefitSel && v.benefit_type && [...benefitSel.options].some(o => o.value === v.benefit_type)) benefitSel.value = v.benefit_type;
                const b = benefit();
                if (q('mode')) q('mode').value = v.bath_mode || '';
                fillStaff(q('co'), b === 'home_bath' ? v.co_caregiver_id : null);
                fillStaff(q('pairCo'), b === 'home_care' ? v.co_caregiver_id : null);
                if (q('pair')) q('pair').checked = b === 'home_care' && !!v.co_caregiver_id;
                if (q('solo')) q('solo').checked = !!v.bath_solo_exception;
                if (q('note')) q('note').value = v.nursing_order_note || '';
                if (q('reason')) q('reason').value = v.special_note || '';
                refresh();
            },
            setSelf(id) {
                selfId = id ? Number(id) : null;
                renderBenefits();
                fillStaff(q('co'), q('co') && q('co').value); fillStaff(q('pairCo'), q('pairCo') && q('pairCo').value);
                refresh();
            },
        };
    }

    return { load, usable, label, mount, fee, applyDurations, BATH_LABELS };
})();
