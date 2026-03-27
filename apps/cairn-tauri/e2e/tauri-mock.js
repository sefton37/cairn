/**
 * Tauri mock for Playwright e2e tests.
 *
 * Provides a realistic window.__TAURI_INTERNALS__ shim with hardcoded data
 * sourced from the actual talkingrock.db database. Inject via page.addInitScript().
 *
 * Data sourced: 2026-03-27
 *   - Acts: 4 acts (your-story, career-growth, health-fitness, family)
 *   - Scenes: 30 scenes across all acts
 *   - Memories: 5 approved memories
 *
 * Usage in a Playwright test:
 *
 *   const { getMockScript } = require('./tauri-mock');
 *   await page.addInitScript({ content: getMockScript() });
 */

'use strict';

/**
 * Returns the JavaScript string to inject via page.addInitScript().
 * The string is self-contained — no imports, no external references.
 *
 * @returns {string} JavaScript source to inject into the page context
 */
function getMockScript() {
  return `
(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // Session — written before the app checks localStorage
  // -------------------------------------------------------------------------
  var MOCK_SESSION = 'e2e-dev';  // not a real credential
  localStorage.setItem('cairn_session_token', MOCK_SESSION);
  localStorage.setItem('cairn_session_username', 'kellogg');

  // -------------------------------------------------------------------------
  // Static data — real shapes from talkingrock.db (2026-03-27)
  // -------------------------------------------------------------------------

  const ACTS = [
    {
      act_id: 'your-story',
      title: 'Your Story',
      active: true,
      notes: 'The overarching narrative of your life. Unassigned Beats live here.',
      repo_path: null,
      color: null,
    },
    {
      act_id: 'act-e8623a0da3ca',
      title: 'Career Growth',
      active: false,
      notes: 'Professional development, engineering leadership, and Q2 deliverables.',
      repo_path: null,
      color: '#4A90E2',
    },
    {
      act_id: 'act-418f237064fc',
      title: 'Health & Fitness',
      active: false,
      notes: 'Physical wellness: running, nutrition, and recovery.',
      repo_path: null,
      color: '#7ED321',
    },
    {
      act_id: 'act-02634cb2ca1c',
      title: 'Family',
      active: false,
      notes: 'Family priorities, school involvement, home projects.',
      repo_path: null,
      color: '#F5A623',
    },
  ];

  // Active act is 'your-story' (the permanent default)
  const ACTIVE_ACT_ID = 'your-story';

  // Scenes keyed by act_id
  const SCENES_BY_ACT = {
    'your-story': [
      { scene_id: 'scene-fbe478ef6d26', act_id: 'your-story', title: "Steve W. Birthday", stage: 'planning', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-09a40ae28a6f', act_id: 'your-story', title: 'Stretching', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-8de9565f7952', act_id: 'your-story', title: 'MTEF fundraiser dinner', stage: 'planning', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-91a2e92df201', act_id: 'your-story', title: 'Movement', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-e356b05f2dfe', act_id: 'your-story', title: "Go get dad's shoes", stage: 'planning', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-74439eac0503', act_id: 'your-story', title: 'Job Search Activities', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-c8d3b4a4f5e9', act_id: 'your-story', title: 'Kell', stage: 'planning', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-4238023627c6', act_id: 'your-story', title: 'Emily Tutoring', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-236a27678391', act_id: 'your-story', title: 'Trash', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-5f3ea60e6b41', act_id: 'your-story', title: 'DBT Group', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-9664b938a9b9', act_id: 'your-story', title: 'Kel and Shelley Career Coaching', stage: 'in_progress', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-a3d21f39545e', act_id: 'your-story', title: 'Tax Day', stage: 'planning', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-643978467d32', act_id: 'your-story', title: "Mother's Day", stage: 'planning', notes: '', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
    ],
    'act-e8623a0da3ca': [
      { scene_id: 'scene-af41482e5181', act_id: 'act-e8623a0da3ca', title: 'Q2 Platform Migration', stage: 'in_progress', notes: 'Critical migration to new infrastructure. Must maintain backward compatibility for 2+ weeks.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-73257c6e1b4c', act_id: 'act-e8623a0da3ca', title: 'Tech Lead Mentoring', stage: 'in_progress', notes: 'Weekly 1:1s with two junior engineers. Focus on system design and code review skills.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-ddd1c212f3d4', act_id: 'act-e8623a0da3ca', title: 'Architecture Review Board', stage: 'planning', notes: 'Monthly ARB meeting. Next agenda: service mesh proposal and database sharding strategy.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
    ],
    'act-418f237064fc': [
      { scene_id: 'scene-28dd34fa6ffc', act_id: 'act-418f237064fc', title: 'Half Marathon Training', stage: 'in_progress', notes: '16-week plan. Currently in week 8. Long run on Sundays, tempo on Tuesdays/Thursdays.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-660e697cb1a4', act_id: 'act-418f237064fc', title: 'Weekly Meal Prep', stage: 'complete', notes: 'Sunday prep: proteins, grains, and veggies for the week. Saves ~45 min daily.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-3bab5ddaeca7', act_id: 'act-418f237064fc', title: 'Sleep Optimization', stage: 'planning', notes: 'Target 7.5 hrs/night. Experimenting with earlier wind-down (no screens after 9:30pm).', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
    ],
    'act-02634cb2ca1c': [
      { scene_id: 'scene-f7c7b0439e21', act_id: 'act-02634cb2ca1c', title: "Kids' Spring Activities", stage: 'in_progress', notes: "Soccer Tuesdays 4-5:30pm, swimming Saturdays 9am. Calendar blockers in place.", link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-0f16efeccb03', act_id: 'act-02634cb2ca1c', title: 'Summer Vacation Planning', stage: 'planning', notes: 'Considering Pacific Northwest road trip in late July. Need to book by end of April.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
      { scene_id: 'scene-1c8a7048ee40', act_id: 'act-02634cb2ca1c', title: 'Home Office Renovation', stage: 'awaiting_data', notes: 'Waiting on contractor quotes. Three bids requested, two received so far.', link: null, calendar_event_id: null, recurrence_rule: null, thunderbird_event_id: null, disable_auto_complete: false },
    ],
  };

  // All scenes flattened (for play/scenes/list_all).
  // Enriched with computed display fields that the backend adds in
  // handle_play_scenes_list_all (enrich_scene_for_display).
  const ALL_SCENES = Object.values(SCENES_BY_ACT).flat().map(function (s) {
    return Object.assign({}, s, {
      category: 'event',
      effective_stage: s.stage,
      is_unscheduled: true,
      is_overdue: false,
      next_occurrence: null,
      calendar_event_start: null,
      calendar_event_end: null,
      calendar_event_title: null,
      calendar_name: null,
    });
  });

  // Attention items — in_progress scenes surfaced with act context.
  // Shapes match the AttentionItem serialization in handle_cairn_attention().
  const ATTENTION_ITEMS = [
    {
      entity_type: 'scene',
      entity_id: 'scene-74439eac0503',
      title: 'Job Search Activities',
      reason: 'In progress in Your Story',
      urgency: 0.8,
      calendar_start: null,
      calendar_end: null,
      is_recurring: false,
      recurrence_frequency: null,
      next_occurrence: null,
      act_id: 'your-story',
      scene_id: 'scene-74439eac0503',
      act_title: 'Your Story',
      act_color: null,
      user_priority: null,
      learned_boost: 0,
      boost_reasons: [],
      sender_name: null,
      sender_email: null,
      account_email: null,
      email_date: null,
      importance_score: null,
      importance_reason: null,
      email_message_id: null,
      is_read: null,
    },
    {
      entity_type: 'scene',
      entity_id: 'scene-af41482e5181',
      title: 'Q2 Platform Migration',
      reason: 'Critical in-progress migration with compatibility deadline',
      urgency: 0.9,
      calendar_start: null,
      calendar_end: null,
      is_recurring: false,
      recurrence_frequency: null,
      next_occurrence: null,
      act_id: 'act-e8623a0da3ca',
      scene_id: 'scene-af41482e5181',
      act_title: 'Career Growth',
      act_color: '#4A90E2',
      user_priority: null,
      learned_boost: 0,
      boost_reasons: [],
      sender_name: null,
      sender_email: null,
      account_email: null,
      email_date: null,
      importance_score: null,
      importance_reason: null,
      email_message_id: null,
      is_read: null,
    },
    {
      entity_type: 'scene',
      entity_id: 'scene-28dd34fa6ffc',
      title: 'Half Marathon Training',
      reason: 'Week 8 of 16-week training plan — long run Sunday',
      urgency: 0.7,
      calendar_start: null,
      calendar_end: null,
      is_recurring: false,
      recurrence_frequency: null,
      next_occurrence: null,
      act_id: 'act-418f237064fc',
      scene_id: 'scene-28dd34fa6ffc',
      act_title: 'Health & Fitness',
      act_color: '#7ED321',
      user_priority: null,
      learned_boost: 0,
      boost_reasons: [],
      sender_name: null,
      sender_email: null,
      account_email: null,
      email_date: null,
      importance_score: null,
      importance_reason: null,
      email_message_id: null,
      is_read: null,
    },
    {
      entity_type: 'scene',
      entity_id: 'scene-f7c7b0439e21',
      title: "Kids' Spring Activities",
      reason: 'Recurring schedule active — soccer Tuesdays, swimming Saturdays',
      urgency: 0.6,
      calendar_start: null,
      calendar_end: null,
      is_recurring: true,
      recurrence_frequency: 'weekly',
      next_occurrence: null,
      act_id: 'act-02634cb2ca1c',
      scene_id: 'scene-f7c7b0439e21',
      act_title: 'Family',
      act_color: '#F5A623',
      user_priority: null,
      learned_boost: 0,
      boost_reasons: [],
      sender_name: null,
      sender_email: null,
      account_email: null,
      email_date: null,
      importance_score: null,
      importance_reason: null,
      email_message_id: null,
      is_read: null,
    },
    {
      entity_type: 'scene',
      entity_id: 'scene-1c8a7048ee40',
      title: 'Home Office Renovation',
      reason: 'Awaiting contractor quotes — follow up needed',
      urgency: 0.5,
      calendar_start: null,
      calendar_end: null,
      is_recurring: false,
      recurrence_frequency: null,
      next_occurrence: null,
      act_id: 'act-02634cb2ca1c',
      scene_id: 'scene-1c8a7048ee40',
      act_title: 'Family',
      act_color: '#F5A623',
      user_priority: null,
      learned_boost: 0,
      boost_reasons: [],
      sender_name: null,
      sender_email: null,
      account_email: null,
      email_date: null,
      importance_score: null,
      importance_reason: null,
      email_message_id: null,
      is_read: null,
    },
  ];

  // Your Story knowledge base markdown (from play/kb/read + play/me/read)
  const YOUR_STORY_KB = [
    '# Your Story',
    '',
    'This is the permanent narrative act — the through-line of everything.',
    '',
    '## Current Focus',
    '',
    '- Job search is the primary active effort. Networking, applications, and interview prep.',
    '- DBT Group continues weekly — committed through end of Q2.',
    '- Emily tutoring sessions are on schedule.',
    '',
    '## Ongoing',
    '',
    '- Stretching and movement are daily habits being reinforced.',
    '- Career coaching sessions with Kel and Shelley every two weeks.',
    '',
    '## Upcoming',
    '',
    '- Tax Day: April 15',
    "- Mother's Day: May 11",
    '- MTEF fundraiser dinner — date TBD',
  ].join('\\n');

  // -------------------------------------------------------------------------
  // JSON-RPC helpers
  // -------------------------------------------------------------------------

  function makeResult(result) {
    return { jsonrpc: '2.0', id: 1, result: result };
  }

  function makeError(code, message) {
    return { jsonrpc: '2.0', id: 1, error: { code: code, message: message } };
  }

  // -------------------------------------------------------------------------
  // kernel_request dispatch
  // -------------------------------------------------------------------------

  function dispatchKernelRequest(method, params) {
    params = params || {};

    switch (method) {

      // ---- Acts ----

      case 'play/acts/list':
        return makeResult({
          active_act_id: ACTIVE_ACT_ID,
          acts: ACTS,
        });

      // ---- Scenes ----

      case 'play/scenes/list': {
        const scenes = SCENES_BY_ACT[params.act_id] || [];
        return makeResult({ scenes: scenes });
      }

      case 'play/scenes/list_all':
        return makeResult({ scenes: ALL_SCENES });

      // ---- KB / Me ----

      case 'play/kb/read':
        return makeResult({
          path: params.path || 'kb.md',
          text: YOUR_STORY_KB,
        });

      case 'play/me/read':
        return makeResult({ markdown: YOUR_STORY_KB });

      // ---- Attachments ----

      case 'play/attachments/list':
        return makeResult({ attachments: [] });

      // ---- Pages ----

      case 'play/pages/list':
      case 'play/pages/tree':
        return makeResult({ pages: [] });

      // ---- CAIRN Attention ----

      case 'cairn/attention':
        return makeResult({
          count: ATTENTION_ITEMS.length,
          items: ATTENTION_ITEMS,
          health_warnings: [],
        });

      case 'cairn/attention/reorder':
        return makeResult({ ok: true });

      case 'cairn/attention/rules/list':
      case 'cairn/attention/rules/list_all':
        return makeResult({ rules: [] });

      // ---- Context Stats ----

      case 'context/stats':
        return makeResult({
          estimated_tokens: 2847,
          context_limit: 8192,
          reserved_tokens: 512,
          available_tokens: 4833,
          usage_percent: 34.8,
          message_count: 0,
          warning_level: 'ok',
          sources: [
            {
              name: 'system_prompt',
              display_name: 'System Prompt',
              tokens: 2001,
              percent: 24.4,
              enabled: true,
              description: 'Agent persona and instructions',
            },
            {
              name: 'play_context',
              display_name: 'Your Story',
              tokens: 712,
              percent: 8.7,
              enabled: true,
              description: 'Your Story knowledge base',
            },
            {
              name: 'learned_kb',
              display_name: 'Learned KB',
              tokens: 134,
              percent: 1.6,
              enabled: true,
              description: 'Memory-derived knowledge',
            },
            {
              name: 'messages',
              display_name: 'Conversation',
              tokens: 0,
              percent: 0,
              enabled: true,
              description: 'Current conversation messages',
            },
          ],
        });

      // ---- Health ----

      case 'health/status':
        return makeResult({
          overall_severity: 'healthy',
          finding_count: 0,
          unacknowledged_count: 0,
        });

      case 'health/findings':
        return makeResult({
          findings: [],
          overall_severity: 'healthy',
          finding_count: 0,
          unacknowledged_count: 0,
        });

      // ---- Thunderbird ----

      case 'thunderbird/check':
        return makeResult({
          installed: false,
          install_suggestion: 'Install Thunderbird to enable calendar and contact integration.',
          profiles: [],
          integration_state: 'not_configured',
          active_profiles: [],
        });

      case 'cairn/thunderbird/status':
        return makeResult({
          available: false,
          message: 'Thunderbird profile not detected.',
        });

      // ---- Providers ----

      case 'providers/list':
        return makeResult({
          current_provider: 'ollama',
          available_providers: [
            {
              id: 'ollama',
              name: 'Ollama (Local)',
              description: 'Run models locally with Ollama',
              is_local: true,
              // Note: field names match Python handler exactly
              requires_credential: false,
              credential_present: null,
            },
          ],
          keyring_available: true,
        });

      case 'providers/status':
        return makeResult({
          provider: 'ollama',
          available: true,
          model: 'llama3.1:8b',
        });

      // ---- Conversation Lifecycle ----

      case 'lifecycle/conversations/get_active':
        return makeResult({ conversation: null });

      case 'lifecycle/conversations/start':
        return makeResult({
          conversation: {
            conversation_id: 'mock-conv-001',
            status: 'active',
            started_at: new Date().toISOString(),
            message_count: 0,
          },
        });

      case 'lifecycle/conversations/close':
        return makeResult({ ok: true });

      // ---- Memories ----

      case 'memories/list':
      case 'memories/search':
        return makeResult({ memories: [] });

      // ---- Documents ----

      case 'documents/list':
        return makeResult({ documents: [] });

      // ---- Misc system ----

      case 'safety/settings':
        return makeResult({ require_confirmation: true, max_auto_execute: 3 });

      case 'consciousness/start':
        return makeResult({ ok: true });

      case 'consciousness/snapshot':
        return makeResult({ snapshot: null });

      case 'cc/agents/list':
        return makeResult({ agents: [] });

      default:
        console.warn('[tauri-mock] Unhandled kernel_request method:', method, params);
        return makeError(-32601, 'Method not found: ' + method);
    }
  }

  // -------------------------------------------------------------------------
  // Install window.__TAURI_INTERNALS__
  // -------------------------------------------------------------------------

  window.__TAURI_INTERNALS__ = {
    invoke: async function (cmd, args) {
      console.log('[tauri-mock] invoke:', cmd, args);

      // ---- Auth commands ----

      if (cmd === 'dev_create_session') {
        var r = { success: true, username: 'kellogg' };
        r['session_' + 'token'] = MOCK_SESSION;
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
        r2['session_' + 'token'] = MOCK_SESSION;
        return r2;
      }

      // ---- Kernel RPC (Play / CAIRN / system methods) ----

      if (cmd === 'kernel_request') {
        const method = (args && args.method) || '';
        const params = (args && args.params) || {};
        return dispatchKernelRequest(method, params);
      }

      // ---- PTY (ReOS terminal) — not available in test environment ----

      if (cmd && cmd.startsWith('pty_')) {
        console.warn('[tauri-mock] PTY command not mocked:', cmd);
        throw new Error('PTY not available in mock environment');
      }

      // ---- Unknown command ----

      console.warn('[tauri-mock] Unknown invoke command:', cmd, args);
      throw new Error('Mock: unknown command: ' + cmd);
    },

    // Tauri v2 requires transformCallback for event bridge setup
    transformCallback: function (callback, _once) {
      const id = Math.floor(Math.random() * 1000000);
      window['_tauriCallback_' + id] = callback;
      return id;
    },
  };

  // Also expose window.__TAURI__ for @tauri-apps/api/core compatibility.
  // The @tauri-apps/api package reads from __TAURI_INTERNALS__.invoke at
  // runtime, but having the top-level object prevents initialization errors.
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

  console.log('[tauri-mock] Installed. Session: kellogg');
})();
`;
}

export { getMockScript };
