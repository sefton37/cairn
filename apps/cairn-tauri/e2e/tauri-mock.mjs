/**
 * Tauri mock for Playwright e2e tests.
 *
 * Provides a realistic window.__TAURI_INTERNALS__ shim with hardcoded data
 * sourced from the actual talkingrock.db database. Inject via page.addInitScript().
 *
 * Data sourced: 2026-03-27
 *   - Acts: 4 acts (your-story, career-growth, health-fitness, family)
 *   - Scenes: 30 scenes across all acts
 *   - Memories: 5 approved memories, 3 pending
 *
 * Usage in a Playwright test:
 *
 *   const { getMockScript } = require('./tauri-mock');
 *   await page.addInitScript({ content: getMockScript() });
 *
 * Stateful write operations:
 *   Write methods (create, update, approve, reject, etc.) mutate an in-memory
 *   STATE object. Read methods serve from STATE, so writes are visible to
 *   subsequent reads within the same page lifecycle.
 *
 *   STATE resets on every page.goto() call because addInitScript re-injects
 *   this script, giving each test a clean slate via test.beforeEach.
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
  // Static seed data — real shapes from talkingrock.db (2026-03-27)
  // -------------------------------------------------------------------------

  const SEED_ACTS = [
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

  const SEED_SCENES_BY_ACT = {
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

  const SEED_ATTENTION_ITEMS = [
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

  const SEED_MEMORIES = [
    {
      memory_id: 'mem-001',
      narrative: 'User prefers deep work sessions in the morning before 10am.',
      memory_type: 'preference',
      status: 'approved',
      signal_count: 3,
      created_at: '2026-03-20T08:00:00Z',
      act_id: 'your-story',
    },
    {
      memory_id: 'mem-002',
      narrative: 'Half marathon race is on June 15th — training plan must peak by June 1st.',
      memory_type: 'commitment',
      status: 'approved',
      signal_count: 2,
      created_at: '2026-03-21T10:30:00Z',
      act_id: 'act-418f237064fc',
    },
    {
      memory_id: 'mem-003',
      narrative: 'Q2 platform migration deadline is April 30th with zero-downtime requirement.',
      memory_type: 'priority',
      status: 'approved',
      signal_count: 4,
      created_at: '2026-03-22T09:15:00Z',
      act_id: 'act-e8623a0da3ca',
    },
    {
      memory_id: 'mem-004',
      narrative: 'Emily tutoring sessions are every Wednesday at 4pm.',
      memory_type: 'fact',
      status: 'pending_review',
      signal_count: 1,
      created_at: '2026-03-25T14:00:00Z',
      act_id: 'your-story',
    },
    {
      memory_id: 'mem-005',
      narrative: 'User dislikes meetings on Friday afternoons — blocks focus time.',
      memory_type: 'preference',
      status: 'pending_review',
      signal_count: 2,
      created_at: '2026-03-26T11:45:00Z',
      act_id: 'act-e8623a0da3ca',
    },
    {
      memory_id: 'mem-006',
      narrative: 'Summer vacation is being planned for late July, Pacific Northwest road trip.',
      memory_type: 'fact',
      status: 'pending_review',
      signal_count: 1,
      created_at: '2026-03-27T09:00:00Z',
      act_id: 'act-02634cb2ca1c',
    },
    {
      memory_id: 'mem-007',
      narrative: 'DBT Group meetings are weekly, committed through end of Q2.',
      memory_type: 'commitment',
      status: 'approved',
      signal_count: 3,
      created_at: '2026-03-18T16:00:00Z',
      act_id: 'your-story',
    },
    {
      memory_id: 'mem-008',
      narrative: 'Career coaching with Kel and Shelley occurs every two weeks.',
      memory_type: 'fact',
      status: 'approved',
      signal_count: 2,
      created_at: '2026-03-19T13:30:00Z',
      act_id: 'your-story',
    },
  ];

  // KB content keyed by act_id — serves act-specific knowledge base markdown
  const SEED_KB_BY_ACT = {
    'your-story': [
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
    ].join('\\n'),

    'act-e8623a0da3ca': [
      '# Career Growth',
      '',
      '## Identity',
      '',
      'Engineering leader focused on platform reliability and team growth.',
      '',
      '## Current Priorities',
      '',
      '- Q2 Platform Migration: critical path, must not slip past April 30.',
      '- Tech Lead Mentoring: weekly 1:1s with junior engineers — system design focus.',
      '- Architecture Review Board: monthly, next agenda item is service mesh proposal.',
      '',
      '## Working Style',
      '',
      '- Deep work in the morning (before 10am) is protected time.',
      '- Documentation-first: write the doc before the code.',
      '- Prefer async communication over synchronous meetings.',
    ].join('\\n'),

    'act-418f237064fc': [
      '# Health & Fitness',
      '',
      '## Current Focus',
      '',
      '- Half Marathon Training: 16-week plan, week 8. Race date: June 15.',
      '- Weekly Meal Prep: Sunday sessions, reduces decision fatigue during the week.',
      '- Sleep Optimization: targeting 7.5 hrs/night, no screens after 9:30pm.',
      '',
      '## Metrics',
      '',
      '- Long run: Sundays (current: 12 miles)',
      '- Tempo runs: Tuesdays and Thursdays',
      '- Resting heart rate goal: below 55 bpm',
    ].join('\\n'),

    'act-02634cb2ca1c': [
      '# Family',
      '',
      '## Recurring Commitments',
      '',
      "- Kids' soccer: Tuesdays 4–5:30pm",
      "- Kids' swimming: Saturdays 9am",
      '- Emily tutoring: Wednesdays 4pm',
      '',
      '## Projects',
      '',
      '- Summer Vacation: Pacific Northwest road trip, late July. Book by April 30.',
      '- Home Office Renovation: awaiting contractor quotes (2 of 3 received).',
    ].join('\\n'),
  };

  // -------------------------------------------------------------------------
  // Stateful in-memory store — mutated by write operations
  // -------------------------------------------------------------------------

  // Deep-clone seed data so writes don't corrupt the originals
  var STATE = {
    acts: JSON.parse(JSON.stringify(SEED_ACTS)),
    scenesByAct: JSON.parse(JSON.stringify(SEED_SCENES_BY_ACT)),
    attention: JSON.parse(JSON.stringify(SEED_ATTENTION_ITEMS)),
    kbByAct: JSON.parse(JSON.stringify(SEED_KB_BY_ACT)),
    memories: JSON.parse(JSON.stringify(SEED_MEMORIES)),
    conversations: {
      active: null,   // null | conversation object
      list: [],
    },
    activeActId: 'your-story',
    nextId: 1000,  // monotonic counter for generated IDs
  };

  function nextId() {
    return 'mock-' + (++STATE.nextId);
  }

  // -------------------------------------------------------------------------
  // Derived helpers
  // -------------------------------------------------------------------------

  function getAllScenes() {
    return Object.values(STATE.scenesByAct).flat().map(function (s) {
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
  }

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

      // ---- Acts (read from STATE) ----

      case 'play/acts/list':
        return makeResult({
          active_act_id: STATE.activeActId,
          acts: STATE.acts,
        });

      case 'play/acts/set_active':
        STATE.activeActId = params.act_id || 'your-story';
        return makeResult({ ok: true });

      case 'play/acts/update': {
        const act = STATE.acts.find(function (a) { return a.act_id === params.act_id; });
        if (!act) return makeError(-32602, 'Act not found: ' + params.act_id);
        if (params.color !== undefined) act.color = params.color;
        if (params.title !== undefined) act.title = params.title;
        if (params.notes !== undefined) act.notes = params.notes;
        if (params.repo_path !== undefined) act.repo_path = params.repo_path;
        return makeResult({ act: act });
      }

      // play/acts/create — push a new act to STATE.acts, return it
      case 'play/acts/create': {
        const newAct = {
          act_id: 'act-' + nextId(),
          title: params.title || 'New Act',
          active: false,
          notes: params.notes || '',
          repo_path: null,
          color: params.color || null,
        };
        STATE.acts.push(newAct);
        STATE.scenesByAct[newAct.act_id] = [];
        return makeResult({ act: newAct });
      }

      case 'play/acts/delete': {
        const idx = STATE.acts.findIndex(function (a) { return a.act_id === params.act_id; });
        if (idx !== -1) {
          STATE.acts.splice(idx, 1);
          delete STATE.scenesByAct[params.act_id];
        }
        return makeResult({ ok: true });
      }

      case 'play/acts/assign_repo': {
        const act = STATE.acts.find(function (a) { return a.act_id === params.act_id; });
        if (act) act.repo_path = params.repo_path || null;
        return makeResult({ ok: true });
      }

      // ---- Scenes (read from STATE) ----

      // play/scenes/list — return scenes filtered by act_id from STATE
      case 'play/scenes/list': {
        const scenes = STATE.scenesByAct[params.act_id] || [];
        return makeResult({ scenes: scenes });
      }

      // play/scenes/list_all — return all scenes from STATE
      case 'play/scenes/list_all':
        return makeResult({ scenes: getAllScenes() });

      // play/scenes/create — push a new scene to STATE, return it
      case 'play/scenes/create': {
        if (!params.act_id) return makeError(-32602, 'act_id required');
        const newScene = {
          scene_id: 'scene-' + nextId(),
          act_id: params.act_id,
          title: params.title || 'New Scene',
          stage: params.stage || 'planning',
          notes: params.notes || '',
          link: null,
          calendar_event_id: null,
          recurrence_rule: null,
          thunderbird_event_id: null,
          disable_auto_complete: false,
        };
        if (!STATE.scenesByAct[params.act_id]) {
          STATE.scenesByAct[params.act_id] = [];
        }
        STATE.scenesByAct[params.act_id].push(newScene);
        return makeResult({ scene: newScene });
      }

      // play/scenes/update — find & update scene by scene_id (especially stage changes)
      case 'play/scenes/update': {
        var found = null;
        for (var actId in STATE.scenesByAct) {
          const list = STATE.scenesByAct[actId];
          for (var i = 0; i < list.length; i++) {
            if (list[i].scene_id === params.scene_id) {
              found = list[i];
              break;
            }
          }
          if (found) break;
        }
        if (!found) return makeError(-32602, 'Scene not found: ' + params.scene_id);
        if (params.title !== undefined) found.title = params.title;
        if (params.stage !== undefined) found.stage = params.stage;
        if (params.notes !== undefined) found.notes = params.notes;
        if (params.link !== undefined) found.link = params.link;
        return makeResult({ scene: found });
      }

      case 'play/scenes/delete': {
        const bucket = STATE.scenesByAct[params.act_id];
        if (bucket) {
          const di = bucket.findIndex(function (s) { return s.scene_id === params.scene_id; });
          if (di !== -1) bucket.splice(di, 1);
        }
        return makeResult({ ok: true });
      }

      // ---- KB / Me ----

      // play/kb/read — return different content based on act_id
      case 'play/kb/read': {
        const actKey = params.act_id || 'your-story';
        const kbText = STATE.kbByAct[actKey] || ('# ' + actKey + '\\n\\nNo content yet.');
        return makeResult({
          path: params.path || 'kb.md',
          text: kbText,
        });
      }

      case 'play/me/read':
        return makeResult({ markdown: STATE.kbByAct['your-story'] });

      case 'play/me/write':
        STATE.kbByAct['your-story'] = params.text || '';
        return makeResult({ ok: true });

      // play/kb/write_apply — store markdown content keyed by act_id, return success
      case 'play/kb/write_apply': {
        const wActId = params.act_id || 'your-story';
        STATE.kbByAct[wActId] = params.text || '';
        return makeResult({ ok: true, sha256: 'mock-sha256-' + nextId() });
      }

      case 'play/kb/write_preview': {
        const wpActId = params.act_id || 'your-story';
        const currentText = STATE.kbByAct[wpActId] || '';
        return makeResult({
          preview: params.text || '',
          expected_sha256_current: 'mock-sha256-preview-' + wpActId,
          current_sha256: 'mock-sha256-current-' + wpActId,
          current_length: currentText.length,
          new_length: (params.text || '').length,
        });
      }

      // ---- Attachments ----

      case 'play/attachments/list':
        return makeResult({ attachments: [] });

      case 'play/attachments/add':
        return makeResult({ ok: true });

      case 'play/attachments/remove':
        return makeResult({ ok: true });

      // ---- Pages ----

      case 'play/pages/list':
      case 'play/pages/tree':
        return makeResult({ pages: [] });

      // ---- CAIRN Attention (read from STATE) ----

      case 'cairn/attention':
        return makeResult({
          count: STATE.attention.length,
          items: STATE.attention,
          health_warnings: [],
        });

      // cairn/attention/reorder — reorder STATE.attention based on ordered_scene_ids
      case 'cairn/attention/reorder': {
        const orderedIds = params.ordered_scene_ids || [];
        if (orderedIds.length > 0) {
          // Sort STATE.attention so that items with scene_id matching the ordered list
          // appear first in the given order; remaining items stay at the end.
          const idIndex = {};
          orderedIds.forEach(function (id, i) { idIndex[id] = i; });
          STATE.attention.sort(function (a, b) {
            const ia = idIndex[a.scene_id] !== undefined ? idIndex[a.scene_id] : 9999;
            const ib = idIndex[b.scene_id] !== undefined ? idIndex[b.scene_id] : 9999;
            return ia - ib;
          });
        }
        return makeResult({ ok: true });
      }

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
          message_count: STATE.conversations.active ? (STATE.conversations.active.message_count || 0) : 0,
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

      // ---- Conversation Lifecycle (stateful) ----

      // lifecycle/conversations/get_active — return STATE.conversations.active
      case 'lifecycle/conversations/get_active':
        return makeResult({ conversation: STATE.conversations.active });

      // lifecycle/conversations/start — create active conversation (enforce singleton)
      case 'lifecycle/conversations/start': {
        if (STATE.conversations.active) {
          // Singleton: return existing conversation if already active
          return makeResult({ conversation: STATE.conversations.active });
        }
        const conv = {
          conversation_id: 'mock-conv-' + nextId(),
          status: 'active',
          started_at: new Date().toISOString(),
          message_count: 0,
        };
        STATE.conversations.active = conv;
        STATE.conversations.list.push(conv);
        return makeResult({ conversation: conv });
      }

      // lifecycle/conversations/close — close active conversation
      case 'lifecycle/conversations/close':
        if (STATE.conversations.active) {
          STATE.conversations.active.status = 'closed';
          STATE.conversations.active = null;
        }
        return makeResult({ ok: true });

      // ---- Chat (async polling pattern) ----

      // cairn/chat_async — start async chat, return a chat_id immediately
      case 'cairn/chat_async': {
        // Auto-start a conversation if none is active
        if (!STATE.conversations.active) {
          const autoConv = {
            conversation_id: 'mock-conv-' + nextId(),
            status: 'active',
            started_at: new Date().toISOString(),
            message_count: 0,
          };
          STATE.conversations.active = autoConv;
          STATE.conversations.list.push(autoConv);
        }
        STATE.conversations.active.message_count = (STATE.conversations.active.message_count || 0) + 1;
        const chatId = 'mock-chat-' + nextId();
        // Store the pending result so chat_status can retrieve it
        window.__mockPendingChats = window.__mockPendingChats || {};
        const userText = params.text || '';
        const attentionItem = STATE.attention[0];
        const responseText = attentionItem
          ? ('Based on your schedule, I\\'d recommend focusing on ' + attentionItem.title +
             '. Your Story mentions career coaching as an ongoing commitment. What would you like to tackle first?')
          : 'Happy to help! What would you like to focus on?';
        window.__mockPendingChats[chatId] = {
          status: 'complete',
          result: {
            response: responseText,
            conversation_id: STATE.conversations.active.conversation_id,
            message_id: 'msg-' + nextId(),
            user_message_id: 'msg-user-' + nextId(),
            thinking_steps: [],
            tool_calls: [],
            message_type: 'response',
          },
        };
        return makeResult({ chat_id: chatId, status: 'processing' });
      }

      // cairn/chat_status — poll for chat completion
      case 'cairn/chat_status': {
        const pending = (window.__mockPendingChats || {})[params.chat_id];
        if (!pending) {
          return makeResult({ status: 'error', error: 'chat_id not found' });
        }
        return makeResult(pending);
      }

      // chat/respond — legacy synchronous chat (kept for tests that use it directly)
      case 'chat/respond': {
        const firstItem = STATE.attention[0];
        const syncResponse = firstItem
          ? ('Based on your schedule, I\\'d recommend focusing on ' + firstItem.title +
             '. Your Story mentions priorities around job search and career coaching.')
          : 'Happy to help! What would you like to focus on?';
        return makeResult({
          response: syncResponse,
          conversation_id: STATE.conversations.active
            ? STATE.conversations.active.conversation_id
            : 'mock-conv-standalone',
          message_id: 'msg-' + nextId(),
          thinking_steps: [],
          tool_calls: [],
        });
      }

      // ---- Memories (stateful) ----

      case 'memories/list':
      case 'memories/search':
        return makeResult({ memories: STATE.memories.filter(function (m) { return m.status === 'approved'; }) });

      // lifecycle/memories/pending — return memories with status=pending_review
      case 'lifecycle/memories/pending':
        return makeResult({
          memories: STATE.memories.filter(function (m) { return m.status === 'pending_review'; }),
        });

      // lifecycle/memories/by_act_page — memories for a given act (for MemoryBlock)
      case 'lifecycle/memories/by_act_page':
        return makeResult({
          memories: STATE.memories.filter(function (m) {
            return !params.act_id || m.act_id === params.act_id;
          }),
        });

      // lifecycle/memories/approve — change memory status to approved
      case 'lifecycle/memories/approve': {
        const mem = STATE.memories.find(function (m) { return m.memory_id === params.memory_id; });
        if (mem) mem.status = 'approved';
        return makeResult({ ok: true, memory_id: params.memory_id });
      }

      // lifecycle/memories/reject — change memory status to rejected
      case 'lifecycle/memories/reject': {
        const mem2 = STATE.memories.find(function (m) { return m.memory_id === params.memory_id; });
        if (mem2) mem2.status = 'rejected';
        return makeResult({ ok: true, memory_id: params.memory_id });
      }

      case 'lifecycle/memories/ensure_page':
        return makeResult({ page_id: 'page-memories-' + (params.act_id || 'your-story') });

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

  console.log('[tauri-mock] Installed. Session: kellogg. Stateful mock active.');
})();
`;
}

export { getMockScript };
