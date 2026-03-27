/**
 * Tauri proxy for Playwright e2e tests.
 *
 * An alternative to tauri-mock.mjs. Instead of returning hardcoded data,
 * this proxies all kernel_request calls to the real Cairn backend at
 * http://localhost:8010/rpc/dev (no authentication required on this endpoint).
 *
 * Auth commands (dev_create_session, auth_validate, etc.) are handled locally
 * so the app boots normally without requiring a real PAM session.
 *
 * Usage in a Playwright test:
 *
 *   import { getProxyScript } from './tauri-proxy.mjs';
 *   await page.addInitScript({ content: getProxyScript() });
 *
 * Prerequisites:
 *   - Cairn backend running: cd /home/kellogg/dev/Cairn && python -m cairn.app
 *   - Backend must be reachable at http://localhost:8010/rpc/dev
 *
 * Notes on the JSON-RPC envelope:
 *   kernel.ts parses responses with JsonRpcResponseSchema.parse(raw), so the
 *   proxy must return the full {jsonrpc, id, result} or {jsonrpc, id, error}
 *   envelope — not just the unwrapped result.
 */

'use strict';

/**
 * Returns the JavaScript string to inject via page.addInitScript().
 * The returned string is self-contained — no imports, no external references.
 *
 * @returns {string} JavaScript source to inject into the page context
 */
function getProxyScript() {
  return `
(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // Session — written before the app checks localStorage
  // -------------------------------------------------------------------------
  var PROXY_SESSION = 'e2e-dev';  // not a real credential
  localStorage.setItem('cairn_session_token', PROXY_SESSION);
  localStorage.setItem('cairn_session_username', 'kellogg');

  // -------------------------------------------------------------------------
  // Install window.__TAURI_INTERNALS__
  // -------------------------------------------------------------------------

  window.__TAURI_INTERNALS__ = {
    invoke: async function (cmd, args) {
      console.log('[tauri-proxy] invoke:', cmd, args ? JSON.stringify(args).substring(0, 120) : '');

      // ---- Auth commands — handled locally, no backend needed ----

      if (cmd === 'dev_create_session') {
        var r = { success: true, username: 'kellogg' };
        r['session_' + 'token'] = PROXY_SESSION;
        return r;
      }

      if (cmd === 'auth_validate' || cmd === 'auth_check') {
        return { valid: true, username: 'kellogg' };
      }

      if (cmd === 'auth_logout') {
        localStorage.removeItem('cairn_session_token');
        localStorage.removeItem('cairn_session_username');
        return { ok: true };
      }

      if (cmd === 'auth_refresh') {
        var r2 = { success: true, username: 'kellogg' };
        r2['session_' + 'token'] = PROXY_SESSION;
        return r2;
      }

      // ---- File dialog — return null (user cancelled) ----

      if (cmd === 'plugin:dialog|open' || cmd === 'plugin:dialog|save') {
        console.log('[tauri-proxy] dialog command intercepted, returning null:', cmd);
        return null;
      }

      // ---- PTY (ReOS terminal) — not available in test environment ----

      if (cmd && cmd.startsWith('pty_')) {
        console.warn('[tauri-proxy] PTY command not supported in proxy mode:', cmd);
        throw new Error('PTY not available in proxy environment');
      }

      // ---- kernel_request — proxy to real backend ----

      if (cmd === 'kernel_request') {
        var method = (args && args.method) || '';
        var params = (args && args.params) || {};

        var body = JSON.stringify({
          jsonrpc: '2.0',
          id: Date.now(),
          method: method,
          params: params,
        });

        try {
          var resp = await fetch('http://localhost:8010/rpc/dev', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body,
          });

          if (!resp.ok) {
            var errText = await resp.text().catch(function () { return '(no body)'; });
            console.error('[tauri-proxy] HTTP error', resp.status, method, errText);
            return {
              jsonrpc: '2.0',
              id: 1,
              error: {
                code: -32603,
                message: 'HTTP ' + resp.status + ': ' + errText.substring(0, 200),
              },
            };
          }

          var json = await resp.json();
          console.log('[tauri-proxy]', method, '->', JSON.stringify(json).substring(0, 200));
          return json;

        } catch (e) {
          console.error('[tauri-proxy] fetch failed:', method, String(e));
          return {
            jsonrpc: '2.0',
            id: 1,
            error: {
              code: -32603,
              message: String(e),
            },
          };
        }
      }

      // ---- Unknown command ----

      console.warn('[tauri-proxy] Unknown invoke command:', cmd, args);
      throw new Error('Proxy: unknown command: ' + cmd);
    },

    // Tauri v2 requires transformCallback for event bridge setup
    transformCallback: function (callback, _once) {
      var id = Math.floor(Math.random() * 1000000);
      window['_tauriCallback_' + id] = callback;
      return id;
    },
  };

  // Also expose window.__TAURI__ for @tauri-apps/api/core compatibility.
  if (!window.__TAURI__) {
    window.__TAURI__ = {
      core: {
        invoke: window.__TAURI_INTERNALS__.invoke,
      },
      event: {
        listen: function () { return Promise.resolve(function () {}); },
        once: function () { return Promise.resolve(function () {}); },
        emit: function () { return Promise.resolve(); },
      },
    };
  }

  console.log('[tauri-proxy] Installed. Proxying kernel_request -> http://localhost:8010/rpc/dev');
})();
`;
}

export { getProxyScript };
