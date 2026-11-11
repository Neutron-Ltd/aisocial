(function () {
    'use strict';
    var N = window.NEUTX, esc = N.esc;
    var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    var state = { view: 'month', anchor: null, today: null, posts: [], filter: '', current: null };

    function ymd(d) {
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }
    function parseYmd(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
    function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
    function todayIn(tz) {
        return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    }
    function timeLabel(hm) {
        var p = hm.split(':');
        return new Date(2000, 0, 1, +p[0], +p[1]).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    }

    function range() {
        if (state.view === 'week') {
            var start = addDays(state.anchor, -state.anchor.getDay());
            return { start: start, days: 7 };
        }
        var first = new Date(state.anchor.getFullYear(), state.anchor.getMonth(), 1);
        var gridStart = addDays(first, -first.getDay());
        var last = new Date(state.anchor.getFullYear(), state.anchor.getMonth() + 1, 0);
        var days = Math.ceil((last.getDate() + first.getDay()) / 7) * 7;
        return { start: gridStart, days: days };
    }

    async function load() {
        var r = range();
        state.posts = await N.api('/api/posts?from=' + ymd(r.start) + '&to=' + ymd(addDays(r.start, r.days - 1)));
        render();
    }

    function chip(post) {
        var draggable = post.status === 'scheduled';
        var title = post.title || post.caption.split('\n')[0] || (post.media && post.media.original_name) || 'Post';
        var tone = { failed: 'border-red-500/40', partial: 'border-yellow-500/40', published: 'border-emerald-500/30', publishing: 'border-blue-500/40' }[post.status] || 'border-white/10';
        return '<div role="button" tabindex="0" data-post="' + post.id + '"' + (draggable ? ' draggable="true"' : '') +
            ' class="' + (draggable ? 'draggable-post ' : 'cursor-pointer ') + 'p-1.5 rounded-lg bg-black/50 border ' + tone + ' hover:border-electric/50 text-left">' +
            '<div class="flex items-center gap-1 mb-0.5">' + post.targets.map(function (t) { return N.platformBadge(t.platform, 'w-4 h-4 !rounded'); }).join('') +
            '<span class="text-[10px] font-mono text-gray-400 ml-auto">' + esc(timeLabel(post.local_time)) + '</span></div>' +
            '<p class="text-[11px] font-medium text-white truncate">' + esc(title) + '</p></div>';
    }

    function render() {
        var r = range(), month = state.anchor.getMonth();
        document.getElementById('cal-title').textContent = state.view === 'week'
            ? 'Week of ' + r.start.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
            : state.anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
        document.querySelectorAll('.view-btn').forEach(function (b) { b.classList.toggle('active', b.dataset.view === state.view); });
        document.getElementById('cal-weekdays').innerHTML = WEEKDAYS.map(function (d) { return '<div class="py-3 text-center mono-label">' + d + '</div>'; }).join('');

        var byDay = {};
        state.posts.forEach(function (p) {
            if (state.filter && !p.targets.some(function (t) { return t.platform === state.filter; })) return;
            (byDay[p.local_date] = byDay[p.local_date] || []).push(p);
        });

        var grid = document.getElementById('calendar-grid');
        grid.style.gridTemplateRows = 'repeat(' + (r.days / 7) + ', minmax(' + (state.view === 'week' ? '420px' : '120px') + ', 1fr))';
        var html = '';
        for (var i = 0; i < r.days; i++) {
            var d = addDays(r.start, i), key = ymd(d);
            var outside = state.view === 'month' && d.getMonth() !== month;
            var isToday = key === state.today, past = key < state.today;
            html += '<div data-day="' + key + '" class="day-cell p-2 border-r border-b border-white/5 ' + (outside ? 'bg-black/20 text-gray-600 ' : 'hover:bg-white/5 ') + 'transition-colors group flex flex-col">' +
                '<div class="flex justify-between items-start mb-1"><div class="text-sm font-medium ' +
                (isToday ? 'w-6 h-6 rounded-full bg-electric text-obsidian flex items-center justify-center' : outside ? '' : 'text-gray-300') + '">' + d.getDate() + '</div>' +
                (past ? '' : '<a href="studio.html" title="Create a post" class="opacity-0 group-hover:opacity-100 focus:opacity-100 text-gray-500 hover:text-white transition-opacity"><i data-lucide="plus" class="w-3.5 h-3.5"></i></a>') +
                '</div><div class="posts-container space-y-1.5 flex-1 pb-2">' + (byDay[key] || []).map(chip).join('') + '</div></div>';
        }
        grid.innerHTML = html;
        N.icons();
    }

    async function loadAttention() {
        var res = await Promise.all([N.api('/api/posts?status=failed&limit=20'), N.api('/api/posts?status=partial&limit=20')]);
        var items = res[0].concat(res[1]);
        var box = document.getElementById('attention');
        if (!items.length) { box.classList.add('hidden'); return; }
        box.className = 'mb-6 shrink-0 glass-panel rounded-2xl border border-red-500/30 p-4';
        box.innerHTML = '<p class="text-sm font-semibold text-red-300 mb-3 flex items-center gap-2"><i data-lucide="alert-triangle" class="w-4 h-4"></i> Needs attention</p>' +
            '<div class="flex flex-wrap gap-2">' + items.map(function (p) {
                return '<button type="button" data-post="' + p.id + '" class="px-3 py-1.5 rounded-lg bg-black/40 border border-white/10 text-xs text-left hover:border-electric/50">' +
                    esc(p.local_date + ' · ' + (p.title || p.caption.split('\n')[0] || 'Post')) + ' — ' + esc(p.status) + '</button>';
            }).join('') + '</div>';
        N.icons();
    }

    // ------------------------------------------------------------------ post dialog
    var dialog = document.getElementById('post-dialog');

    async function openPost(id) {
        var post = await N.api('/api/posts/' + id);
        state.current = post;
        var editable = post.status === 'scheduled';
        document.getElementById('pd-title').textContent = post.title || 'Post #' + post.id;
        document.getElementById('pd-status').innerHTML = N.statusPill(post.status) + ' <span class="text-xs text-gray-500 ml-2">' + esc(post.local_date + ' ' + timeLabel(post.local_time)) + '</span>';
        var m = post.media;
        document.getElementById('pd-media').innerHTML = !m ? '' : m.kind === 'video'
            ? '<video src="' + esc(m.url) + '" controls muted playsinline class="w-full h-full object-contain"></video>'
            : '<img src="' + esc(m.url) + '" alt="" class="w-full h-full object-contain">';
        var cap = document.getElementById('pd-caption'), date = document.getElementById('pd-date'), time = document.getElementById('pd-time');
        cap.value = post.caption; date.value = post.local_date; time.value = post.local_time;
        [cap, date, time].forEach(function (el) { el.disabled = !editable; });
        date.min = editable ? state.today : '';
        document.getElementById('pd-targets').innerHTML = post.targets.map(function (t) {
            return '<div class="flex items-start gap-3 p-3 rounded-xl bg-black/30 border border-white/5">' + N.platformBadge(t.platform, 'w-8 h-8') +
                '<div class="flex-1 min-w-0"><div class="flex items-center gap-2 flex-wrap"><span class="text-sm font-semibold text-white">' + esc((N.platforms[t.platform] || {}).label || t.platform) + '</span>' +
                '<span class="text-xs text-gray-500">' + (t.username ? '@' + esc(t.username) : 'disconnected account') + '</span>' + N.statusPill(t.status) + '</div>' +
                (t.error ? '<p class="text-xs text-red-300 mt-1 break-words">' + esc(t.error) + '</p>' : '') +
                (t.url ? '<a href="' + esc(t.url) + '" target="_blank" rel="noopener noreferrer" class="text-xs text-electric hover:text-goldlight mt-1 inline-flex items-center gap-1">View post <i data-lucide="external-link" class="w-3 h-3"></i></a>' : '') +
                '</div></div>';
        }).join('');
        var actions = [];
        if (editable) {
            actions.push('<button type="button" data-act="cancel" class="px-4 py-2 rounded-xl border border-red-500/30 text-red-300 text-sm hover:bg-red-500/10">Cancel post</button>');
            actions.push('<button type="button" data-act="now" class="px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-sm hover:bg-white/10">Publish now</button>');
            actions.push('<button type="button" data-act="save" class="gold-cta px-5 py-2 rounded-xl text-sm">Save changes</button>');
        } else if (post.status === 'failed' || post.status === 'partial') {
            actions.push('<button type="button" data-act="delete" class="px-4 py-2 rounded-xl border border-white/10 text-sm hover:bg-white/5">Remove from calendar</button>');
            actions.push('<button type="button" data-act="retry" class="gold-cta px-5 py-2 rounded-xl text-sm">Retry failed</button>');
        } else if (post.status === 'published') {
            actions.push('<button type="button" data-act="delete" class="px-4 py-2 rounded-xl border border-white/10 text-sm hover:bg-white/5">Remove from calendar</button>');
        }
        document.getElementById('pd-actions').innerHTML = actions.join('');
        N.icons();
        if (!dialog.open) dialog.showModal();
        if (post.status === 'publishing') setTimeout(function () { if (dialog.open && state.current && state.current.id === post.id) openPost(post.id); }, 4000);
    }

    dialog.addEventListener('click', async function (e) {
        if (e.target === dialog || e.target.closest('[data-close]')) { dialog.close(); return; }
        var btn = e.target.closest('[data-act]');
        if (!btn) return;
        var post = state.current, act = btn.dataset.act;
        btn.disabled = true;
        try {
            if (act === 'save') {
                await N.api('/api/posts/' + post.id, { method: 'PATCH', body: {
                    caption: document.getElementById('pd-caption').value,
                    date: document.getElementById('pd-date').value, time: document.getElementById('pd-time').value
                } });
                N.toast('Post updated', 'success');
                dialog.close();
            } else if (act === 'cancel' || act === 'delete') {
                if (!confirm(act === 'cancel' ? 'Cancel this scheduled post?' : 'Remove this post from the calendar? Published posts stay on the platforms.')) { btn.disabled = false; return; }
                await N.api('/api/posts/' + post.id, { method: 'DELETE' });
                N.toast(act === 'cancel' ? 'Post cancelled' : 'Post removed', 'success');
                dialog.close();
            } else if (act === 'now') {
                if (!confirm('Publish this post right now?')) { btn.disabled = false; return; }
                var nowDate = todayIn(N.user.timezone);
                var nowTime = new Intl.DateTimeFormat('en-GB', { timeZone: N.user.timezone, hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date());
                await N.api('/api/posts/' + post.id, { method: 'PATCH', body: { date: nowDate, time: nowTime } });
                N.toast('Publishing within a few seconds', 'success');
                await openPost(post.id);
            } else if (act === 'retry') {
                await N.api('/api/posts/' + post.id + '/retry', { method: 'POST' });
                N.toast('Retrying failed destinations', 'success');
                await openPost(post.id);
            }
            load(); loadAttention();
        } catch (err) { N.fail(err); btn.disabled = false; }
    });

    // ------------------------------------------------------------------ interactions
    function onOpen(e) {
        var el = e.target.closest('[data-post]');
        if (el) openPost(+el.dataset.post).catch(N.fail);
    }
    document.getElementById('calendar-grid').addEventListener('click', onOpen);
    document.getElementById('attention').addEventListener('click', onOpen);
    document.getElementById('calendar-grid').addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target.closest('[data-post]')) onOpen(e);
    });

    var grid = document.getElementById('calendar-grid');
    grid.addEventListener('dragstart', function (e) {
        var el = e.target.closest('.draggable-post');
        if (!el) return;
        e.dataTransfer.setData('text/plain', el.dataset.post);
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(function () { el.classList.add('dragging'); }, 0);
    });
    grid.addEventListener('dragend', function (e) {
        var el = e.target.closest('.draggable-post');
        if (el) el.classList.remove('dragging');
        grid.querySelectorAll('.drag-over').forEach(function (z) { z.classList.remove('drag-over'); });
    });
    grid.addEventListener('dragover', function (e) {
        var cell = e.target.closest('.day-cell');
        if (!cell || cell.dataset.day < state.today) return;
        e.preventDefault();
        grid.querySelectorAll('.drag-over').forEach(function (z) { if (z !== cell) z.classList.remove('drag-over'); });
        cell.classList.add('drag-over');
    });
    grid.addEventListener('drop', async function (e) {
        var cell = e.target.closest('.day-cell');
        if (!cell) return;
        e.preventDefault();
        cell.classList.remove('drag-over');
        var id = e.dataTransfer.getData('text/plain');
        var post = state.posts.find(function (p) { return String(p.id) === id; });
        if (!post || post.local_date === cell.dataset.day) return;
        try {
            await N.api('/api/posts/' + id, { method: 'PATCH', body: { date: cell.dataset.day } });
            N.toast('Rescheduled to ' + parseYmd(cell.dataset.day).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }), 'success');
        } catch (err) { N.fail(err); }
        load();
    });

    document.getElementById('cal-prev').addEventListener('click', function () { shift(-1); });
    document.getElementById('cal-next').addEventListener('click', function () { shift(1); });
    document.getElementById('cal-today').addEventListener('click', function () { state.anchor = parseYmd(state.today); load().catch(N.fail); });
    document.querySelectorAll('.view-btn').forEach(function (b) {
        b.addEventListener('click', function () { state.view = b.dataset.view; load().catch(N.fail); });
    });
    document.getElementById('cal-filter').addEventListener('change', function (e) { state.filter = e.target.value; render(); });

    function shift(dir) {
        var a = state.anchor;
        state.anchor = state.view === 'week' ? addDays(a, 7 * dir) : new Date(a.getFullYear(), a.getMonth() + dir, 1);
        load().catch(N.fail);
    }

    dialog.addEventListener('close', function () { state.current = null; });

    (async function init() {
        await N.ready;
        state.today = todayIn(N.user.timezone);
        state.anchor = parseYmd(state.today);
        document.getElementById('tz-label').textContent = N.user.timezone;
        var postId = N.query('post');
        if (postId) {
            var p = await N.api('/api/posts/' + encodeURIComponent(postId));
            state.anchor = parseYmd(p.local_date);
        }
        await load();
        loadAttention().catch(N.fail);
        if (postId) openPost(+postId).catch(N.fail);
        setInterval(function () { if (!dialog.open) load().catch(function () {}); }, 30000);
    })().catch(N.fail);
})();
