(function () {
    'use strict';
    var N = window.NEUTX, esc = N.esc;
    var PAGE = 24;
    var state = { kind: 'all', sort: 'recent', q: '', view: 'grid', items: [], total: 0, select: false, selected: new Set(), current: null };
    var $ = function (id) { return document.getElementById(id); };

    function card(m) {
        var ext = (m.original_name.split('.').pop() || m.kind).slice(0, 4).toUpperCase();
        var sel = state.selected.has(m.id) ? ' selected' : '';
        var actions = '<div class="media-overlay absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center gap-2">' +
            btn('preview', m.kind === 'video' ? 'play' : 'eye', 'Preview', 'bg-electric text-obsidian hover:bg-goldlight') +
            btn('download', 'download', 'Download', 'bg-white/15 text-cloud border border-white/20 hover:bg-white/25') +
            btn('schedule', 'send', 'Schedule post', 'bg-white/15 text-cloud border border-white/20 hover:bg-white/25') +
            btn('delete', 'trash-2', 'Delete', 'bg-white/15 text-red-400 border border-red-500/30 hover:bg-red-500/20') + '</div>';
        var meta = '<span>' + (m.width ? m.width + '×' + m.height : m.kind) + '</span><span>' + N.bytes(m.size_bytes) + '</span>';
        var usage = m.post_count ? '<span class="text-[10px] text-electric font-mono uppercase tracking-wider flex items-center gap-1"><i data-lucide="link-2" class="w-3 h-3"></i>' + m.post_count + ' post' + (m.post_count > 1 ? 's' : '') + '</span>'
            : '<span class="text-[10px] text-gray-600 font-mono uppercase tracking-wider">' + (m.source === 'generated' ? 'generated' : 'uploaded') + '</span>';
        if (state.view === 'list') {
            return '<div data-id="' + m.id + '" class="media-item glass-card rounded-xl overflow-hidden flex items-center gap-4 p-2 pr-4' + sel + '">' +
                '<div class="relative w-16 h-16 shrink-0 rounded-lg overflow-hidden">' + N.thumb(m, 'w-full h-full') + '</div>' +
                '<div class="flex-1 min-w-0"><h4 class="text-sm font-semibold text-cloud truncate">' + esc(m.original_name) + '</h4>' +
                '<div class="flex gap-4 text-[10px] font-mono text-gray-500">' + meta + '<span>' + esc(N.date(m.created_at)) + '</span></div></div>' + usage +
                '<div class="flex gap-1">' + btn('preview', 'eye', 'Preview', 'text-gray-400 hover:text-white', 'w-8 h-8') + btn('schedule', 'send', 'Schedule post', 'text-gray-400 hover:text-white', 'w-8 h-8') +
                btn('delete', 'trash-2', 'Delete', 'text-gray-400 hover:text-red-400', 'w-8 h-8') + '</div></div>';
        }
        return '<div data-id="' + m.id + '" class="media-item glass-card rounded-2xl overflow-hidden cursor-pointer group' + sel + '">' +
            '<div class="relative aspect-[9/16] bg-gray-900 overflow-hidden">' + N.thumb(m, 'absolute inset-0 w-full h-full') +
            '<span class="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-black/70 backdrop-blur-sm border border-white/10 text-[10px] text-cloud font-mono uppercase tracking-wider">' + esc(ext) + '</span>' +
            (m.source === 'upload' && m.kind === 'image' ? '<span class="absolute top-2 right-2 px-1.5 py-0.5 rounded bg-black/70 border border-white/10 text-[10px] text-electric font-mono uppercase tracking-wider">Hero</span>' : '') +
            actions + '</div><div class="p-3"><h4 class="text-sm font-semibold text-cloud truncate mb-1" title="' + esc(m.original_name) + '">' + esc(m.original_name) + '</h4>' +
            '<div class="flex items-center justify-between text-[10px] font-mono text-gray-500">' + meta + '</div>' +
            '<div class="flex items-center justify-between mt-2 pt-2 border-t border-white/5"><span class="text-[10px] text-gray-500 font-mono">' + esc(N.date(m.created_at)) + '</span>' + usage + '</div></div></div>';
    }

    function btn(action, icon, title, cls, size) {
        return '<button type="button" data-action="' + action + '" title="' + title + '" aria-label="' + title + '" class="' + (size || 'w-10 h-10') +
            ' rounded-full flex items-center justify-center transition-colors ' + cls + '"><i data-lucide="' + icon + '" class="w-4 h-4"></i></button>';
    }

    function renderGrid() {
        var grid = $('media-grid');
        grid.className = state.view === 'list' ? 'flex flex-col gap-2' : 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5';
        grid.innerHTML = state.items.length ? state.items.map(card).join('')
            : '<div class="col-span-full p-10 text-center text-gray-500 text-sm border border-dashed border-white/10 rounded-2xl">' +
              (state.q || state.kind !== 'all' ? 'No media matches your filters.' : 'Your library is empty. Generate something in the Studio or upload a file below.') + '</div>';
        $('showing').textContent = state.total ? 'Showing ' + state.items.length + ' of ' + state.total : '';
        $('load-more').classList.toggle('hidden', state.items.length >= state.total);
        $('grid-label').textContent = state.q ? 'Results for "' + state.q + '"' : state.kind === 'all' ? 'Library' : state.kind === 'video' ? 'Videos' : 'Images';
        N.icons();
    }

    async function load(append) {
        var params = new URLSearchParams({ kind: state.kind, sort: state.sort, q: state.q, limit: PAGE, offset: append ? state.items.length : 0 });
        var res = await N.api('/api/media?' + params);
        state.items = append ? state.items.concat(res.items) : res.items;
        state.total = res.total;
        var st = res.stats;
        $('st-total').textContent = st.count;
        $('st-total-sub').textContent = '+' + st.added_this_week + ' this week';
        $('st-total-sub').className = 'text-xs font-mono uppercase tracking-wider mt-2 ' + (st.added_this_week ? 'text-green-400' : 'text-gray-500');
        $('st-bytes').textContent = N.bytes(st.bytes);
        $('st-bytes-sub').textContent = 'on this server';
        $('st-videos').textContent = st.videos.n;
        $('st-videos-sub').textContent = N.bytes(st.videos.bytes);
        $('st-images').textContent = st.images.n;
        $('st-images-sub').textContent = N.bytes(st.images.bytes);
        $('upload-limits').textContent = 'PNG / JPG / WEBP / MP4 / MOV / WEBM · Max ' + res.max_upload_mb + ' MB / file';
        renderGrid();
    }

    async function loadRendering() {
        var jobs = await N.api('/api/jobs?active=true');
        var box = $('rendering');
        box.classList.toggle('hidden', !jobs.length);
        box.innerHTML = '<p class="mono-label mb-3">Rendering now</p><div class="flex flex-wrap gap-3">' + jobs.map(function (j) {
            return '<a href="studio.html?job=' + j.id + '" class="glass-card rounded-xl px-4 py-3 flex items-center gap-3 border border-electric/30 max-w-xs">' +
                '<i data-lucide="loader-2" class="w-4 h-4 text-electric animate-spin shrink-0"></i><span class="text-sm truncate">' + esc(j.prompt) + '</span></a>';
        }).join('') + '</div>';
        N.icons();
        if (jobs.length) setTimeout(function () { loadRendering().catch(function () {}); load(false).catch(function () {}); }, 6000);
    }

    // ------------------------------------------------------------------ actions
    function find(id) { return state.items.find(function (m) { return m.id === id; }); }

    async function del(ids) {
        if (!confirm(ids.length > 1 ? 'Delete ' + ids.length + ' files permanently?' : 'Delete this file permanently?')) return false;
        var res = await N.api('/api/media/bulk-delete', { body: { ids: ids } });
        if (res.errors.length) N.toast(res.errors.join(' · '), 'error');
        if (res.deleted) N.toast('Deleted ' + res.deleted + ' file' + (res.deleted > 1 ? 's' : ''), 'success');
        ids.forEach(function (id) { state.selected.delete(id); });
        updateBulk();
        await load(false);
        return res.deleted > 0;
    }

    function download(m) {
        var a = document.createElement('a');
        a.href = m.url + '?download=1';
        a.download = m.original_name;
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    function openPreview(m) {
        state.current = m;
        $('pv-name').textContent = m.original_name;
        $('pv-media').innerHTML = m.kind === 'video'
            ? '<video src="' + esc(m.url) + '" controls autoplay muted playsinline class="max-h-[60vh] max-w-full"></video>'
            : '<img src="' + esc(m.url) + '" alt="" class="max-h-[60vh] max-w-full object-contain">';
        var rows = [['Type', m.mime], ['Size', N.bytes(m.size_bytes)], ['Dimensions', m.width ? m.width + '×' + m.height : '—'], ['Added', new Date(m.created_at).toLocaleString()]];
        $('pv-meta').innerHTML = rows.map(function (r) { return '<div><dt class="mono-label">' + r[0] + '</dt><dd class="text-gray-200 mt-1 break-all">' + esc(r[1]) + '</dd></div>'; }).join('');
        $('pv-prompt').textContent = m.prompt ? 'Prompt: ' + m.prompt : '';
        $('pv-download').href = m.url + '?download=1';
        $('pv-schedule').href = 'studio.html?media=' + m.id;
        N.icons();
        $('preview').showModal();
    }

    $('media-grid').addEventListener('click', async function (e) {
        var item = e.target.closest('.media-item');
        if (!item) return;
        var m = find(+item.dataset.id);
        var action = e.target.closest('[data-action]');
        if (state.select && !action) { toggleSelected(m.id, item); return; }
        if (!action) { openPreview(m); return; }
        var act = action.dataset.action;
        try {
            if (act === 'preview') openPreview(m);
            else if (act === 'download') download(m);
            else if (act === 'schedule') location.href = 'studio.html?media=' + m.id;
            else if (act === 'delete') await del([m.id]);
        } catch (err) { N.fail(err); }
    });

    $('preview').addEventListener('click', function (e) {
        if (e.target.id === 'preview' || e.target.closest('[data-close]')) $('preview').close();
    });
    $('preview').addEventListener('close', function () { $('pv-media').innerHTML = ''; });
    $('pv-delete').addEventListener('click', async function () {
        try { if (await del([state.current.id])) $('preview').close(); } catch (err) { N.fail(err); }
    });

    // ------------------------------------------------------------------ selection
    function toggleSelected(id, el) {
        if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
        el.classList.toggle('selected', state.selected.has(id));
        updateBulk();
    }
    function updateBulk() {
        $('bulk-count').textContent = state.selected.size + ' selected';
    }
    $('select-mode-btn').addEventListener('click', function () {
        state.select = !state.select;
        $('bulk-bar').classList.toggle('hidden', !state.select);
        var b = $('select-mode-btn');
        ['bg-electric/10', 'border-electric/40', 'text-electric'].forEach(function (c) { b.classList.toggle(c, state.select); });
        ['bg-white/5', 'border-white/10', 'text-cloud'].forEach(function (c) { b.classList.toggle(c, !state.select); });
        if (!state.select) { state.selected.clear(); updateBulk(); renderGrid(); }
    });
    $('bulk-clear').addEventListener('click', function () { state.selected.clear(); updateBulk(); renderGrid(); });
    $('bulk-delete').addEventListener('click', function () {
        if (state.selected.size) del(Array.from(state.selected)).catch(N.fail);
    });
    $('bulk-download').addEventListener('click', function () {
        Array.from(state.selected).forEach(function (id, i) {
            var m = find(id);
            if (m) setTimeout(function () { download(m); }, i * 400);
        });
    });

    // ------------------------------------------------------------------ filters
    var searchTimer;
    $('media-search').addEventListener('input', function (e) {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () { state.q = e.target.value.trim(); load(false).catch(N.fail); }, 250);
    });
    $('kind-filters').addEventListener('click', function (e) {
        var b = e.target.closest('[data-kind]');
        if (!b) return;
        $('kind-filters').querySelectorAll('.filter-pill').forEach(function (x) { x.classList.toggle('active', x === b); });
        state.kind = b.dataset.kind;
        load(false).catch(N.fail);
    });
    $('media-sort').addEventListener('change', function (e) { state.sort = e.target.value; load(false).catch(N.fail); });
    $('view-toggle').addEventListener('click', function (e) {
        var b = e.target.closest('[data-view]');
        if (!b) return;
        $('view-toggle').querySelectorAll('.filter-pill').forEach(function (x) { x.classList.toggle('active', x === b); });
        state.view = b.dataset.view;
        renderGrid();
    });
    $('load-more').addEventListener('click', function () { load(true).catch(N.fail); });

    // ------------------------------------------------------------------ upload
    var dz = $('dropzone'), input = $('file-input');
    dz.addEventListener('click', function () { input.click(); });
    dz.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    input.addEventListener('change', function () { upload(input.files); input.value = ''; });
    ['dragenter', 'dragover'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('border-electric'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('border-electric'); }); });
    dz.addEventListener('drop', function (e) { upload(e.dataTransfer.files); });

    async function upload(files) {
        if (!files || !files.length) return;
        var fd = new FormData();
        Array.prototype.forEach.call(files, function (f) { fd.append('files', f); });
        var title = $('upload-title'), original = title.textContent;
        title.textContent = 'Uploading ' + files.length + ' file' + (files.length > 1 ? 's' : '') + '...';
        dz.classList.add('opacity-60', 'pointer-events-none');
        try {
            var res = await N.api('/api/media', { form: fd });
            if (res.errors.length) N.toast(res.errors.join(' · '), 'error');
            N.toast('Uploaded ' + res.items.length + ' file' + (res.items.length > 1 ? 's' : ''), 'success');
            await load(false);
        } catch (err) { N.fail(err); } finally {
            title.textContent = original;
            dz.classList.remove('opacity-60', 'pointer-events-none');
        }
    }

    (async function init() {
        await N.ready;
        var q = N.query('q');
        if (q) { state.q = q; $('media-search').value = q; }
        await load(false);
        loadRendering().catch(function () {});
        if (N.query('upload')) {
            $('upload-zone').scrollIntoView({ behavior: 'smooth' });
            dz.classList.add('border-electric');
            dz.focus();
        }
    })().catch(N.fail);
})();
