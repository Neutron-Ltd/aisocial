(function () {
    'use strict';
    var N = window.NEUTX;
    var state = { workflows: [], aspect: '9:16', id: null, readiness: {} };
    var $ = function (id) { return document.getElementById(id); };

    function workflow() {
        return state.workflows.find(function (w) { return w.key === $('tpl-workflow').value; });
    }

    function selectAspect(aspect) {
        var wf = workflow();
        if (wf && wf.aspects.indexOf(aspect) < 0) aspect = wf.aspects[0];
        state.aspect = aspect;
        document.querySelectorAll('.res-card').forEach(function (el) {
            var supported = !wf || wf.aspects.indexOf(el.dataset.aspect) >= 0;
            var active = el.dataset.aspect === aspect;
            el.classList.toggle('active', active);
            el.classList.toggle('opacity-40', !supported);
            el.classList.toggle('pointer-events-none', !supported);
            el.setAttribute('aria-checked', active);
            el.setAttribute('aria-disabled', !supported);
            var icon = el.querySelector('div');
            icon.classList.toggle('text-electric', active);
            icon.classList.toggle('text-gray-500', !active);
        });
        preview();
    }

    function onWorkflowChange() {
        var wf = workflow();
        if (!wf) return;
        $('tpl-workflow-desc').textContent = wf.description + ' Output: ' + wf.kind + (wf.image_input === 'required' ? ' · needs a hero image' : wf.image_input === 'optional' ? ' · hero image optional' : '') + '.';
        var r = state.readiness[wf.key];
        var models = $('tpl-workflow-models');
        if (r && !r.ready) {
            models.className = 'text-xs mt-1 ml-1 text-yellow-300';
            models.textContent = 'Missing in ComfyUI: ' + r.missing.join(', ');
        } else if (r) {
            models.className = 'text-xs mt-1 ml-1 text-emerald-400';
            models.textContent = 'All required models are installed in ComfyUI.';
        } else {
            models.textContent = '';
        }
        selectAspect(state.aspect);
    }

    function preview() {
        var wf = workflow();
        if (!wf) return;
        var size = wf.sizes[state.aspect] || [];
        $('tpl-preview').textContent = JSON.stringify({
            name: $('tpl-name').value || '(unnamed)',
            workflow: wf.key + '.json',
            engine: wf.engine,
            width: size[0], height: size[1],
            prompt: '<your prompt>' + ($('tpl-style').value.trim() ? ', ' + $('tpl-style').value.trim() : ''),
            negative_prompt: $('tpl-negative').value.trim(),
            seed: '<random per generation>'
        }, null, 2);
    }

    async function save() {
        var body = {
            name: $('tpl-name').value.trim(), description: $('tpl-desc').value.trim(),
            workflow: $('tpl-workflow').value, aspect: state.aspect,
            style_prompt: $('tpl-style').value.trim(), negative_prompt: $('tpl-negative').value.trim()
        };
        if (!body.name) { N.toast('Give your template a name', 'error'); $('tpl-name').focus(); return; }
        var btn = $('tpl-save');
        btn.disabled = true;
        try {
            var saved = state.id
                ? await N.api('/api/templates/' + state.id, { method: 'PUT', body: body })
                : await N.api('/api/templates', { body: body });
            N.toast('Template saved', 'success');
            setTimeout(function () { location.href = 'studio.html?template=' + saved.id; }, 600);
        } catch (err) { N.fail(err); btn.disabled = false; }
    }

    async function remove() {
        if (!confirm('Delete this template? Posts and media made with it are kept.')) return;
        try {
            await N.api('/api/templates/' + state.id, { method: 'DELETE' });
            N.toast('Template deleted', 'success');
            setTimeout(function () { location.href = 'studio.html?tab=mine'; }, 500);
        } catch (err) { N.fail(err); }
    }

    document.querySelectorAll('.res-card').forEach(function (el) {
        el.addEventListener('click', function () { selectAspect(el.dataset.aspect); });
        el.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAspect(el.dataset.aspect); } });
    });
    $('tpl-workflow').addEventListener('change', onWorkflowChange);
    ['tpl-name', 'tpl-style', 'tpl-negative'].forEach(function (id) { $(id).addEventListener('input', preview); });
    $('tpl-save').addEventListener('click', save);
    $('tpl-delete').addEventListener('click', remove);

    (async function init() {
        await N.ready;
        state.workflows = await N.api('/api/workflows');
        $('tpl-workflow').innerHTML = state.workflows.map(function (w) {
            return '<option value="' + N.esc(w.key) + '">' + N.esc(w.name) + '</option>';
        }).join('');
        var id = N.query('id');
        if (id) {
            var t = await N.api('/api/templates/' + encodeURIComponent(id));
            if (t.system) {
                // System templates are read-only: open as a copy.
                $('tpl-heading').textContent = 'Customize "' + t.name + '"';
                $('tpl-name').value = t.name + ' (copy)';
            } else {
                state.id = t.id;
                $('tpl-heading').textContent = 'Edit Template';
                $('tpl-name').value = t.name;
                $('tpl-delete').classList.remove('hidden');
            }
            $('tpl-desc').value = t.description;
            $('tpl-workflow').value = t.workflow;
            $('tpl-style').value = t.style_prompt;
            $('tpl-negative').value = t.negative_prompt;
            state.aspect = t.aspect;
        }
        onWorkflowChange();
        N.api('/api/system/comfyui?models=true').then(function (c) {
            (c.workflows || []).forEach(function (w) { state.readiness[w.key] = w; });
            onWorkflowChange();
        }).catch(function () { /* informational */ });
    })().catch(N.fail);
})();
