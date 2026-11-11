/**
 * NEUTX WebUI — shared client: API calls, auth guard, header user, helpers.
 * Every value from the server is inserted with textContent or escaped via esc().
 */
(function () {
    'use strict';

    var NEUTX = window.NEUTX || {};
    window.NEUTX = NEUTX;

    function ApiError(status, message) {
        this.status = status;
        this.message = message;
    }
    ApiError.prototype = Object.create(Error.prototype);
    NEUTX.ApiError = ApiError;

    /** fetch wrapper. opts: {method, body (object → JSON), form (FormData), raw (return Response)} */
    NEUTX.api = async function (path, opts) {
        opts = opts || {};
        var headers = { 'X-NEUTX': '1', 'Accept': 'application/json' };
        var body;
        if (opts.form) {
            body = opts.form;
        } else if (opts.body !== undefined) {
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(opts.body);
        }
        var res;
        try {
            res = await fetch(path, { method: opts.method || (body ? 'POST' : 'GET'), headers: headers, body: body, credentials: 'same-origin' });
        } catch (e) {
            throw new ApiError(0, 'Cannot reach the NEUTX server. Is it running?');
        }
        if (res.status === 401 && !opts.allow401) {
            var here = location.pathname.split('/').pop() || 'dashboard.html';
            location.href = 'auth.html?mode=login&next=' + encodeURIComponent(here + location.search);
            throw new ApiError(401, 'Please sign in');
        }
        if (opts.raw) return res;
        var data = null;
        if (res.status !== 204) {
            try { data = await res.json(); } catch (e) { data = null; }
        }
        if (!res.ok) {
            var msg = data && data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : ('Request failed (' + res.status + ')');
            throw new ApiError(res.status, msg);
        }
        return data;
    };

    NEUTX.esc = function (value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    };

    NEUTX.icons = function () {
        if (window.lucide) window.lucide.createIcons();
    };

    // ------------------------------------------------------------------ toasts
    NEUTX.toast = function (message, kind) {
        var host = document.getElementById('neutx-toasts');
        if (!host) {
            host = document.createElement('div');
            host.id = 'neutx-toasts';
            host.setAttribute('role', 'status');
            host.setAttribute('aria-live', 'polite');
            host.className = 'fixed bottom-24 md:bottom-6 right-4 left-4 md:left-auto z-[100] flex flex-col gap-2 items-end pointer-events-none';
            document.body.appendChild(host);
        }
        var el = document.createElement('div');
        var tone = kind === 'error' ? 'border-red-500/40 text-red-300' : kind === 'success' ? 'border-emerald-500/40 text-emerald-300' : 'border-electric/40 text-cloud';
        el.className = 'pointer-events-auto glass-panel max-w-sm w-full md:w-auto px-4 py-3 rounded-xl text-sm shadow-2xl border ' + tone;
        el.textContent = message;
        host.appendChild(el);
        setTimeout(function () { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; }, kind === 'error' ? 6000 : 3500);
        setTimeout(function () { el.remove(); }, kind === 'error' ? 6400 : 3900);
    };
    NEUTX.fail = function (err) {
        if (err && err.status === 401) return;
        NEUTX.toast((err && err.message) || 'Something went wrong', 'error');
    };

    // ------------------------------------------------------------------ formatting
    NEUTX.platforms = {
        tiktok: { label: 'TikTok', icon: 'music-2', tone: 'text-white', bg: 'bg-black border border-white/20' },
        instagram: { label: 'Instagram', icon: 'camera', tone: 'text-pink-300', bg: 'bg-gradient-to-tr from-yellow-500 via-pink-500 to-purple-600' },
        youtube: { label: 'YouTube', icon: 'play', tone: 'text-red-300', bg: 'bg-red-600' },
        x: { label: 'X', icon: 'at-sign', tone: 'text-gray-200', bg: 'bg-gray-900 border border-white/20' }
    };
    NEUTX.platformBadge = function (key, size) {
        var p = NEUTX.platforms[key] || { label: key, icon: 'globe', bg: 'bg-gray-700' };
        var s = size || 'w-6 h-6';
        return '<span title="' + NEUTX.esc(p.label) + '" class="' + s + ' rounded-lg ' + p.bg + ' inline-flex items-center justify-center text-white shrink-0">' +
            '<i data-lucide="' + p.icon + '" class="w-3.5 h-3.5"></i></span>';
    };

    NEUTX.bytes = function (n) {
        if (!n) return '0 B';
        var u = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
        return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + ' ' + u[i];
    };
    NEUTX.date = function (iso, opts) {
        return new Date(iso).toLocaleDateString(undefined, opts || { month: 'short', day: 'numeric' });
    };
    NEUTX.ago = function (iso) {
        var s = (Date.now() - new Date(iso).getTime()) / 1000;
        if (s < 60) return 'just now';
        if (s < 3600) return Math.floor(s / 60) + 'm ago';
        if (s < 86400) return Math.floor(s / 3600) + 'h ago';
        if (s < 86400 * 30) return Math.floor(s / 86400) + 'd ago';
        return NEUTX.date(iso);
    };
    /** "2026-11-12" + "15:00" (already in the user's zone) → "Today at 3:00 PM" style text. */
    NEUTX.whenLabel = function (localDate, localTime, today) {
        var hm = localTime.split(':');
        var t = new Date(2000, 0, 1, +hm[0], +hm[1]).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
        var d0 = new Date(today + 'T00:00:00'), d1 = new Date(localDate + 'T00:00:00');
        var diff = Math.round((d1 - d0) / 86400000);
        var day = diff === 0 ? 'Today' : diff === 1 ? 'Tomorrow' : diff === -1 ? 'Yesterday'
            : (diff > 1 && diff < 7) ? d1.toLocaleDateString(undefined, { weekday: 'long' })
            : d1.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        return day + ' at ' + t;
    };
    NEUTX.statusPill = function (status) {
        var map = {
            scheduled: 'bg-electric/10 text-electric border-electric/20',
            publishing: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
            published: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
            partial: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30',
            failed: 'bg-red-500/10 text-red-300 border-red-500/30',
            pending: 'bg-white/5 text-gray-300 border-white/10'
        };
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider ' +
            (map[status] || map.pending) + '">' + NEUTX.esc(status) + '</span>';
    };
    /** <img>/<video> preview for a media object ({id, kind, url}). */
    NEUTX.thumb = function (media, cls) {
        if (!media) return '<div class="' + (cls || '') + ' bg-gray-900"></div>';
        var c = (cls || '') + ' object-cover bg-black';
        return media.kind === 'video'
            ? '<video src="' + NEUTX.esc(media.url) + '#t=0.5" class="' + c + '" muted playsinline preload="metadata"></video>'
            : '<img src="' + NEUTX.esc(media.url) + '" alt="" loading="lazy" class="' + c + '">';
    };
    NEUTX.query = function (name) {
        return new URLSearchParams(location.search).get(name);
    };

    // ------------------------------------------------------------------ session
    NEUTX.signOut = async function () {
        try { await NEUTX.api('/api/auth/logout', { method: 'POST', allow401: true }); } catch (e) { /* ignore */ }
        location.href = 'auth.html?mode=login';
    };

    /** Loads the signed-in user (redirects to sign-in when needed) and fills the header. */
    NEUTX.ready = (async function () {
        if (document.body && document.body.dataset.public === 'true') return null;
        var user = await NEUTX.api('/api/auth/me');
        NEUTX.user = user;
        var display = user.name || user.email.split('@')[0];
        document.querySelectorAll('[data-user-name]').forEach(function (el) { el.textContent = display; });
        document.querySelectorAll('[data-user-initial]').forEach(function (el) { el.textContent = display.charAt(0).toUpperCase(); });
        return user;
    })();
    NEUTX.ready.catch(function () { /* redirect already handled */ });

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-action="sign-out"]');
        if (btn) { e.preventDefault(); NEUTX.signOut(); }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target.matches('[data-global-search]')) {
            var q = e.target.value.trim();
            location.href = 'media.html' + (q ? '?q=' + encodeURIComponent(q) : '');
        }
    });
})();
