(function () {
    'use strict';
    var N = window.NEUTX, esc = N.esc;

    function postRow(post, today) {
        var badges = post.targets.map(function (t) { return N.platformBadge(t.platform); }).join('');
        var title = post.title || post.caption.split('\n')[0] || (post.media && post.media.original_name) || 'Untitled post';
        return '<div class="p-4 sm:p-5 border-b border-white/5 last:border-b-0 hover:bg-white/5 transition-colors flex flex-col sm:flex-row gap-4 items-start sm:items-center">' +
            '<div class="w-24 h-32 sm:w-20 sm:h-28 flex-shrink-0 rounded-xl border border-white/10 overflow-hidden">' + N.thumb(post.media, 'w-full h-full') + '</div>' +
            '<div class="flex-1 min-w-0">' +
            '<div class="flex items-center gap-2 mb-1.5 flex-wrap">' + badges + N.statusPill(post.status) + '</div>' +
            '<h4 class="text-white font-semibold truncate mb-1">' + esc(title) + '</h4>' +
            '<p class="text-sm text-gray-500 truncate mb-2">' + esc(post.caption || 'No caption') + '</p>' +
            '<div class="text-xs font-medium text-gray-400 flex items-center gap-1.5"><i data-lucide="calendar" class="w-3.5 h-3.5"></i> ' +
            esc(N.whenLabel(post.local_date, post.local_time, today)) + '</div></div>' +
            (post.status === 'scheduled'
                ? '<div class="flex sm:flex-col gap-2 w-full sm:w-auto mt-2 sm:mt-0 border-t sm:border-t-0 border-white/5 pt-3 sm:pt-0">' +
                  '<a href="calendar.html?post=' + post.id + '" class="flex-1 sm:flex-none p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors border border-white/5 flex justify-center" title="Edit post"><i data-lucide="edit-3" class="w-4 h-4"></i></a>' +
                  '<button type="button" data-cancel="' + post.id + '" class="flex-1 sm:flex-none p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-red-400 transition-colors border border-white/5 flex justify-center" title="Cancel scheduled post"><i data-lucide="trash-2" class="w-4 h-4"></i></button></div>'
                : '') +
            '</div>';
    }

    function jobRow(job) {
        var label = { queued: job.error ? job.error : 'Queued', submitted: 'Queued in ComfyUI', running: 'Rendering...' }[job.status] || job.status;
        return '<a href="studio.html?job=' + job.id + '" class="p-4 sm:p-5 border-b border-white/5 hover:bg-white/5 transition-colors flex gap-4 items-center">' +
            '<div class="w-20 h-20 flex-shrink-0 rounded-xl bg-gray-900 border border-electric/30 relative flex items-center justify-center">' +
            '<i data-lucide="cpu" class="w-6 h-6 text-electric animate-pulse"></i></div>' +
            '<div class="flex-1 min-w-0"><span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-electric/10 text-electric border border-electric/20 text-xs font-medium mb-1.5">' +
            '<i data-lucide="loader-2" class="w-3 h-3 animate-spin"></i> ' + esc(label) + '</span>' +
            '<h4 class="text-white font-semibold truncate">' + esc(job.prompt) + '</h4>' +
            '<p class="text-sm text-gray-500 truncate">' + esc((job.params.template_name || '') + ' · ' + (job.params.engine || '')) + '</p></div></a>';
    }

    function bar(label, used, total, gradient) {
        var pct = total ? Math.round(used / total * 100) : 0;
        return '<div><div class="flex justify-between text-xs font-medium mb-1"><span class="text-gray-300">' + esc(label) + '</span>' +
            '<span class="text-white">' + (used / 2 ** 30).toFixed(1) + ' / ' + (total / 2 ** 30).toFixed(0) + ' GB</span></div>' +
            '<div class="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden"><div class="h-full ' + gradient + '" style="width:' + pct + '%"></div></div></div>';
    }

    async function loadHardware() {
        var box = document.getElementById('hardware');
        var status = document.getElementById('station-status');
        try {
            var c = await N.api('/api/system/comfyui');
            if (!c.online) {
                status.textContent = 'ComfyUI is offline — generations will wait until it is reachable.';
                box.innerHTML = '<div class="flex items-start gap-2 text-red-300"><i data-lucide="alert-triangle" class="w-4 h-4 mt-0.5 shrink-0"></i><p>' +
                    esc(c.error || 'ComfyUI is not reachable') + '</p></div><a href="connections.html" class="text-xs text-electric">Check the endpoint</a>';
            } else {
                status.textContent = 'Your AI rendering station is online and ready.';
                var html = (c.devices || []).map(function (d) {
                    return d.vram_total ? bar('GPU VRAM (' + d.name + ')', d.vram_total - d.vram_free, d.vram_total, 'bg-gradient-to-r from-electric to-goldlight') : '';
                }).join('');
                if (c.ram_total) html += bar('System RAM', c.ram_total - c.ram_free, c.ram_total, 'bg-electric');
                var q = c.queue_running + c.queue_pending;
                html += '<div class="pt-4 border-t border-white/5 text-xs text-gray-500 flex items-start gap-2"><i data-lucide="info" class="w-4 h-4 flex-shrink-0 mt-0.5"></i><p>' +
                    (q ? 'ComfyUI has ' + q + ' job' + (q > 1 ? 's' : '') + ' in its queue.' : 'ComfyUI is idle and ready for a new job.') +
                    ' Version ' + esc(c.version || '?') + '.</p></div>';
                box.innerHTML = html;
            }
        } catch (e) {
            box.textContent = e.message;
        }
        N.icons();
    }

    async function load() {
        await N.ready;
        var results = await Promise.all([N.api('/api/dashboard'), N.api('/api/jobs?active=true')]);
        var d = results[0], jobs = results[1], s = d.stats;
        document.getElementById('today-label').textContent = new Date(d.today + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

        document.getElementById('stat-scheduled').textContent = s.scheduled_next_7_days;
        document.getElementById('stat-scheduled-sub').textContent = s.scheduled_total + ' scheduled in total · ' + s.published_last_7_days + ' published this week';
        document.getElementById('stat-generated').textContent = s.generated_last_7_days;
        document.getElementById('stat-generated-sub').innerHTML = s.active_jobs
            ? '<i data-lucide="loader-2" class="w-3 h-3 animate-spin text-electric"></i> ' + s.active_jobs + ' rendering now'
            : '<a href="studio.html" class="text-electric hover:text-goldlight">Start a new generation</a>';
        document.getElementById('stat-accounts').textContent = s.connected_accounts;
        var accounts = await N.api('/api/accounts');
        document.getElementById('stat-accounts-sub').innerHTML = accounts.length
            ? '<div class="flex gap-2">' + accounts.map(function (a) { return N.platformBadge(a.platform); }).join('') + '</div>'
            : '<a href="connections.html" class="text-electric hover:text-goldlight">Connect your first account</a>';

        var banner = document.getElementById('failed-banner');
        if (s.failed_posts) {
            banner.className = 'flex items-center justify-between gap-4 px-5 py-4 rounded-2xl border border-red-500/30 bg-red-500/10 text-red-200 text-sm';
            banner.innerHTML = '<span class="flex items-center gap-2"><i data-lucide="alert-triangle" class="w-4 h-4"></i>' + s.failed_posts +
                ' post' + (s.failed_posts > 1 ? 's' : '') + ' failed to publish on at least one platform.</span><a href="calendar.html?status=failed" class="font-semibold underline">Review</a>';
        }

        var queue = document.getElementById('queue');
        var rows = jobs.map(jobRow).concat(d.upcoming.map(function (p) { return postRow(p, d.today); }));
        queue.innerHTML = rows.length ? rows.join('')
            : '<div class="p-8 text-center text-gray-500"><i data-lucide="calendar-plus" class="w-8 h-8 mx-auto mb-3 text-gray-600"></i>' +
              '<p class="text-sm">Nothing scheduled yet. Generate something in the Studio and schedule it.</p></div>';

        var tpl = document.getElementById('templates');
        tpl.innerHTML = d.templates.length ? d.templates.map(function (t) {
            var info = t.workflow_info || {};
            return '<a href="template.html?id=' + t.id + '" class="flex items-center gap-3 p-2 rounded-xl hover:bg-white/5 transition-colors">' +
                '<div class="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center text-gray-400"><i data-lucide="' + (info.kind === 'image' ? 'image' : 'film') + '" class="w-4 h-4"></i></div>' +
                '<div class="min-w-0"><p class="text-sm font-medium text-white truncate">' + esc(t.name) + '</p>' +
                '<p class="text-[10px] text-gray-500">' + esc((info.engine || t.workflow) + ' • ' + t.aspect) + '</p></div></a>';
        }).join('') : '<a href="template.html" class="block text-sm text-gray-500 hover:text-white p-2">No custom templates yet — create one</a>';
        N.icons();
        if (jobs.length) setTimeout(load, 5000);
    }

    document.getElementById('queue').addEventListener('click', async function (e) {
        var btn = e.target.closest('[data-cancel]');
        if (!btn || !confirm('Cancel this scheduled post?')) return;
        try {
            await N.api('/api/posts/' + btn.dataset.cancel, { method: 'DELETE' });
            N.toast('Post cancelled', 'success');
            load();
        } catch (err) { N.fail(err); }
    });

    load().catch(N.fail);
    loadHardware();
})();
