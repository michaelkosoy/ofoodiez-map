/* Ofoodiez accessibility menu — self-hosted, no dependencies.
   Loaded on every page via components/analytics.html. Provides the user-facing
   adjustments expected under IS 5568 / WCAG 2.1 AA (text size, contrast,
   underlined links, readable font, stop animations) + a link to the
   accessibility statement. Preferences persist in localStorage. */
(function () {
    'use strict';
    var KEY = 'ofoodiez-a11y';
    var FLAGS = ['bigtext', 'hugetext', 'contrast', 'grayscale', 'links', 'font', 'still'];

    var css = [
        '.a11y-fab{position:fixed;bottom:88px;left:14px;z-index:99990;width:46px;height:46px;',
        'border-radius:50%;background:#1a56b0;color:#fff;border:2px solid #fff;cursor:pointer;',
        'font-size:24px;line-height:1;box-shadow:0 2px 10px rgba(0,0,0,.35);}',
        '.a11y-fab:focus{outline:3px solid #ffbf47;outline-offset:2px;}',
        '.a11y-panel{position:fixed;bottom:142px;left:14px;z-index:99991;background:#fff;color:#111;',
        'border:1px solid #bbb;border-radius:12px;padding:14px;width:230px;box-shadow:0 8px 30px rgba(0,0,0,.3);',
        'font-family:Arial,sans-serif;font-size:15px;direction:rtl;text-align:right;}',
        '.a11y-panel h2{font-size:16px;margin:0 0 10px;}',
        '.a11y-panel button{display:block;width:100%;margin:4px 0;padding:8px 10px;border:1px solid #888;',
        'border-radius:8px;background:#f7f7f7;cursor:pointer;font-size:14px;text-align:right;color:#111;}',
        '.a11y-panel button[aria-pressed="true"]{background:#1a56b0;color:#fff;border-color:#1a56b0;}',
        '.a11y-panel button:focus{outline:3px solid #ffbf47;}',
        '.a11y-panel a{display:block;margin-top:8px;font-size:13px;color:#1a56b0;}',
        'html.a11y-bigtext body{zoom:1.15;}',
        'html.a11y-hugetext body{zoom:1.35;}',
        'html.a11y-contrast{filter:invert(1) hue-rotate(180deg);background:#000;}',
        'html.a11y-contrast img,html.a11y-contrast video,html.a11y-contrast iframe{filter:invert(1) hue-rotate(180deg);}',
        'html.a11y-grayscale{filter:grayscale(1);}',
        'html.a11y-links a{text-decoration:underline !important;}',
        'html.a11y-font *{font-family:Arial,Helvetica,sans-serif !important;}',
        'html.a11y-still *{animation:none !important;transition:none !important;scroll-behavior:auto !important;}'
    ].join('');

    var labels = {
        bigtext: 'הגדלת טקסט', hugetext: 'טקסט גדול מאוד', contrast: 'ניגודיות גבוהה',
        grayscale: 'גווני אפור', links: 'הדגשת קישורים', font: 'פונט קריא', still: 'עצירת אנימציות'
    };

    function load() {
        try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
    }
    function save(state) {
        try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
    }
    function apply(state) {
        FLAGS.forEach(function (f) {
            document.documentElement.classList.toggle('a11y-' + f, !!state[f]);
        });
    }

    function build() {
        var style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);

        var state = load();
        apply(state);

        var fab = document.createElement('button');
        fab.className = 'a11y-fab';
        fab.type = 'button';
        fab.setAttribute('aria-label', 'תפריט נגישות / Accessibility menu');
        fab.setAttribute('aria-expanded', 'false');
        fab.textContent = '♿';
        document.body.appendChild(fab);

        var panel = document.createElement('div');
        panel.className = 'a11y-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'אפשרויות נגישות');
        panel.hidden = true;
        var h = document.createElement('h2');
        h.textContent = 'נגישות';
        panel.appendChild(h);

        FLAGS.forEach(function (f) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = labels[f];
            b.setAttribute('aria-pressed', String(!!state[f]));
            b.addEventListener('click', function () {
                state[f] = !state[f];
                if (f === 'bigtext' && state[f]) { state.hugetext = false; }
                if (f === 'hugetext' && state[f]) { state.bigtext = false; }
                save(state); apply(state);
                panel.querySelectorAll('button[data-flag]').forEach(function (x) {
                    x.setAttribute('aria-pressed', String(!!state[x.dataset.flag]));
                });
            });
            b.dataset.flag = f;
            panel.appendChild(b);
        });

        var reset = document.createElement('button');
        reset.type = 'button';
        reset.textContent = 'איפוס נגישות';
        reset.addEventListener('click', function () {
            state = {}; save(state); apply(state);
            panel.querySelectorAll('button[data-flag]').forEach(function (x) {
                x.setAttribute('aria-pressed', 'false');
            });
        });
        panel.appendChild(reset);

        var link = document.createElement('a');
        link.href = '/accessibility';
        link.textContent = 'הצהרת נגישות';
        panel.appendChild(link);
        document.body.appendChild(panel);

        fab.addEventListener('click', function () {
            panel.hidden = !panel.hidden;
            fab.setAttribute('aria-expanded', String(!panel.hidden));
            if (!panel.hidden) { panel.querySelector('button').focus(); }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !panel.hidden) {
                panel.hidden = true;
                fab.setAttribute('aria-expanded', 'false');
                fab.focus();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();
