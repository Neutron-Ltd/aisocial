(function () {
    'use strict';
    var N = window.NEUTX, esc = N.esc;
    var $ = function (id) { return document.getElementById(id); };
    var FALLBACK_ZONES = ['UTC', 'America/Los_Angeles', 'America/New_York', 'Europe/London', 'Europe/Berlin', 'Asia/Dhaka',
        'Asia/Kolkata', 'Asia/Singapore', 'Asia/Tokyo', 'Australia/Sydney'];

    function zones(current) {
        var list = (Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : FALLBACK_ZONES).slice();
        if (list.indexOf('UTC') < 0) list.unshift('UTC');
        if (current && list.indexOf(current) < 0) list.unshift(current);
        return list;
    }

    function fillProfile(u) {
        $('f-name').value = u.name;
        $('f-email').value = u.email;
        $('f-timezone').innerHTML = zones(u.timezone).map(function (z) { return '<option>' + esc(z) + '</option>'; }).join('');
        $('f-timezone').value = u.timezone;
        $('member-since').textContent = u.email + ' · member since ' + N.date(u.created_at, { year: 'numeric', month: 'short', day: 'numeric' });
        $('pw-changed').textContent = 'Last changed ' + N.ago(u.password_changed_at);
        document.querySelectorAll('[data-user-name]').forEach(function (el) { el.textContent = u.name || u.email.split('@')[0]; });
        document.querySelectorAll('[data-user-initial]').forEach(function (el) { el.textContent = (u.name || u.email).charAt(0).toUpperCase(); });
        document.querySelectorAll('#platform-choices input').forEach(function (cb) {
            cb.checked = u.default_platforms.indexOf(cb.value) >= 0;
            cb.closest('.choice-card').classList.toggle('active', cb.checked);
        });
        $('f-time').value = u.default_time;
        $('f-hashtags').value = u.default_hashtags;
    }

    async function save(body, okMsg) {
        try {
            var u = await N.api('/api/auth/me', { method: 'PATCH', body: body });
            N.user = u;
            fillProfile(u);
            $('f-template').value = u.default_template_id || '';
            N.toast(okMsg, 'success');
        } catch (err) { N.fail(err); }
    }

    $('profile-form').addEventListener('submit', function (e) {
        e.preventDefault();
        save({ name: $('f-name').value.trim(), email: $('f-email').value.trim(), timezone: $('f-timezone').value }, 'Profile saved');
    });

    $('defaults-form').addEventListener('submit', function (e) {
        e.preventDefault();
        var platforms = Array.prototype.filter.call(document.querySelectorAll('#platform-choices input'), function (c) { return c.checked; })
            .map(function (c) { return c.value; });
        var body = { default_platforms: platforms, default_time: $('f-time').value || '15:00', default_hashtags: $('f-hashtags').value.trim() };
        var t = $('f-template').value;
        if (t) body.default_template_id = +t; else body.clear_default_template = true;
        save(body, 'Posting defaults saved');
    });
    $('platform-choices').addEventListener('change', function (e) {
        e.target.closest('.choice-card').classList.toggle('active', e.target.checked);
    });

    $('password-form').addEventListener('submit', async function (e) {
        e.preventDefault();
        var cur = $('f-pw-current').value, next = $('f-pw-new').value;
        if (next.length < 10) { N.toast('The new password needs at least 10 characters', 'error'); return; }
        try {
            await N.api('/api/auth/password', { body: { current_password: cur, new_password: next } });
            $('f-pw-current').value = $('f-pw-new').value = '';
            N.toast('Password changed. Other sessions were signed out.', 'success');
            loadSessions();
            fillProfile(await N.api('/api/auth/me'));
        } catch (err) { N.fail(err); }
    });

    function device(ua) {
        if (!ua) return 'Unknown device';
        var os = /iPhone|iPad/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Mac OS X/.test(ua) ? 'macOS' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : 'Device';
        var br = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
        return os + ' · ' + br;
    }

    async function loadSessions() {
        var list = await N.api('/api/auth/sessions');
        $('sessions').innerHTML = list.map(function (s) {
            return '<div class="flex items-center gap-4 p-3 rounded-xl bg-black/30 border border-white/5">' +
                '<div class="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center text-gray-400 shrink-0"><i data-lucide="' + (/Mobile|iPhone|Android/.test(s.user_agent) ? 'smartphone' : 'laptop') + '" class="w-5 h-5"></i></div>' +
                '<div class="flex-1 min-w-0"><p class="text-sm font-bold text-cloud truncate">' + esc(device(s.user_agent)) +
                (s.current ? ' <span class="ml-1 px-2 py-0.5 rounded-full bg-electric/10 text-electric border border-electric/30 text-[10px] font-mono uppercase">This device</span>' : '') + '</p>' +
                '<p class="text-xs text-gray-500 font-mono">Signed in ' + esc(N.date(s.created_at)) + ' · active ' + esc(N.ago(s.last_seen_at)) + '</p></div>' +
                (s.current ? '' : '<button type="button" data-revoke="' + esc(s.id) + '" class="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-300 text-xs hover:text-red-400 hover:border-red-500/30">Revoke</button>') +
                '</div>';
        }).join('');
        $('revoke-others').classList.toggle('hidden', list.length < 2);
        N.icons();
    }
    $('sessions').addEventListener('click', async function (e) {
        var b = e.target.closest('[data-revoke]');
        if (!b) return;
        try { await N.api('/api/auth/sessions/' + b.dataset.revoke, { method: 'DELETE' }); N.toast('Session revoked', 'success'); loadSessions(); }
        catch (err) { N.fail(err); }
    });
    $('revoke-others').addEventListener('click', async function () {
        if (!confirm('Sign out every other device?')) return;
        try { await N.api('/api/auth/sessions/revoke-others', { method: 'POST' }); N.toast('Other sessions signed out', 'success'); loadSessions(); }
        catch (err) { N.fail(err); }
    });

    $('delete-form').addEventListener('submit', async function (e) {
        e.preventDefault();
        var pw = $('f-delete-pw').value;
        if (!pw) { N.toast('Enter your password to confirm', 'error'); return; }
        if (!confirm('Permanently delete your NEUTX account and all of its data?')) return;
        try {
            await N.api('/api/auth/delete-account', { body: { password: pw } });
            location.href = 'index.html';
        } catch (err) { N.fail(err); }
    });

    // Highlight the section in view.
    var links = document.querySelectorAll('.section-nav-link');
    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
            if (en.isIntersecting) links.forEach(function (l) { l.classList.toggle('active', l.dataset.section === en.target.id); });
        });
    }, { root: $('settings-scroll'), rootMargin: '0px 0px -70% 0px' });
    document.querySelectorAll('section[id^="sec-"]').forEach(function (s) { observer.observe(s); });

    (async function init() {
        var user = await N.ready;
        document.querySelectorAll('[data-badge]').forEach(function (el) { el.outerHTML = N.platformBadge(el.dataset.badge, 'w-8 h-8'); });
        fillProfile(user);
        var templates = await N.api('/api/templates');
        $('f-template').innerHTML = '<option value="">None — choose every time</option>' + templates.map(function (t) {
            return '<option value="' + t.id + '">' + esc(t.name) + (t.system ? ' (System)' : '') + '</option>';
        }).join('');
        $('f-template').value = user.default_template_id || '';
        loadSessions();
        N.icons();
    })().catch(N.fail);
})();
