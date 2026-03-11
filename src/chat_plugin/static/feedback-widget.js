/**
 * Amplifier Feedback Widget
 *
 * A self-contained, framework-agnostic feedback component that opens a
 * pre-filled GitHub issue.  Drop a single <script> tag into any page and
 * call `AmplifierFeedback.init(opts)`.
 *
 * Three rendering modes:
 *   "floating" – fixed FAB in the bottom-right corner (default/fallback)
 *   "header"   – icon-only button for dense header bars (chat)
 *   "inline"   – text button that blends into surrounding links (dashboard footer, settings header)
 */
(function () {
  'use strict';

  /* ------------------------------------------------------------------ */
  /*  Constants                                                          */
  /* ------------------------------------------------------------------ */

  var REPO = 'microsoft/amplifier-distro';
  var CATEGORIES = [
    { key: 'bug',     label: 'Bug Report' },
    { key: 'feature', label: 'Feature Request' },
    { key: 'general', label: 'General' },
  ];
  var GITHUB_LABEL_MAP = {
    bug: 'bug',
    feature: 'enhancement',
    general: 'feedback',
  };

  /* ------------------------------------------------------------------ */
  /*  Icon SVG (chat-bubble + heart)                                     */
  /* ------------------------------------------------------------------ */

  var ICON_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' +
    '<path d="M12 8.5c-1-1.2-3-.4-2.5 1.1.5 1.4 2.5 2.9 2.5 2.9s2-1.5 2.5-2.9c.5-1.5-1.5-2.3-2.5-1.1z" stroke-width="1.5"/>' +
    '</svg>';

  /* ------------------------------------------------------------------ */
  /*  Stylesheet (injected once)                                         */
  /* ------------------------------------------------------------------ */

  var CSS = [
    /* --- Floating trigger (FAB) --- */
    '.amp-fb-fab {',
    '  position: fixed; bottom: 24px; right: 24px; z-index: 900;',
    '  width: 48px; height: 48px; border-radius: 50%;',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  background: var(--canvas-warm, var(--bg-secondary, #1E1E1E));',
    '  color: var(--ink-slate, var(--text-secondary, #999));',
    '  cursor: pointer; display: flex; align-items: center; justify-content: center;',
    '  box-shadow: var(--shadow-elevate, 0 4px 12px rgba(0,0,0,0.25));',
    '  transition: all 200ms cubic-bezier(0.22,1,0.36,1);',
    '  animation: amp-fb-entrance 400ms cubic-bezier(0.175,0.885,0.32,1.275) 1s both;',
    '  padding: 0; margin: 0;',
    '}',
    '.amp-fb-fab:hover {',
    '  background: var(--signal-soft, rgba(91,77,227,0.06));',
    '  border-color: var(--signal, var(--accent, #5B4DE3));',
    '  color: var(--signal, var(--accent, #5B4DE3));',
    '  box-shadow: var(--shadow-float, 0 8px 24px rgba(0,0,0,0.35));',
    '  transform: translateY(-2px);',
    '}',
    '.amp-fb-fab:active { transform: translateY(0); }',
    '.amp-fb-fab:focus-visible {',
    '  outline: 2px solid var(--signal, var(--accent, #5B4DE3));',
    '  outline-offset: 2px;',
    '}',
    '.amp-fb-fab svg { width: 22px; height: 22px; }',
    '@keyframes amp-fb-entrance {',
    '  from { opacity: 0; transform: scale(0.8) translateY(8px); }',
    '  to   { opacity: 1; transform: scale(1) translateY(0); }',
    '}',

    /* --- Header trigger --- */
    '.amp-fb-header-btn {',
    '  background: var(--bg-tertiary, var(--canvas-stone, #262626));',
    '  border: 1px solid var(--border, var(--canvas-mist, rgba(255,255,255,0.08)));',
    '  color: var(--text-secondary, var(--ink-slate, #999));',
    '  padding: 4px 6px; border-radius: 4px;',
    '  cursor: pointer; display: inline-flex; align-items: center; justify-content: center;',
    '  transition: all 0.15s;',
    '  margin: 0;',
    '}',
    '.amp-fb-header-btn:hover {',
    '  background: var(--bg-card, var(--canvas, #171717));',
    '  color: var(--text-primary, var(--ink, #e8e8e8));',
    '}',
    '.amp-fb-header-btn:focus-visible {',
    '  outline: 2px solid var(--signal, var(--accent, #5B4DE3));',
    '  outline-offset: 1px;',
    '}',
    '.amp-fb-header-btn svg { width: 14px; height: 14px; }',

    /* --- Inline trigger (blends into surrounding text links) --- */
    '.amp-fb-inline-btn {',
    '  background: none; border: none; padding: 0; margin: 0;',
    '  color: inherit; font: inherit; cursor: pointer;',
    '  text-decoration: none; position: relative;',
    '  transition: color 200ms cubic-bezier(0.22,1,0.36,1);',
    '}',
    '.amp-fb-inline-btn:hover {',
    '  color: var(--signal, var(--accent, #5B4DE3));',
    '}',
    '.amp-fb-inline-btn::after {',
    '  content: ""; position: absolute; bottom: -2px; left: 0; right: 0;',
    '  height: 1px; background: var(--signal, var(--accent, #5B4DE3));',
    '  transform: scaleX(0); transition: transform 200ms cubic-bezier(0.22,1,0.36,1);',
    '}',
    '.amp-fb-inline-btn:hover::after { transform: scaleX(1); }',
    '.amp-fb-inline-btn:focus-visible {',
    '  outline: 2px solid var(--signal, var(--accent, #5B4DE3));',
    '  outline-offset: 2px;',
    '}',

    /* --- Backdrop --- */
    '.amp-fb-backdrop {',
    '  position: fixed; inset: 0; z-index: 1001;',
    '  background: var(--overlay, rgba(0,0,0,0.5));',
    '  display: flex; align-items: center; justify-content: center;',
    '  animation: amp-fb-fade-in 200ms cubic-bezier(0.22,1,0.36,1);',
    '}',
    '@keyframes amp-fb-fade-in { from { opacity: 0; } to { opacity: 1; } }',

    /* --- Modal card --- */
    '.amp-fb-card {',
    '  background: var(--canvas-warm, var(--bg-secondary, #1E1E1E));',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-radius: var(--radius-card, 20px);',
    '  padding: 28px; width: 90%; max-width: 440px;',
    '  box-shadow: var(--shadow-float, 0 8px 24px rgba(0,0,0,0.35));',
    '  animation: amp-fb-card-enter 300ms cubic-bezier(0.22,1,0.36,1);',
    '  position: relative;',
    '}',
    '@keyframes amp-fb-card-enter {',
    '  from { opacity: 0; transform: scale(0.96) translateY(8px); }',
    '  to   { opacity: 1; transform: scale(1) translateY(0); }',
    '}',

    /* --- Header row --- */
    '.amp-fb-card-header {',
    '  display: flex; align-items: center; justify-content: space-between;',
    '  margin-bottom: 20px;',
    '}',
    '.amp-fb-card-title {',
    '  font-family: var(--font-heading, "Syne", system-ui, sans-serif);',
    '  font-size: 18px; font-weight: 700; letter-spacing: -0.02em;',
    '  color: var(--ink, var(--text-primary, #e8e8e8));',
    '  margin: 0;',
    '}',
    '.amp-fb-close {',
    '  width: 28px; height: 28px; border-radius: 8px;',
    '  border: none; background: transparent;',
    '  color: var(--ink-fog, var(--text-muted, #555));',
    '  cursor: pointer; display: flex; align-items: center; justify-content: center;',
    '  font-size: 18px; line-height: 1;',
    '  transition: all 150ms;',
    '}',
    '.amp-fb-close:hover {',
    '  background: var(--canvas-stone, var(--bg-tertiary, #262626));',
    '  color: var(--ink, var(--text-primary, #e8e8e8));',
    '}',

    /* --- Category segmented control --- */
    '.amp-fb-categories {',
    '  display: flex; gap: 0;',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-radius: var(--radius-button, 14px);',
    '  overflow: hidden; margin-bottom: 16px;',
    '}',
    '.amp-fb-cat {',
    '  flex: 1; padding: 8px 4px; background: transparent; border: none;',
    '  color: var(--ink-slate, var(--text-secondary, #999));',
    '  font-size: 12px; font-weight: 600;',
    '  font-family: var(--font-body, "Epilogue", system-ui, sans-serif);',
    '  cursor: pointer; text-align: center;',
    '  transition: all 200ms cubic-bezier(0.22,1,0.36,1);',
    '}',
    '.amp-fb-cat:not(:last-child) {',
    '  border-right: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '}',
    '.amp-fb-cat:hover { background: var(--signal-soft, rgba(91,77,227,0.06)); }',
    '.amp-fb-cat[aria-checked="true"] {',
    '  background: var(--signal, var(--accent, #5B4DE3)); color: #fff;',
    '}',

    /* --- Labels --- */
    '.amp-fb-label {',
    '  display: block; font-size: 12px; font-weight: 600;',
    '  color: var(--ink-slate, var(--text-secondary, #999));',
    '  margin-bottom: 6px;',
    '  font-family: var(--font-body, "Epilogue", system-ui, sans-serif);',
    '}',
    '.amp-fb-required { color: var(--error, #ef4444); }',

    /* --- Inputs --- */
    '.amp-fb-field { margin-bottom: 14px; }',
    '.amp-fb-input, .amp-fb-textarea {',
    '  width: 100%;',
    '  background: var(--canvas, var(--bg-primary, #0d0d0d));',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-radius: var(--radius-input, 10px);',
    '  color: var(--ink, var(--text-primary, #e8e8e8));',
    '  font-family: var(--font-body, "Epilogue", system-ui, sans-serif);',
    '  font-size: 14px; padding: 10px 12px; outline: none;',
    '  transition: border-color 200ms cubic-bezier(0.22,1,0.36,1), box-shadow 200ms;',
    '  box-sizing: border-box;',
    '}',
    '.amp-fb-input:focus, .amp-fb-textarea:focus {',
    '  border-color: var(--signal, var(--accent, #5B4DE3));',
    '  box-shadow: 0 0 0 3px var(--signal-soft, rgba(91,77,227,0.06));',
    '}',
    '.amp-fb-input::placeholder, .amp-fb-textarea::placeholder {',
    '  color: var(--ink-fog, var(--text-muted, #555));',
    '}',
    '.amp-fb-textarea { resize: vertical; min-height: 80px; max-height: 200px; }',

    /* --- Button row --- */
    '.amp-fb-actions {',
    '  display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px;',
    '}',
    '.amp-fb-btn-submit {',
    '  padding: 10px 20px; border: none;',
    '  border-radius: var(--radius-button, 14px);',
    '  background: var(--signal, var(--accent, #5B4DE3)); color: #fff;',
    '  font-family: var(--font-body, "Epilogue", system-ui, sans-serif);',
    '  font-size: 14px; font-weight: 600; cursor: pointer;',
    '  transition: all 200ms cubic-bezier(0.22,1,0.36,1);',
    '}',
    '.amp-fb-btn-submit:hover {',
    '  background: var(--signal-light, #7B6FF0);',
    '  box-shadow: 0 2px 8px var(--signal-glow, rgba(91,77,227,0.15));',
    '}',
    '.amp-fb-btn-submit:disabled { opacity: 0.4; cursor: not-allowed; }',
    '.amp-fb-btn-cancel {',
    '  padding: 10px 20px;',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-radius: var(--radius-button, 14px);',
    '  background: transparent;',
    '  color: var(--ink-slate, var(--text-secondary, #999));',
    '  font-family: var(--font-body, "Epilogue", system-ui, sans-serif);',
    '  font-size: 14px; cursor: pointer;',
    '  transition: all 200ms cubic-bezier(0.22,1,0.36,1);',
    '}',
    '.amp-fb-btn-cancel:hover {',
    '  background: var(--canvas-stone, var(--bg-tertiary, #262626));',
    '  color: var(--ink, var(--text-primary, #e8e8e8));',
    '}',

    /* --- Mobile sheet --- */
    '@media (max-width: 768px) {',
    '  .amp-fb-backdrop { align-items: flex-end; }',
    '  .amp-fb-card {',
    '    width: 100%; max-width: none;',
    '    border-radius: var(--radius-card, 20px) var(--radius-card, 20px) 0 0;',
    '    padding-bottom: calc(28px + env(safe-area-inset-bottom, 0px));',
    '    animation-name: amp-fb-sheet-enter;',
    '  }',
    '  .amp-fb-fab { bottom: max(24px, calc(env(safe-area-inset-bottom, 0px) + 16px)); }',
    '}',
    '@keyframes amp-fb-sheet-enter {',
    '  from { opacity: 0; transform: translateY(100%); }',
    '  to   { opacity: 1; transform: translateY(0); }',
    '}',

    /* --- Reduced motion --- */
    '@media (prefers-reduced-motion: reduce) {',
    '  .amp-fb-fab, .amp-fb-card, .amp-fb-backdrop {',
    '    animation-duration: 0.01ms !important;',
    '    transition-duration: 0.01ms !important;',
    '  }',
    '}',
  ].join('\n');

  /* ------------------------------------------------------------------ */
  /*  Helpers                                                            */
  /* ------------------------------------------------------------------ */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'className') { node.className = attrs[k]; }
        else if (k.slice(0, 2) === 'on') {
          node.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
        } else {
          node.setAttribute(k, attrs[k]);
        }
      });
    }
    (children || []).forEach(function (c) {
      if (typeof c === 'string') { node.appendChild(document.createTextNode(c)); }
      else if (c) { node.appendChild(c); }
    });
    return node;
  }

  function buildGitHubUrl(category, title, body, repo, surface) {
    var label = GITHUB_LABEL_MAP[category] || 'feedback';
    var labels = [label];
    if (surface) { labels.push('surface:' + surface); }
    var parts = [
      'labels=' + encodeURIComponent(labels.join(',')),
      'title=' + encodeURIComponent('[' + (CATEGORIES.find(function(c){return c.key===category;}) || {}).label + '] ' + title),
      'body=' + encodeURIComponent(body),
    ];
    return 'https://github.com/' + repo + '/issues/new?' + parts.join('&');
  }

  function buildIssueBody(category, description, context) {
    var lines = [];
    lines.push('## Description');
    lines.push('');
    lines.push(description || '_No additional details provided._');
    lines.push('');
    lines.push('---');
    lines.push('');
    lines.push('**Submitted via:** Amplifier ' + (context.app || 'Web') + ' UI');
    if (context.userAgent) {
      lines.push('**User Agent:** `' + context.userAgent + '`');
    }
    return lines.join('\n');
  }

  /* ------------------------------------------------------------------ */
  /*  Modal                                                              */
  /* ------------------------------------------------------------------ */

  function openModal(opts) {
    var category = 'general';
    var backdrop = el('div', {
      className: 'amp-fb-backdrop',
      role: 'presentation',
      onClick: function (e) { if (e.target === backdrop) { closeModal(); } },
    });

    var titleInput = el('input', {
      className: 'amp-fb-input',
      type: 'text',
      placeholder: 'Brief description\u2026',
      'aria-required': 'true',
      onInput: syncSubmit,
    });

    var descInput = el('textarea', {
      className: 'amp-fb-textarea',
      placeholder: 'Tell us more (optional)\u2026',
      rows: '3',
    });

    var submitBtn = el('button', {
      className: 'amp-fb-btn-submit',
      type: 'button',
      disabled: 'true',
      onClick: doSubmit,
    }, ['Submit']);

    function syncSubmit() {
      if (titleInput.value.trim()) {
        submitBtn.removeAttribute('disabled');
      } else {
        submitBtn.setAttribute('disabled', 'true');
      }
    }

    function selectCategory(key) {
      category = key;
      var btns = catGroup.querySelectorAll('.amp-fb-cat');
      btns.forEach(function (b) {
        b.setAttribute('aria-checked', b.dataset.key === key ? 'true' : 'false');
      });
    }

    // Category segmented control
    var catGroup = el('div', {
      className: 'amp-fb-categories',
      role: 'radiogroup',
      'aria-label': 'Feedback category',
    }, CATEGORIES.map(function (c) {
      return el('button', {
        className: 'amp-fb-cat',
        type: 'button',
        role: 'radio',
        'aria-checked': c.key === category ? 'true' : 'false',
        'data-key': c.key,
        onClick: function () { selectCategory(c.key); },
      }, [c.label]);
    }));

    var card = el('div', {
      className: 'amp-fb-card',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': 'amp-fb-title',
    }, [
      // Header
      el('div', { className: 'amp-fb-card-header' }, [
        el('h2', { className: 'amp-fb-card-title', id: 'amp-fb-title' }, ['Send Feedback']),
        el('button', {
          className: 'amp-fb-close',
          'aria-label': 'Close feedback form',
          type: 'button',
          onClick: closeModal,
        }, ['\u00d7']),
      ]),
      // Category
      catGroup,
      // Title
      el('div', { className: 'amp-fb-field' }, [
        el('label', { className: 'amp-fb-label', 'for': 'amp-fb-title-input' }, [
          'Title ',
          el('span', { className: 'amp-fb-required' }, ['*']),
        ]),
        titleInput,
      ]),
      // Description
      el('div', { className: 'amp-fb-field' }, [
        el('label', { className: 'amp-fb-label', 'for': 'amp-fb-desc-input' }, ['Details']),
        descInput,
      ]),
      // Actions
      el('div', { className: 'amp-fb-actions' }, [
        el('button', {
          className: 'amp-fb-btn-cancel',
          type: 'button',
          onClick: closeModal,
        }, ['Cancel']),
        submitBtn,
      ]),
    ]);

    titleInput.id = 'amp-fb-title-input';
    descInput.id = 'amp-fb-desc-input';
    backdrop.appendChild(card);
    document.body.appendChild(backdrop);

    // Focus management
    titleInput.focus();

    // Keyboard handling
    function onKey(e) {
      if (e.key === 'Escape') { closeModal(); }
      if (e.key === 'Tab') {
        // Simple focus trap
        var focusable = card.querySelectorAll(
          'button:not([disabled]), input, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener('keydown', onKey);

    var triggerEl = opts._triggerEl;

    function closeModal() {
      document.removeEventListener('keydown', onKey);
      if (backdrop.parentNode) { backdrop.parentNode.removeChild(backdrop); }
      if (triggerEl) { try { triggerEl.focus(); } catch (e) { /* noop */ } }
    }

    function doSubmit() {
      var title = titleInput.value.trim();
      if (!title) return;

      var body = buildIssueBody(
        category,
        descInput.value.trim(),
        {
          app: opts.context && opts.context.app || 'web',
          userAgent: navigator.userAgent,
        }
      );

      var surface = opts.context && opts.context.app || '';
      var url = buildGitHubUrl(category, title, body, opts.repo || REPO, surface);

      submitBtn.textContent = 'Opening GitHub\u2026';
      submitBtn.setAttribute('disabled', 'true');

      window.open(url, '_blank', 'noopener');

      setTimeout(closeModal, 600);
    }
  }

  /* ------------------------------------------------------------------ */
  /*  Public API                                                         */
  /* ------------------------------------------------------------------ */

  var styleInjected = false;

  function injectStyle() {
    if (styleInjected) return;
    var s = document.createElement('style');
    s.textContent = CSS;
    document.head.appendChild(s);
    styleInjected = true;
  }

  /**
   * Initialise the feedback widget.
   *
   * @param {Object}  opts
   * @param {"floating"|"header"|"inline"} [opts.mode="floating"]
   *   - "floating": fixed FAB in the bottom-right corner
   *   - "header":   icon-only button for dense header bars (e.g. chat)
   *   - "inline":   text button that blends into surrounding links (e.g. footer, header-actions)
   * @param {HTMLElement}  [opts.container]  Mount target (required for "header" and "inline")
   * @param {string}       [opts.label]      Text label for inline mode (default: "Feedback")
   * @param {string}       [opts.repo]       GitHub owner/repo
   * @param {Object}       [opts.context]    Extra context { app, sessionId }
   */
  function init(opts) {
    opts = opts || {};
    injectStyle();

    var mode = opts.mode || 'floating';
    var trigger;
    var openFn = function () { openModal(Object.assign({}, opts, { _triggerEl: trigger })); };

    if (mode === 'header' && opts.container) {
      // Icon-only button for dense headers (chat)
      trigger = el('button', {
        className: 'amp-fb-header-btn',
        'aria-label': 'Send feedback',
        'aria-haspopup': 'dialog',
        title: 'Send feedback',
        type: 'button',
        onClick: openFn,
      });
      trigger.innerHTML = ICON_SVG;
      opts.container.appendChild(trigger);

    } else if (mode === 'inline' && opts.container) {
      // Text button that blends into surrounding links
      trigger = el('button', {
        className: 'amp-fb-inline-btn',
        'aria-label': 'Send feedback',
        'aria-haspopup': 'dialog',
        type: 'button',
        onClick: openFn,
      }, [opts.label || 'Feedback']);
      opts.container.appendChild(trigger);

    } else {
      // Floating FAB (fallback)
      trigger = el('button', {
        className: 'amp-fb-fab',
        'aria-label': 'Send feedback',
        'aria-haspopup': 'dialog',
        title: 'Send feedback',
        type: 'button',
        onClick: openFn,
      });
      trigger.innerHTML = ICON_SVG;
      document.body.appendChild(trigger);
    }

    return { trigger: trigger };
  }

  /* ------------------------------------------------------------------ */
  /*  Export                                                              */
  /* ------------------------------------------------------------------ */

  window.AmplifierFeedback = { init: init };
})();
