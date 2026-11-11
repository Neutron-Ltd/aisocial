(function () {
    'use strict';
    var N = window.NEUTX, esc = N.esc;
    var state = {
        templates: [], platforms: {}, accounts: [], tab: 'system',
        template: null, heroMediaId: null, job: null, media: null, pollTimer: null, lastStatus: null, fromStep: 3
    };
    var ASPECT_LABEL = { '9:16': '9:16 Vertical', '1:1': '1:1 Square', '16:9': '16:9 Landscape' };

    // ------------------------------------------------------------------ wizard
    function goTo(step) {
        document.querySelectorAll('.wizard-step').forEach(function (el) { el.classList.remove('active'); });
        document.getElementById('step-' + step).classList.add('active');
        document.getElementById('progress-line').style.width = { 1: '0%', 2: '33%', 3: '66%', 4: '100%' }[step];
        for (var i = 1; i <= 4; i++) {
            var ind = document.getElementById('ind-' + i), dot = ind.firstElementChild, text = ind.lastElementChild;
            var base = 'w-10 h-10 rounded-full flex items-center justify-center font-bold border-4 border-[#0F0F0F] transition-all ';
            var tbase = 'text-xs font-mono uppercase tracking-wider absolute -bottom-6 whitespace-nowrap ';
            if (i < step) {
                dot.className = base + 'bg-goldlight text-obsidian';
                dot.innerHTML = '<i data-lucide="check" class="w-5 h-5"></i>';
                text.className = tbase + 'font-semibold text-goldlight';
            } else if (i === step) {
                dot.className = base + 'bg-electric text-obsidian shadow-[0_0_15px_rgba(229,185,108,0.5)]';
                dot.textContent = i;
                text.className = tbase + 'font-semibold text-electric';
            } else {
                dot.className = base + 'bg-gray-800 text-gray-400';
                dot.textContent = i;
                text.className = tbase + 'font-medium text-gray-500';
            }
        }
        N.icons();
        document.querySelector('main').scrollTo({ top: 0, behavior: 'smooth' });
    }
    document.addEventListener('click', function (e) {
        var g = e.target.closest('[data-goto]');
        if (!g) return;
        var step = +g.dataset.goto;
        if (step === 4) openSchedule(state.media, 3); else goTo(step);
    });

    // ------------------------------------------------------------------ step 1: templates
    function renderTemplates() {
        document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.toggle('active', b.dataset.tab === state.tab); });
        var list = state.templates.filter(function (t) { return state.tab === 'system' ? t.system : !t.system; });
        var grid = document.getElementById('template-grid');
        if (!list.length) {
            grid.innerHTML = '<a href="template.html" class="glass-panel p-6 rounded-2xl flex flex-col items-center justify-center text-center gap-3 text-gray-400 hover:text-white hover:border-electric/50 min-h-[14rem]">' +
                '<i data-lucide="plus-circle" class="w-8 h-8"></i><span class="font-semibold">Create your first template</span></a>';
            N.icons();
            return;
        }
        grid.innerHTML = list.map(function (t) {
            var info = t.workflow_info;
            var icon = !info ? 'alert-triangle' : info.kind === 'image' ? 'image' : t.aspect === '9:16' ? 'smartphone' : 'film';
            var badge = !info ? '<span class="text-xs text-red-400">Workflow missing</span>'
                : '<span class="text-xs font-mono text-gray-500">' + esc(info.engine) + ' · ' + esc(t.aspect) + '</span>';
            return '<div role="button" tabindex="0" data-template="' + t.id + '" class="glass-panel p-6 rounded-2xl flex flex-col h-full hover:border-electric/50 transition-all group cursor-pointer' + (info ? '' : ' opacity-50 pointer-events-none') + '">' +
                '<div class="w-12 h-12 rounded-xl bg-electric/10 flex items-center justify-center mb-4 border border-electric/20 group-hover:scale-110 transition-transform"><i data-lucide="' + icon + '" class="w-6 h-6 text-electric"></i></div>' +
                '<h3 class="text-lg font-bold text-white mb-2">' + esc(t.name) + '</h3>' +
                '<p class="text-sm text-gray-400 mb-6 flex-1">' + esc(t.description || (info && info.description) || '') + '</p>' +
                '<div class="flex items-center justify-between border-t border-white/10 pt-4 mt-auto gap-2">' + badge +
                (t.system ? '' : '<a href="template.html?id=' + t.id + '" data-stop class="text-xs text-gray-400 hover:text-white">Edit</a>') +
                '<span class="text-sm text-electric font-bold group-hover:translate-x-1 transition-transform flex items-center gap-1">Select <i data-lucide="arrow-right" class="w-4 h-4"></i></span></div></div>';
        }).join('');
        N.icons();
    }

    document.querySelectorAll('.tab-btn').forEach(function (b) {
        b.addEventListener('click', function () { state.tab = b.dataset.tab; renderTemplates(); });
    });
    document.getElementById('template-grid').addEventListener('click', function (e) {
        if (e.target.closest('[data-stop]')) return;
        var card = e.target.closest('[data-template]');
        if (card) chooseTemplate(+card.dataset.template);
    });
    document.getElementById('template-grid').addEventListener('keydown', function (e) {
        var card = e.target.closest('[data-template]');
        if (card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); chooseTemplate(+card.dataset.template); }
    });

    // ------------------------------------------------------------------ step 2: content
    function chooseTemplate(id) {
        var t = state.templates.find(function (x) { return x.id === id; });
        if (!t || !t.workflow_info) return;
        state.template = t;
        var info = t.workflow_info;
        document.getElementById('chosen-template').textContent = t.name;
        document.getElementById('chosen-engine').textContent = info.engine;
        var needsHero = info.image_input !== 'none';
        document.getElementById('hero-section').classList.toggle('hidden', !needsHero);
        document.getElementById('no-hero-note').classList.toggle('hidden', needsHero);
        document.getElementById('hero-required').textContent = info.image_input === 'required' ? '(required for this template)' : '(optional)';
        document.getElementById('style-note').textContent = t.style_prompt ? 'Style added to your prompt: "' + t.style_prompt + '"' : '';
        var aspect = document.getElementById('aspect');
        aspect.innerHTML = info.aspects.map(function (a) { return '<option value="' + esc(a) + '">' + esc(ASPECT_LABEL[a] || a) + '</option>'; }).join('');
        aspect.value = t.aspect;
        document.getElementById('length-field').classList.toggle('hidden', !info.lengths.length);
        document.getElementById('generate-label').textContent = info.kind === 'image' ? 'Generate Image' : 'Generate Video';
        goTo(2);
        document.getElementById('prompt').focus();
    }

    function setHero(media) {
        state.heroMediaId = media ? media.id : null;
        var img = document.getElementById('hero-preview');
        img.classList.toggle('hidden', !media);
        document.getElementById('hero-empty').classList.toggle('invisible', !!media);
        document.getElementById('hero-remove').classList.toggle('hidden', !media);
        if (media) img.src = media.url;
    }

    async function uploadHero(file) {
        if (!file) return;
        if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { N.toast('Choose a PNG, JPG or WEBP image', 'error'); return; }
        var fd = new FormData();
        fd.append('files', file);
        var drop = document.getElementById('hero-drop');
        drop.classList.add('opacity-60');
        try {
            var res = await N.api('/api/media', { form: fd });
            setHero(res.items[0]);
        } catch (err) { N.fail(err); } finally { drop.classList.remove('opacity-60'); }
    }

    var drop = document.getElementById('hero-drop'), heroInput = document.getElementById('hero-input');
    drop.addEventListener('click', function (e) { if (!e.target.closest('#hero-remove')) heroInput.click(); });
    drop.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); heroInput.click(); } });
    heroInput.addEventListener('change', function () { uploadHero(heroInput.files[0]); heroInput.value = ''; });
    ['dragenter', 'dragover'].forEach(function (ev) {
        drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('border-electric'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
        drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('border-electric'); });
    });
    drop.addEventListener('drop', function (e) { uploadHero(e.dataTransfer.files[0]); });
    document.getElementById('hero-remove').addEventListener('click', function (e) { e.stopPropagation(); setHero(null); });

    document.getElementById('content-form').addEventListener('submit', function (e) {
        e.preventDefault();
        startJob();
    });
    document.getElementById('retry-btn').addEventListener('click', startJob);
    document.getElementById('regenerate-btn').addEventListener('click', startJob);

    async function startJob() {
        var t = state.template, prompt = document.getElementById('prompt').value.trim();
        if (!t) { goTo(1); return; }
        if (!prompt) { goTo(2); N.toast('Write a prompt first', 'error'); document.getElementById('prompt').focus(); return; }
        if (t.workflow_info.image_input === 'required' && !state.heroMediaId) { goTo(2); N.toast('This template needs a hero image', 'error'); return; }
        var body = {
            template_id: t.id, prompt: prompt,
            quality: document.getElementById('quality').value,
            aspect: document.getElementById('aspect').value
        };
        if (t.workflow_info.lengths.length) body.length = document.getElementById('length').value;
        if (state.heroMediaId && t.workflow_info.image_input !== 'none') body.image_media_id = state.heroMediaId;
        var btn = document.getElementById('generate-btn');
        btn.disabled = true;
        try {
            var job = await N.api('/api/jobs', { body: body });
            history.replaceState(null, '', 'studio.html?job=' + job.id);
            watchJob(job);
        } catch (err) { N.fail(err); } finally { btn.disabled = false; }
    }

    // ------------------------------------------------------------------ step 3: progress
    function log(text, cls) {
        var line = document.createElement('span');
        line.textContent = '> ' + text;
        if (cls) line.className = cls;
        var box = document.getElementById('terminal-logs');
        box.appendChild(line);
        box.parentElement.scrollTop = box.parentElement.scrollHeight;
    }

    function showState(which) {
        ['rendering-state', 'failed-state', 'ready-state'].forEach(function (id) {
            document.getElementById(id).classList.toggle('hidden', id !== which);
        });
    }

    function watchJob(job) {
        clearTimeout(state.pollTimer);
        state.job = job;
        state.lastStatus = null;
        document.getElementById('terminal-logs').textContent = '';
        log('Job #' + job.id + ' created · ' + (job.params.engine || job.workflow) + ' · ' + job.params.width + '×' + job.params.height);
        showState('rendering-state');
        goTo(3);
        update(job);
    }

    var PHASES = {
        queued: ['Queued', 'Waiting to be sent to ComfyUI.', 10],
        submitted: ['Queued in ComfyUI', 'ComfyUI has accepted the workflow and will start it shortly.', 30],
        running: ['Rendering...', 'ComfyUI is sampling your generation. Video can take several minutes.', 60]
    };

    function update(job) {
        state.job = job;
        var elapsed = Math.max(0, Math.round((Date.now() - new Date(job.created_at).getTime()) / 1000));
        document.getElementById('render-elapsed').textContent = elapsed < 60 ? elapsed + 's' : Math.floor(elapsed / 60) + 'm ' + (elapsed % 60) + 's';
        if (job.status !== state.lastStatus) {
            state.lastStatus = job.status;
            if (PHASES[job.status]) log(PHASES[job.status][0]);
        }
        if (job.status === 'succeeded') {
            log('Done — ' + job.outputs.length + ' file(s) saved to your Media Library', 'text-goldlight');
            showReady(job);
            return;
        }
        if (job.status === 'failed') {
            log('Failed: ' + job.error, 'text-red-400');
            document.getElementById('failed-reason').textContent = job.error || 'Unknown error';
            showState('failed-state');
            N.icons();
            return;
        }
        var p = PHASES[job.status] || PHASES.queued;
        document.getElementById('render-title').textContent = p[0];
        document.getElementById('render-desc').textContent = job.error && job.status === 'queued' ? job.error : p[1];
        document.getElementById('render-phase').textContent = p[0];
        // Progress isn't reported per step; ease towards the phase ceiling while waiting.
        var bar = document.getElementById('render-bar');
        var cur = parseFloat(bar.style.width) || 5;
        bar.style.width = Math.min(p[2] + 25, Math.max(cur, p[2]) + 2) + '%';
        state.pollTimer = setTimeout(async function () {
            try { update(await N.api('/api/jobs/' + job.id)); } catch (err) { N.fail(err); state.pollTimer = setTimeout(function () { update(job); }, 5000); }
        }, 2000);
    }

    function showReady(job) {
        var media = job.outputs[0];
        state.media = media;
        var secs = job.started_at && job.finished_at ? Math.round((new Date(job.finished_at) - new Date(job.created_at)) / 1000) : null;
        document.getElementById('render-time').textContent = secs !== null ? 'Render Time: ' + secs + 's' : 'Ready';
        var player = document.getElementById('output-player');
        player.innerHTML = media.kind === 'video'
            ? '<video src="' + esc(media.url) + '" controls autoplay loop muted playsinline class="max-h-[500px] w-auto max-w-full"></video>'
            : '<img src="' + esc(media.url) + '" alt="Generated image" class="max-h-[500px] w-auto max-w-full object-contain">';
        document.getElementById('output-meta').textContent = media.original_name + ' · ' + (media.width ? media.width + '×' + media.height + ' · ' : '') + N.bytes(media.size_bytes);
        document.getElementById('download-btn').href = media.url + '?download=1';
        showState('ready-state');
        N.icons();
    }

    // ------------------------------------------------------------------ step 4: schedule
    function todayIn(tz) {
        var parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
        return parts; // en-CA formats as YYYY-MM-DD
    }

    function openSchedule(media, fromStep) {
        if (!media) { goTo(1); return; }
        state.media = media;
        state.fromStep = fromStep;
        var user = N.user;
        document.getElementById('tz-label').textContent = user.timezone;
        document.getElementById('schedule-thumb').innerHTML = N.thumb(media, 'w-full h-full');
        document.getElementById('schedule-media-name').textContent = media.original_name;
        var dateInput = document.getElementById('publish-date'), timeInput = document.getElementById('publish-time');
        var today = todayIn(user.timezone);
        if (!dateInput.value) {
            dateInput.value = today;
            timeInput.value = user.default_time;
            var nowHM = new Intl.DateTimeFormat('en-GB', { timeZone: user.timezone, hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date());
            if (nowHM >= user.default_time) {
                var d = new Date(today + 'T12:00:00');
                d.setDate(d.getDate() + 1);
                dateInput.value = d.toISOString().slice(0, 10);
            }
        }
        dateInput.min = today;
        var caption = document.getElementById('caption');
        if (!caption.value && user.default_hashtags) caption.value = '\n\n' + user.default_hashtags;
        renderPlatforms();
        goTo(4);
    }

    function renderPlatforms() {
        var list = document.getElementById('platform-list');
        var media = state.media, defaults = N.user.default_platforms || [];
        if (!state.accounts.length) {
            list.innerHTML = '<div class="p-5 rounded-xl border border-dashed border-white/15 text-sm text-gray-400">No social accounts connected yet. ' +
                '<a href="connections.html" class="text-electric hover:text-goldlight">Connect an account</a> to publish.</div>';
            return;
        }
        list.innerHTML = state.accounts.map(function (a) {
            var p = state.platforms[a.platform] || {};
            var ok = p.configured && (p.media_kinds || []).indexOf(media.kind) >= 0;
            var why = !p.configured ? 'Not configured on this server' : !ok ? 'Does not accept ' + media.kind + 's' : '@' + a.username;
            var selected = ok && (defaults.length ? defaults.indexOf(a.platform) >= 0 : true);
            return '<div role="checkbox" tabindex="0" aria-checked="' + selected + '" data-account="' + a.id + '" data-platform="' + esc(a.platform) + '" class="platform-card ' +
                (selected ? 'selected ' : '') + (ok ? '' : 'disabled ') + 'flex items-center justify-between p-4 rounded-xl border border-white/10 bg-white/5 cursor-pointer transition-all">' +
                '<div class="flex items-center gap-3">' + N.platformBadge(a.platform, 'w-10 h-10 !rounded-full') +
                '<div><h4 class="font-bold text-white text-sm">' + esc((N.platforms[a.platform] || {}).label || a.platform) + '</h4><p class="text-xs text-gray-400">' + esc(why) + '</p></div></div>' +
                '<div class="w-6 h-6 rounded-full border-2 border-gray-600 text-electric flex items-center justify-center check-icon"><i data-lucide="check" class="w-4 h-4 hidden"></i></div></div>';
        }).join('');
        N.icons();
        syncPlatformFields();
    }

    function selectedAccounts() {
        return Array.prototype.map.call(document.querySelectorAll('.platform-card.selected'), function (el) {
            return { id: +el.dataset.account, platform: el.dataset.platform };
        });
    }

    function syncPlatformFields() {
        var sel = selectedAccounts();
        var hasYT = sel.some(function (a) { return a.platform === 'youtube'; });
        document.getElementById('title-field').classList.toggle('hidden', !hasYT);
        var title = document.getElementById('post-title');
        if (hasYT && !title.value) title.value = (state.job ? state.job.prompt : '').slice(0, 80);
        var len = document.getElementById('caption').value.length;
        var limit = sel.some(function (a) { return a.platform === 'x'; }) ? 280 : 2200;
        var counter = document.getElementById('caption-count');
        counter.textContent = len + ' / ' + limit + (limit === 280 ? ' (X limit — longer captions are cut on X)' : '');
        counter.className = 'text-xs mt-1 text-right ' + (len > limit ? 'text-red-400' : 'text-gray-500');
    }

    var platformList = document.getElementById('platform-list');
    function toggleCard(card) {
        if (!card || card.classList.contains('disabled')) return;
        card.classList.toggle('selected');
        card.setAttribute('aria-checked', card.classList.contains('selected'));
        syncPlatformFields();
    }
    platformList.addEventListener('click', function (e) { toggleCard(e.target.closest('.platform-card')); });
    platformList.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleCard(e.target.closest('.platform-card')); }
    });
    document.getElementById('caption').addEventListener('input', syncPlatformFields);
    document.getElementById('schedule-back').addEventListener('click', function () {
        if (state.fromStep === 3) goTo(3); else location.href = 'media.html';
    });

    async function submitPost(now) {
        var accounts = selectedAccounts();
        if (!accounts.length) { N.toast('Select at least one platform', 'error'); return; }
        var body = {
            media_id: state.media.id, account_ids: accounts.map(function (a) { return a.id; }),
            caption: document.getElementById('caption').value.trim(),
            title: document.getElementById('post-title').value.trim()
        };
        if (now) {
            if (!confirm('Publish to ' + accounts.length + ' account(s) right now?')) return;
            body.publish_now = true;
        } else {
            body.date = document.getElementById('publish-date').value;
            body.time = document.getElementById('publish-time').value;
            if (!body.date || !body.time) { N.toast('Pick a date and time', 'error'); return; }
        }
        var btns = [document.getElementById('publish-now'), document.getElementById('schedule-btn')];
        btns.forEach(function (b) { b.disabled = true; });
        try {
            var post = await N.api('/api/posts', { body: body });
            N.toast(now ? 'Publishing started' : 'Post scheduled', 'success');
            setTimeout(function () { location.href = 'calendar.html?post=' + post.id; }, 600);
        } catch (err) {
            N.fail(err);
            btns.forEach(function (b) { b.disabled = false; });
        }
    }
    document.getElementById('schedule-form').addEventListener('submit', function (e) { e.preventDefault(); submitPost(false); });
    document.getElementById('publish-now').addEventListener('click', function () { submitPost(true); });

    // ------------------------------------------------------------------ init
    async function init() {
        await N.ready;
        var r = await Promise.all([N.api('/api/templates'), N.api('/api/platforms'), N.api('/api/accounts')]);
        state.templates = r[0];
        r[1].forEach(function (p) { state.platforms[p.key] = p; });
        state.accounts = r[2];
        state.tab = N.query('tab') === 'mine' ? 'mine' : 'system';
        renderTemplates();

        N.api('/api/system/comfyui?models=true').then(function (c) {
            var warn = document.getElementById('comfy-warning');
            if (!c.online) {
                warn.textContent = 'ComfyUI is not reachable at ' + c.url + '. You can still queue generations; they will start once ComfyUI is online.';
                warn.classList.remove('hidden');
            } else if (c.workflows) {
                var missing = c.workflows.filter(function (w) { return !w.ready; });
                if (missing.length) {
                    warn.textContent = 'Some workflows are missing model files in ComfyUI: ' + missing.map(function (w) { return w.name + ' (' + w.missing.join(', ') + ')'; }).join('; ');
                    warn.classList.remove('hidden');
                }
            }
        }).catch(function () { /* status is informational */ });

        var jobId = N.query('job'), mediaId = N.query('media'), templateId = N.query('template');
        if (jobId) {
            var job = await N.api('/api/jobs/' + encodeURIComponent(jobId));
            state.template = state.templates.find(function (t) { return t.id === job.template_id; }) || null;
            if (state.template) {
                chooseTemplate(state.template.id);
                document.getElementById('prompt').value = job.prompt.replace(', ' + state.template.style_prompt, '');
            }
            watchJob(job);
        } else if (mediaId) {
            openSchedule(await N.api('/api/media/' + encodeURIComponent(mediaId)), 1);
        } else if (templateId) {
            chooseTemplate(+templateId);
        } else if (N.user.default_template_id && state.templates.some(function (t) { return t.id === N.user.default_template_id; })) {
            var card = document.querySelector('[data-template="' + N.user.default_template_id + '"]');
            if (card) card.classList.add('border-electric/60');
        }
    }
    init().catch(N.fail);
})();
