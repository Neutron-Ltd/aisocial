(function () {
    'use strict';
    var N = window.NEUTX, esc = N.esc;
    var ENV = { tiktok: 'TIKTOK', instagram: 'INSTAGRAM', youtube: 'YOUTUBE', x: 'X' };
    var DESC = {
        tiktok: 'Direct Post of videos. Unaudited TikTok apps can only post privately.',
        instagram: 'Reels and single-image posts (professional accounts).',
        youtube: 'Video uploads to your channel (private by default).',
        x: 'Posts with a video or image (280 characters).'
    };

    function tokenState(a) {
        if (!a.expires_at) return ['check-circle-2', 'text-electric', 'Token valid'];
        var left = (new Date(a.expires_at) - Date.now()) / 1000;
        if (left > 0 && left < 7 * 86400) return ['clock', 'text-yellow-300', 'Token expires ' + new Date(a.expires_at).toLocaleDateString()];
        if (left <= 0 && !a.has_refresh_token) return ['alert-triangle', 'text-red-300', 'Token expired — reconnect'];
        return ['check-circle-2', 'text-electric', a.has_refresh_token ? 'Auto-refreshes' : 'Token valid'];
    }

    function platformCard(p, accounts) {
        var meta = N.platforms[p.key];
        var rows = accounts.map(function (a) {
            var t = tokenState(a);
            return '<div class="flex flex-col sm:flex-row sm:items-center gap-3 justify-between p-3 rounded-xl bg-black/30 border border-white/5">' +
                '<div class="min-w-0"><p class="text-sm text-cloud truncate">@' + esc(a.username || a.external_id) + '</p>' +
                '<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] font-mono uppercase tracking-wider text-gray-500 mt-1">' +
                '<span class="flex items-center gap-1"><i data-lucide="link" class="w-3 h-3"></i> Connected ' + esc(N.ago(a.created_at)) + '</span>' +
                '<span class="flex items-center gap-1"><i data-lucide="send" class="w-3 h-3"></i> ' + a.published_count + ' posts via NEUTX</span>' +
                '<span class="flex items-center gap-1 ' + t[1] + '"><i data-lucide="' + t[0] + '" class="w-3 h-3"></i> ' + esc(t[2]) + '</span></div></div>' +
                '<button type="button" data-disconnect="' + a.id + '" data-name="' + esc(meta.label + ' @' + (a.username || '')) + '" class="px-3 py-1.5 rounded-lg bg-red-500/5 border border-red-500/20 text-red-400 text-xs font-semibold hover:bg-red-500/15 transition-colors flex items-center gap-1.5 shrink-0"><i data-lucide="log-out" class="w-3.5 h-3.5"></i> Disconnect</button></div>';
        }).join('');
        var status = accounts.length
            ? '<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/30 text-[10px] font-mono uppercase tracking-wider"><i data-lucide="check" class="w-3 h-3"></i> Connected</span>'
            : p.configured ? '' : '<span class="px-2 py-0.5 rounded-full bg-white/5 text-gray-400 border border-white/10 text-[10px] font-mono uppercase tracking-wider">Not configured</span>';
        var action = p.configured
            ? '<button type="button" data-connect="' + esc(p.key) + '" class="gold-cta px-4 py-2 rounded-xl text-sm shrink-0">' + (accounts.length ? 'Connect another' : 'Connect') + '</button>'
            : '';
        var help = p.configured ? '' : '<p class="text-xs text-gray-500 mt-3">To enable ' + esc(meta.label) + ', create a developer app and set <code class="text-gray-300">' + ENV[p.key] + '_CLIENT_ID</code> and <code class="text-gray-300">' + ENV[p.key] +
            '_CLIENT_SECRET</code> on the server, with redirect URI <code class="text-gray-300 break-all">' + esc(location.origin + '/api/oauth/' + p.key + '/callback') + '</code>. See the README.</p>';
        var warn = p.warning ? '<p class="text-xs text-yellow-300 mt-3 flex items-start gap-1.5"><i data-lucide="alert-triangle" class="w-3.5 h-3.5 shrink-0 mt-0.5"></i>' + esc(p.warning) + '</p>' : '';
        return '<div class="glass-panel rounded-2xl p-5">' +
            '<div class="flex flex-col sm:flex-row sm:items-center gap-4"><div class="flex items-center gap-4 flex-1 min-w-0">' + N.platformBadge(p.key, 'w-14 h-14 !rounded-2xl') +
            '<div class="min-w-0"><div class="flex items-center gap-2 mb-1"><h3 class="text-base font-bold text-cloud">' + esc(meta.label) + '</h3>' + status + '</div>' +
            '<p class="text-sm text-gray-400">' + esc(DESC[p.key]) + '</p></div></div>' + action + '</div>' +
            help + warn + (rows ? '<div class="space-y-2 mt-4">' + rows + '</div>' : '') + '</div>';
    }

    async function loadPlatforms() {
        var r = await Promise.all([N.api('/api/platforms'), N.api('/api/accounts')]);
        var accounts = r[1];
        document.getElementById('active-count').textContent = accounts.length + ' Active';
        document.getElementById('platforms').innerHTML = r[0].map(function (p) {
            return platformCard(p, accounts.filter(function (a) { return a.platform === p.key; }));
        }).join('');
        N.icons();
    }

    function gb(n) { return (n / 2 ** 30).toFixed(1); }

    async function loadComfy() {
        var box = document.getElementById('comfy'), pill = document.getElementById('system-pill');
        box.innerHTML = 'Checking ComfyUI...';
        var c;
        try { c = await N.api('/api/system/comfyui?models=true'); } catch (e) { box.textContent = e.message; return; }
        var online = c.online;
        pill.className = 'flex items-center gap-2 px-4 py-2 rounded-xl border ' + (online ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30');
        pill.innerHTML = '<span class="w-2 h-2 rounded-full ' + (online ? 'bg-green-500 animate-pulse' : 'bg-red-500') + '"></span>' +
            '<span class="text-xs font-mono uppercase tracking-wider font-semibold ' + (online ? 'text-green-400' : 'text-red-400') + '">' + (online ? 'Renderer online' : 'Renderer offline') + '</span>';
        box.className = 'glass-panel rounded-2xl p-6 border-l-[3px] ' + (online ? 'border-l-green-500' : 'border-l-red-500');
        var head = '<div class="flex items-start gap-4 mb-5"><div class="w-14 h-14 rounded-2xl bg-electric/10 border border-electric/30 flex items-center justify-center shrink-0"><i data-lucide="server" class="w-7 h-7 text-electric"></i></div>' +
            '<div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2 mb-1"><h3 class="text-base font-bold text-cloud">ComfyUI</h3>' +
            '<span class="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider border ' + (online ? 'bg-green-500/10 text-green-400 border-green-500/30">Online' : 'bg-red-500/10 text-red-400 border-red-500/30">Offline') + '</span></div>' +
            '<code class="font-mono text-xs text-cloud break-all">' + esc(c.url) + '</code>' +
            '<p class="text-xs text-gray-500 mt-1">Set with the <code>COMFYUI_URL</code> environment variable on the NEUTX server.</p></div></div>';
        if (!online) {
            box.innerHTML = head + '<p class="text-sm text-red-300">' + esc(c.error || 'Not reachable') + '</p>' +
                '<p class="text-xs text-gray-500 mt-2">Start ComfyUI (see README) or point COMFYUI_URL at your GPU machine. Queued generations start automatically once it is reachable.</p>';
            N.icons();
            return;
        }
        var stats = (c.devices || []).map(function (d) {
            return stat('VRAM · ' + d.name, d.vram_total ? gb(d.vram_total - d.vram_free) + ' / ' + gb(d.vram_total) + ' GB' : d.type);
        }).join('') + (c.ram_total ? stat('System RAM', gb(c.ram_total - c.ram_free) + ' / ' + gb(c.ram_total) + ' GB') : '') +
            stat('Queue', c.queue_running + ' running · ' + c.queue_pending + ' pending') + stat('Version', c.version || '?');
        var wf = (c.workflows || []).map(function (w) {
            return '<li class="flex items-start gap-2 text-xs"><i data-lucide="' + (w.ready ? 'check-circle-2' : 'alert-triangle') + '" class="w-3.5 h-3.5 shrink-0 mt-0.5 ' + (w.ready ? 'text-emerald-400' : 'text-yellow-300') + '"></i>' +
                '<span><span class="text-cloud">' + esc(w.name) + '</span>' + (w.ready ? '' : ' <span class="text-gray-500">— missing ' + esc(w.missing.join(', ')) + '</span>') + '</span></li>';
        }).join('');
        box.innerHTML = head + '<div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">' + stats + '</div>' +
            '<p class="mono-label mb-2">Workflows</p><ul class="space-y-1.5">' + wf + '</ul>';
        N.icons();
    }

    function stat(label, value) {
        return '<div class="rounded-xl bg-black/30 border border-white/5 p-3"><p class="mono-label mb-1">' + esc(label) + '</p><p class="text-sm font-semibold text-cloud">' + esc(value) + '</p></div>';
    }

    document.getElementById('platforms').addEventListener('click', async function (e) {
        var c = e.target.closest('[data-connect]'), d = e.target.closest('[data-disconnect]');
        try {
            if (c) {
                c.disabled = true;
                var res = await N.api('/api/oauth/' + c.dataset.connect + '/start', { body: { return_to: 'connections.html' } });
                location.href = res.url;
            } else if (d) {
                if (!confirm('Disconnect ' + d.dataset.name + '? Scheduled posts to this account will fail until you reconnect. To fully revoke access, also remove NEUTX in the platform\'s app settings.')) return;
                await N.api('/api/accounts/' + d.dataset.disconnect, { method: 'DELETE' });
                N.toast('Account disconnected', 'success');
                loadPlatforms();
            }
        } catch (err) { N.fail(err); if (c) c.disabled = false; }
    });
    document.getElementById('retest').addEventListener('click', loadComfy);

    (async function init() {
        await N.ready;
        var connected = N.query('connected'), error = N.query('error');
        if (connected) N.toast((N.platforms[connected] || { label: connected }).label + ' connected', 'success');
        if (error) N.toast(error, 'error');
        if (connected || error) history.replaceState(null, '', 'connections.html');
        await loadPlatforms();
        loadComfy();
    })().catch(N.fail);
})();
