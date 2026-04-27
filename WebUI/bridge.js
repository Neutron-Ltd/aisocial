/**
 * NEUTX WebUI — shared mobile navigation (hamburger + drawer).
 */
(function () {
    'use strict';

    var sidebar = document.getElementById('bridge-sidebar');
    var toggle = document.getElementById('bridge-nav-toggle');
    var backdrop = document.getElementById('bridge-nav-backdrop');
    if (!sidebar || !toggle) return;

    var mq = window.matchMedia('(min-width: 768px)');

    function isDesktop() {
        return mq.matches;
    }

    function setOpen(open) {
        if (isDesktop()) {
            sidebar.classList.remove('bridge-nav-open');
            if (backdrop) {
                backdrop.classList.remove('bridge-nav-backdrop--open');
                backdrop.setAttribute('aria-hidden', 'true');
            }
            toggle.setAttribute('aria-expanded', 'false');
            toggle.setAttribute('aria-label', 'Open menu');
            return;
        }
        if (open) {
            sidebar.classList.add('bridge-nav-open');
            if (backdrop) {
                backdrop.classList.add('bridge-nav-backdrop--open');
                backdrop.setAttribute('aria-hidden', 'false');
            }
            toggle.setAttribute('aria-expanded', 'true');
            toggle.setAttribute('aria-label', 'Close menu');
        } else {
            sidebar.classList.remove('bridge-nav-open');
            if (backdrop) {
                backdrop.classList.remove('bridge-nav-backdrop--open');
                backdrop.setAttribute('aria-hidden', 'true');
            }
            toggle.setAttribute('aria-expanded', 'false');
            toggle.setAttribute('aria-label', 'Open menu');
        }
    }

    function onToggle() {
        if (isDesktop()) return;
        setOpen(!sidebar.classList.contains('bridge-nav-open'));
    }

    toggle.addEventListener('click', function (e) {
        e.stopPropagation();
        onToggle();
    });
    if (backdrop) {
        backdrop.addEventListener('click', function () {
            setOpen(false);
        });
    }

    sidebar.querySelectorAll('a[href]').forEach(function (a) {
        a.addEventListener('click', function () {
            setOpen(false);
        });
    });
    sidebar.querySelectorAll('button').forEach(function (btn) {
        if (btn.id === 'bridge-nav-toggle') return;
        btn.addEventListener('click', function () {
            setOpen(false);
        });
    });

    window.addEventListener('resize', function () {
        if (isDesktop()) setOpen(false);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !isDesktop() && sidebar.classList.contains('bridge-nav-open')) {
            setOpen(false);
        }
    });
})();
