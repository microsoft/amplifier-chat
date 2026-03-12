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

    /* --- Analysis section --- */
    '.amp-fb-analysis {',
    '  margin-top: 16px; padding: 12px;',
    '  border: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-radius: var(--radius-input, 10px);',
    '  background: var(--canvas, var(--bg-primary, #0d0d0d));',
    '  font-size: 13px; color: var(--ink-slate, var(--text-secondary, #999));',
    '  min-height: 48px;',
    '}',
    '.amp-fb-analysis-loading {',
    '  display: flex; align-items: center; gap: 10px;',
    '}',
    '.amp-fb-spinner {',
    '  width: 18px; height: 18px; border-radius: 50%;',
    '  border: 2px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '  border-top-color: var(--signal, var(--accent, #5B4DE3));',
    '  animation: amp-fb-spin 0.8s linear infinite;',
    '}',
    '@keyframes amp-fb-spin {',
    '  to { transform: rotate(360deg); }',
    '}',
    '.amp-fb-analysis-cancel {',
    '  background: none; border: none; color: var(--ink-fog, var(--text-muted, #555));',
    '  font-size: 12px; cursor: pointer; text-decoration: underline;',
    '  margin-left: auto; padding: 0;',
    '}',
    '.amp-fb-analysis-cancel:hover { color: var(--ink, var(--text-primary, #e8e8e8)); }',
    '.amp-fb-analysis-error {',
    '  color: var(--error, #ef4444); font-size: 13px;',
    '}',
    '.amp-fb-findings-group {',
    '  margin-top: 8px;',
    '}',
    '.amp-fb-findings-group-header {',
    '  font-size: 12px; font-weight: 600; margin-bottom: 6px;',
    '  color: var(--ink-slate, var(--text-secondary, #999));',
    '}',
    '.amp-fb-finding {',
    '  display: flex; align-items: flex-start; gap: 8px;',
    '  padding: 6px 0; border-bottom: 1px solid var(--canvas-mist, var(--border, rgba(255,255,255,0.08)));',
    '}',
    '.amp-fb-finding:last-child { border-bottom: none; }',
    '.amp-fb-finding input[type=checkbox] {',
    '  margin-top: 3px; accent-color: var(--signal, var(--accent, #5B4DE3));',
    '}',
    '.amp-fb-finding-content {',
    '  flex: 1; min-width: 0;',
    '}',
    '.amp-fb-finding-summary {',
    '  font-size: 13px; font-weight: 500;',
    '  color: var(--ink, var(--text-primary, #e8e8e8));',
    '}',
    '.amp-fb-finding-detail {',
    '  font-size: 12px; color: var(--ink-slate, var(--text-secondary, #999));',
    '  margin-top: 4px;',
    '}',
    '.amp-fb-finding-detail pre {',
    '  white-space: pre-wrap; word-break: break-word;',
    '  font-family: var(--font-mono, "Fira Code", monospace);',
    '  font-size: 11px; margin-top: 4px;',
    '  padding: 6px; border-radius: 4px;',
    '  background: var(--canvas-warm, var(--bg-secondary, #1E1E1E));',
    '}',
    '.amp-fb-finding-link {',
    '  font-size: 12px; color: var(--signal, var(--accent, #5B4DE3));',
    '  text-decoration: none;',
    '}',
    '.amp-fb-finding-link:hover { text-decoration: underline; }',
    '.amp-fb-finding-status {',
    '  font-size: 11px; font-weight: 600; padding: 1px 6px;',
    '  border-radius: 4px; display: inline-block; margin-left: 6px;',
    '}',
    '.amp-fb-finding-status.open {',
    '  background: rgba(34,197,94,0.15); color: var(--accent-green, #22c55e);',
    '}',
    '.amp-fb-finding-status.closed {',
    '  background: rgba(239,68,68,0.15); color: var(--error, #ef4444);',
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

  function serializeFindings(allFindings, checkedMap) {
    var checked = allFindings.filter(function (f, i) {
      return checkedMap[i] !== false;
    });
    if (!checked.length) return '';

    var lines = ['\n## Automated Findings'];

    var groups = [
      { source: 'github',     header: '### Related Issues' },
      { source: 'session',    header: '### Session Errors' },
      { source: 'server_log', header: '### Server Logs' },
    ];

    groups.forEach(function (group) {
      var groupFindings = checked.filter(function (f) {
        return f.source === group.source;
      });
      if (!groupFindings.length) return;

      lines.push('');
      lines.push(group.header);
      lines.push('');

      groupFindings.forEach(function (f) {
        if (group.source === 'github') {
          var summary = f.title || f.summary || f.url || '';
          var url = f.url || '';
          var entry = '- [' + summary + '](' + url + ')';
          if (f.state) {
            entry += ' `' + f.state + '`';
          }
          lines.push(entry);
          if (f.relevance) {
            lines.push('> ' + f.relevance);
          }
        } else if (group.source === 'session') {
          var sessionSummary = f.title || f.summary || '';
          var item = '- **' + sessionSummary + '**';
          if (f.error && f.error.type) {
            item += ' `' + f.error.type + '`';
          }
          lines.push(item);
          if (f.error) {
            if (f.error.message) {
              lines.push('  ' + f.error.message);
            }
            if (f.error.traceback && f.error.traceback.length) {
              lines.push('  ```');
              f.error.traceback.forEach(function (frame) {
                lines.push('  ' + frame);
              });
              lines.push('  ```');
            }
          }
        } else if (group.source === 'server_log') {
          var logSummary = f.title || f.summary || '';
          lines.push('- **' + logSummary + '**');
          if (f.context_lines && f.context_lines.length) {
            lines.push('  ```');
            f.context_lines.forEach(function (line) {
              lines.push('  ' + line);
            });
            lines.push('  ```');
          } else if (f.log_line) {
            lines.push('  ```');
            lines.push('  ' + f.log_line);
            lines.push('  ```');
          }
        }
      });
    });

    return lines.join('\n');
  }

  function extractFindings(text) {
    try {
      // Strip markdown code fences (```json ... ``` or ``` ... ```)
      var stripped = text.replace(/```[\w]*\n?/g, '').replace(/```/g, '');
      var first = stripped.indexOf('[');
      var last = stripped.lastIndexOf(']');
      if (first === -1 || last === -1 || last <= first) return [];
      return JSON.parse(stripped.substring(first, last + 1));
    } catch (e) {
      return [];
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function buildFindingDetail(f, source) {
    var parts = [];
    if (source === 'github') {
      if (f.relevance) {
        parts.push('<p>' + escapeHtml(f.relevance) + '</p>');
      }
    } else if (source === 'session') {
      if (f.event_type) {
        parts.push('<div><strong>Event:</strong> ' + escapeHtml(f.event_type) + '</div>');
      }
      if (f.turn != null) {
        parts.push('<div><strong>Turn:</strong> ' + escapeHtml(String(f.turn)) + '</div>');
      }
      if (f.error) {
        if (f.error.type) {
          parts.push('<div><strong>Type:</strong> ' + escapeHtml(f.error.type) + '</div>');
        }
        if (f.error.message) {
          parts.push('<div>' + escapeHtml(f.error.message) + '</div>');
        }
        if (f.error.traceback && f.error.traceback.length) {
          var frames = f.error.traceback.map(function (frame) { return escapeHtml(frame); });
          parts.push('<pre>' + frames.join('\n') + '</pre>');
        }
      }
    } else if (source === 'server_log') {
      if (f.log_level) {
        parts.push('<div><strong>Level:</strong> ' + escapeHtml(f.log_level) + '</div>');
      }
      if (f.context_lines && f.context_lines.length) {
        var lines = f.context_lines.map(function (line) { return escapeHtml(line); });
        parts.push('<pre>' + lines.join('\n') + '</pre>');
      } else if (f.log_line) {
        parts.push('<pre>' + escapeHtml(f.log_line) + '</pre>');
      }
    }
    return parts.length ? parts.join('') : null;
  }

  /* ------------------------------------------------------------------ */
  /*  Modal                                                              */
  /* ------------------------------------------------------------------ */

  function openModal(opts) {
    var category = 'general';

    // Analysis lifecycle state
    var apiBase = (window.location.origin || '') + '/chat/api';
    var analysisSessionId = null;
    var analysisSSE = null;
    var analysisComplete = false;
    var responseText = '';
    var findings = [];
    var findingChecked = {}; // Tracks per-finding checkbox state by index
    var analysisSection = el('div', { className: 'amp-fb-analysis' });

    function closeSSE() {
      if (analysisSSE) { analysisSSE.close(); analysisSSE = null; }
    }

    function updateAnalysisUI(state, errorMsg) {
      analysisSection.innerHTML = '';
      if (state === 'loading') {
        var spinner = el('div', { className: 'amp-fb-spinner' });
        var loadingRow = el('div', { className: 'amp-fb-analysis-loading' }, [
          spinner,
          el('span', null, ['Analyzing session\u2026']),
        ]);
        var cancelBtn = el('button', {
          className: 'amp-fb-analysis-cancel',
          type: 'button',
          onClick: function () { cancelAnalysis(); updateAnalysisUI('idle'); },
        }, ['Cancel']);
        loadingRow.appendChild(cancelBtn);
        analysisSection.appendChild(loadingRow);
      } else if (state === 'error') {
        analysisSection.appendChild(
          el('div', { className: 'amp-fb-analysis-error' }, [errorMsg || 'Analysis failed.'])
        );
      } else if (state === 'complete') {
        renderFindings();
      } else {
        // idle
        analysisSection.innerHTML = '';
      }
    }

    function startAnalysis() {
      var getSessionId = opts.getSessionId;
      var currentSessionId = getSessionId ? getSessionId() : null;
      if (!currentSessionId) {
        // No active session — skip analysis silently (nothing to analyze)
        analysisSection.style.display = 'none';
        return;
      }
      analysisSection.style.display = '';
      updateAnalysisUI('loading');
      fetch(apiBase + '/feedback/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId }),
      })
        .then(function (res) {
          if (!res.ok) throw new Error('Analysis request failed: ' + res.status);
          return res.json();
        })
        .then(function (data) {
          analysisSessionId = data.analysis_session_id;
          console.log('[feedback-analysis] Got analysis session:', analysisSessionId);
          subscribeToSSE(analysisSessionId);
        })
        .catch(function (err) {
          console.error('[feedback-analysis] Analyze request failed:', err);
          updateAnalysisUI('error', err.message);
        });
    }

    function subscribeToSSE(sessionId) {
      var sseUrl = '/events?session=' + encodeURIComponent(sessionId);
      console.log('[feedback-analysis] Opening SSE:', sseUrl);
      var evtSource = new EventSource(sseUrl);
      analysisSSE = evtSource;

      evtSource.onopen = function () {
        console.log('[feedback-analysis] SSE connected');
      };

      evtSource.addEventListener('content_block:delta', function (e) {
        try {
          var payload = JSON.parse(e.data);
          var delta = payload.delta || payload;
          responseText += (delta.text || delta.thinking || '');
        } catch (ex) { console.warn('SSE delta parse error:', ex); }
      });

      function onComplete() {
        if (analysisComplete) return;
        analysisComplete = true;
        closeSSE();
        console.log('[feedback-analysis] Complete. Response length:', responseText.length);
        findings = extractFindings(responseText);
        console.log('[feedback-analysis] Extracted', findings.length, 'findings');
        renderFindings();
      }

      evtSource.addEventListener('orchestrator:complete', onComplete);
      evtSource.addEventListener('execution:end', onComplete);

      evtSource.onerror = function (evt) {
        console.error('[feedback-analysis] SSE error:', evt, 'readyState:', evtSource.readyState);
        if (analysisComplete) return;
        // Try to parse whatever we have accumulated
        if (responseText) {
          findings = extractFindings(responseText);
          if (findings.length > 0) {
            analysisComplete = true;
            closeSSE();
            renderFindings();
            return;
          }
        }
        updateAnalysisUI('error', 'Connection to analysis stream lost.');
        closeSSE();
      };
    }

    function cancelAnalysis() {
      closeSSE();
      if (analysisSessionId && !analysisComplete) {
        // Cancel endpoint is at server root, not under apiBase (/chat/api)
        fetch('/sessions/' + encodeURIComponent(analysisSessionId) + '/cancel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ immediate: true }),
        }).catch(function () { /* best effort */ });
      }
    }

    function renderFindings() {
      analysisSection.innerHTML = '';
      var groups = [
        { source: 'github',     label: 'Related Issues' },
        { source: 'session',    label: 'Session Errors' },
        { source: 'server_log', label: 'Server Logs' },
      ];

      groups.forEach(function (group) {
        var groupFindings = findings.filter(function (f) {
          return f.source === group.source;
        });
        if (!groupFindings.length) return;

        var groupEl = el('div', { className: 'amp-fb-findings-group' });
        groupEl.appendChild(
          el('div', { className: 'amp-fb-findings-group-header' }, [group.label])
        );

        groupFindings.forEach(function (f) {
          var idx = findings.indexOf(f);

          var cb = el('input', { type: 'checkbox' });
          cb.checked = findingChecked[idx] !== false;
          cb.addEventListener('change', function () {
            findingChecked[idx] = cb.checked;
          });

          var summaryEl;
          if (group.source === 'github') {
            var link = el('a', {
              className: 'amp-fb-finding-link',
              href: f.url || '#',
              target: '_blank',
              rel: 'noopener',
            }, [f.title || f.url || '']);
            var statusClass = 'amp-fb-finding-status ' + (f.state === 'closed' ? 'closed' : 'open');
            var badge = el('span', { className: statusClass }, [f.state || 'open']);
            summaryEl = el('span', { className: 'amp-fb-finding-summary' }, [link, badge]);
          } else {
            summaryEl = el('span', { className: 'amp-fb-finding-summary' }, [
              f.title || f.summary || '',
            ]);
          }

          var contentChildren = [summaryEl];
          var detailHtml = buildFindingDetail(f, group.source);
          if (detailHtml) {
            var detailsEl = el('details', null);
            detailsEl.appendChild(el('summary', null, ['Details']));
            var inner = document.createElement('div');
            inner.innerHTML = detailHtml;
            detailsEl.appendChild(inner);
            contentChildren.push(
              el('div', { className: 'amp-fb-finding-detail' }, [detailsEl])
            );
          }

          groupEl.appendChild(
            el('div', { className: 'amp-fb-finding' }, [
              cb,
              el('div', { className: 'amp-fb-finding-content' }, contentChildren),
            ])
          );
        });

        analysisSection.appendChild(groupEl);
      });
    }

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
      // Analysis
      analysisSection,
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

    // Kick off analysis
    startAnalysis();

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
      cancelAnalysis();
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

      if (findings.length > 0) {
        body += serializeFindings(findings, findingChecked);
      }

      var surface = opts.context && opts.context.app || '';
      var url = buildGitHubUrl(category, title, body, opts.repo || REPO, surface);

      submitBtn.textContent = 'Opening GitHub\u2026';
      submitBtn.setAttribute('disabled', 'true');

      if (!analysisComplete) { cancelAnalysis(); }

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
