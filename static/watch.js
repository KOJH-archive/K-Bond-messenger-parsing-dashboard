/* Independent from the original search/socket state and local filters. */
(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    let settings = null, busy = false, polling = false, serial = 0, editingId = null, typeAliases = {};
    function error(message = '') { $('watchError').textContent = message; $('watchError').hidden = !message; }
    async function api(url, options) {
        const response = await fetch(url, {cache:'no-store', ...options});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '관심조건 처리에 실패했습니다.');
        return data;
    }
    function description(rule) {
        return [rule.keyword && `키워드: ${rule.keyword}`, `채권종류: ${rule.types.length ? rule.types.join(' / ') : '전체 종류 (제한 없음)'}`,
            rule.maturity_from && `만기 ${rule.maturity_from}부터`, rule.maturity_to && `${rule.maturity_to}까지`,
            rule.min_months !== null && `잔존 ${rule.min_months}개월 이상`,
            rule.max_months !== null && `잔존 ${rule.max_months}개월 이하`].filter(Boolean).join(' · ');
    }
    function renderSettings() {
        $('watchDesktop').checked = settings.desktop_enabled;
        $('watchTabCount').textContent = settings.rules.filter(r=>r.enabled).length;
        $('watchRules').innerHTML = settings.rules.map(r => `<article class="watch-rule ${r.enabled?'':'disabled'}"><label><input type="checkbox" data-watch-toggle="${escape(r.id)}" ${r.enabled?'checked':''}><span><strong>${escape(r.name)}</strong><small>${escape(description(r))}</small></span></label><div class="watch-rule-actions"><button type="button" data-watch-edit="${escape(r.id)}">수정</button><button type="button" data-watch-delete="${escape(r.id)}" aria-label="${escape(r.name)} 삭제">삭제</button></div></article>`).join('');
        const selected = $('watchRuleFilter').value;
        $('watchRuleFilter').innerHTML = '<option value="">모든 관심조건</option>' + settings.rules.map(r=>`<option value="${escape(r.id)}">${escape(r.name)}${r.enabled?'':' (꺼짐)'}</option>`).join('');
        if (settings.rules.some(r=>r.id===selected)) $('watchRuleFilter').value = selected;
    }
    async function loadSettings() {
        settings = await api('/api/watch/settings');
        typeAliases = settings.type_aliases || {};
        $('watchTypeOptions').innerHTML = settings.types.map(t=>`<label><input type="checkbox" name="types" value="${escape(t)}">${escape(t)}</label>`).join('');
        renderSettings();
        previewTypes();
        if (settings.error) error(settings.error);
    }
    async function save(next) {
        if (busy) return false;
        busy = true; serial++;
        $('watchSave').disabled = $('watchDesktop').disabled = true;
        try {
            settings = await api('/api/watch/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(next)});
            renderSettings(); error();
            return true;
        } catch (err) {
            error(err.message);
            // Refresh revision without losing the draft form on a concurrent edit or save failure.
            try { settings = await api('/api/watch/settings'); renderSettings(); } catch (_) {}
            return false;
        } finally { busy = false; $('watchSave').disabled = $('watchDesktop').disabled = false; refresh(); }
    }
    async function refresh() {
        if (!settings || busy || polling) return;
        polling = true;
        const mine = serial;
        try {
            const data = await api('/api/watch/results?rule=' + encodeURIComponent($('watchRuleFilter').value));
            if (mine !== serial) return;
            if (data.revision !== settings.revision) {
                settings = await api('/api/watch/settings'); renderSettings();
            }
            $('watchNote').textContent = `${data.date} 수집분 · 일치 ${data.total.toLocaleString()}건 중 최신 ${data.shown.toLocaleString()}건 · 5초마다 갱신`;
            $('watchMonitorStatus').textContent = data.error || (data.desktop_enabled ? (data.monitor_running ? 'PC 알림 켜짐 · 대시보드 실행 중 감지' : 'PC 알림 감시가 시작되지 않았습니다. 통합실행을 다시 시작해 주세요.') : 'PC 알림 꺼짐 · 관심조건 필터는 사용 가능');
            $('watchRows').innerHTML = data.rows.map(r => `<tr><td class="time">${escape(r.timestamp)}</td><td class="room">${escape((r.room||'').replace('[채권] ',''))}</td><td>${r.watch_rules.map(rule=>`<span class="watch-rule-tag">${escape(rule.name)}</span>`).join('')}</td><td>${escape((r.watch_types||[]).join(' / ')||'미분류')}</td><td><span class="ticker">${escape(r.ticker||'-')}</span></td><td>${escape(r.maturity||'-')}</td><td>${escape(r.side||'-')}</td><td class="content">${escape(r.content||'')}</td></tr>`).join('');
            $('watchEmpty').hidden = data.rows.length > 0;
            $('watchEmpty').textContent = settings.rules.length ? '활성화된 관심조건에 맞는 오늘의 메시지가 없습니다.' : '위에서 관심조건을 추가해 주세요. 기존 채권 내역은 그대로 이용할 수 있습니다.';
        } catch (err) { error('관심조건 연결 실패: ' + err.message); }
        finally { polling = false; }
    }
    function tab(watch) {
        $('basicView').hidden = watch; $('watchView').hidden = !watch;
        for (const [id, active] of [['basicTab',!watch],['watchTab',watch]]) {
            $(id).classList.toggle('active', active); $(id).setAttribute('aria-selected', String(active));
        }
        if (watch) refresh();
    }
    $('basicTab').addEventListener('click',()=>tab(false));
    $('watchTab').addEventListener('click',()=>tab(true));
    const aliasTypes = value => typeAliases[String(value||'').replace(/\s+/g,'')] || [];
    function previewTypes() {
        const form = new FormData($('watchForm'));
        const chosen = form.getAll('types'), fromKeyword = aliasTypes(form.get('keyword'));
        let types = chosen.length ? chosen : aliasTypes(form.get('name'));
        if (fromKeyword.length) types = chosen.length ? chosen.filter(t=>fromKeyword.includes(t)) : fromKeyword;
        $('watchTypePreview').textContent = fromKeyword.length && chosen.length && !types.length
            ? '키워드의 채권종류와 선택한 종류가 다릅니다. 조건을 확인해 주세요.'
            : `적용 채권종류: ${types.length ? types.join(' / ') : '전체 종류 (제한 없음)'}${!chosen.length&&types.length?' · 입력한 종류명에서 자동 적용':''}`;
    }
    function resetEditor() {
        editingId = null; $('watchForm').reset();
        $('watchSave').textContent = '관심조건 추가'; $('watchCancel').hidden = true;
        previewTypes();
    }
    $('watchForm').addEventListener('input',previewTypes);
    $('watchCancel').addEventListener('click',resetEditor);
    $('watchForm').addEventListener('submit',async event=>{
        event.preventDefault(); if (!settings || busy) return;
        const form = new FormData(event.currentTarget);
        const previous = editingId ? settings.rules.find(r=>r.id===editingId) : null;
        if (editingId && !previous) { error('수정하던 조건이 다른 창에서 삭제되었습니다.'); return; }
        const rule = {id:editingId||crypto.randomUUID(), enabled:previous?previous.enabled:true, types:form.getAll('types')};
        for (const key of ['name','keyword','maturity_from','maturity_to']) rule[key] = String(form.get(key)||'').trim();
        for (const key of ['min_months','max_months']) rule[key] = form.get(key)===''?null:Number(form.get(key));
        const rules = editingId ? settings.rules.map(r=>r.id===editingId?rule:r) : [...settings.rules,rule];
        if (await save({...settings, rules})) resetEditor();
    });
    $('watchDesktop').addEventListener('change',()=>{ if(settings) save({...settings, desktop_enabled:$('watchDesktop').checked}); });
    $('watchRules').addEventListener('change',event=>{
        const id = event.target.dataset.watchToggle;
        if (id && settings && !busy) save({...settings,rules:settings.rules.map(r=>r.id===id?{...r,enabled:event.target.checked}:r)});
    });
    $('watchRules').addEventListener('click',event=>{
        const edit = event.target.closest('[data-watch-edit]')?.dataset.watchEdit;
        if (edit && settings && !busy) {
            const rule = settings.rules.find(r=>r.id===edit);
            if (!rule) return;
            editingId = edit;
            for (const key of ['name','keyword','maturity_from','maturity_to','min_months','max_months']) $('watchForm').elements.namedItem(key).value=rule[key]??'';
            $('watchTypeOptions').querySelectorAll('input').forEach(input=>{input.checked=rule.types.includes(input.value);});
            $('watchSave').textContent='수정 저장'; $('watchCancel').hidden=false; previewTypes();
            $('watchForm').scrollIntoView({behavior:'smooth',block:'center'});
            return;
        }
        const id = event.target.closest('[data-watch-delete]')?.dataset.watchDelete;
        if (id && settings && !busy) {
            if (id===editingId) resetEditor();
            save({...settings,rules:settings.rules.filter(r=>r.id!==id)});
        }
    });
    $('watchRuleFilter').addEventListener('change',()=>{serial++; refresh();});
    $('watchRefresh').addEventListener('click',refresh);
    $('watchTest').addEventListener('click',async()=>{
        $('watchTest').disabled = true;
        try { await api('/api/watch/test',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); error(); }
        catch(err){error(err.message);}
        finally{$('watchTest').disabled=false;}
    });
    loadSettings().then(refresh).catch(err=>error(err.message));
    setInterval(()=>{if(!$('watchView').hidden)refresh();},5000);
})();
