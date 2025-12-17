"""
M1b Bifocal System Architecture Diagram

════════════════════════════════════════════════════════════════════════════════

                        ┌─────────────────────────────┐
                        │  VSCode Editor (Primary)    │
                        │  ├─ File Focus              │
                        │  ├─ Saves                   │
                        │  ├─ Git Branch/Commits      │
                        │  └─ Time in File            │
                        └──────────────┬──────────────┘
                                       │
                    ┌──────────────────┘
                    │
                    ▼
        ┌────────────────────────────────┐
        │ VSCode Extension               │
        │ (vscode-extension/extension.js)│
        │                                │
        │ ├─ getGitInfo()                │
        │ ├─ fileEventHistory tracking   │
        │ ├─ Enhanced onDidChangeEditor  │
        │ ├─ 10-sec heartbeat interval   │
        │ └─ Project context extraction  │
        └──────────────┬─────────────────┘
                       │
            [Events: file switch, heartbeat,
             git info, timestamps, project]
                       │
                       ▼
        ┌────────────────────────────────┐
        │ FastAPI Event Service          │
        │ POST /events                   │
        │ (src/reos/app.py)              │
        └──────────────┬─────────────────┘
                       │
                       ▼
        ┌────────────────────────────────┐
        │ SQLite Local Store             │
        │ (src/reos/db.py)               │
        │                                │
        │ ├─ events table                │
        │ │  └─ Raw VSCode activity      │
        │ ├─ sessions table              │
        │ ├─ classifications table       │
        │ └─ audit_log table             │
        │                                │
        │ 📦 Location: .reos-data/       │
        │    (git-ignored, user-owned)   │
        └──────────────┬─────────────────┘
                       │
            ┌──────────┼──────────┬──────────┐
            │          │          │          │
            ▼          ▼          ▼          ▼
    ┌─────────────┐ ┌──────────────────┐ ┌─────────────────────┐
    │ Attention   │ │ Command Registry │ │ ReOS GUI            │
    │ Module      │ │ (commands.py)    │ │ (gui/main_window.py)│
    │ (NEW!)      │ │                  │ │                     │
    │             │ │ ├─ reflect_      │ │ ┌─────────────────┐ │
    │ ├─ Calculate│ │   recent()       │ │ │ Nav Pane        │ │
    │   fragm.    │ │ ├─ inspect_      │ │ │ ├─ Projects     │ │
    │   (0.0-1.0) │ │   session()      │ │ │ ├─ Fragmentation│ │
    │ │           │ │ ├─ list_         │ │ │ │   Score       │ │
    │ ├─ Get      │ │   events()       │ │ │ ├─ Duration     │ │
    │   session   │ │ └─ note()        │ │ │ └─ Auto-refresh │ │
    │   summary   │ │                  │ │ │    (30 sec)     │ │
    │ │           │ │ (Real handlers   │ │ └─────────────────┘ │
    │ ├─ Classify │ │  using attention)│ │ ┌─────────────────┐ │
    │   pattern   │ │                  │ │ │ Chat Pane       │ │
    │ │           │ │                  │ │ │ (Ready for LLM) │ │
    │ └─ Output:  │ │                  │ │ └─────────────────┘ │
    │   "Your     │ │                  │ │ ┌─────────────────┐ │
    │    attention│ │                  │ │ │ Inspection Pane │ │
    │    is       │ │                  │ │ │ (Reasoning)     │ │
    │    scattered│ │                  │ │ └─────────────────┘ │
    │    What was │ │                  │ │                     │
    │    your     │ │                  │ │ ┌─────────────────┐ │
    │    intention│ │                  │ │ │ LLM Integration │ │
    │   ?"        │ │                  │ │ │ (Ollama)        │ │
    │             │ │                  │ │ │ [Coming M2]     │ │
    └─────────────┘ └──────────────────┘ └─────────────────────┘
         │                │
         │ Queries        │ Uses for
         │ SQLite         │ reasoning
         └────────────┬───┘
                      │
                      ▼
        ┌───────────────────────────────┐
        │ User Reflection               │
        │ ├─ Reads metrics              │
        │ ├─ Sees projects              │
        │ ├─ Responds to prompts        │
        │ └─ Reflects on patterns       │
        │                               │
        │ ("This switching was          │
        │  intentional exploration")    │
        └───────────────┬───────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ SQLite audit_log              │
        │ (Learning: stores intentions) │
        └───────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════

Key Design Principles:

1. BIFOCAL PATTERN
   - VSCode = Primary workspace (user stays here)
   - ReOS = Companion observer (runs in background)
   - No interruption; observation only

2. LOCAL-FIRST
   - All data in .reos-data/ (SQLite)
   - No cloud transmission without consent
   - User owns all their attention data

3. TRANSPARENT METRICS
   - Every number shows how it's calculated
   - Fragmentation: explicit window + threshold
   - No black-box AI; all rules explainable

4. COMPASSIONATE LANGUAGE
   - Never: "distracted", "bad", "productive"
   - Always: "fragmented/coherent", "what was your intention?"
   - Ask questions; don't judge

5. REAL-TIME OBSERVATION
   - VSCode extension streams events instantly
   - SQLite updated sub-second
   - ReOS nav pane refreshes every 30 sec

6. PROACTIVE (not reactive)
   - Detect patterns → ask reflection questions
   - Example: "8 switches in 5 min. Settle or explore?"
   - User chooses their attention; ReOS aids awareness

════════════════════════════════════════════════════════════════════════════════

Data Types Flowing:

VSCode Extension sends:
  {
    kind: "active_editor" | "heartbeat" | "save" | "git_change",
    projectName: "backend",
    uri: "file:///dev/backend/main.py",
    timeInFileSeconds: 120,
    editorChangeTime: "2024-12-17T14:59:45Z",
    workspaceFolder: "/dev/backend"
  }

SQLite events table stores:
  id, source, kind, ts, payload_metadata, note, created_at, ingested_at

Attention Module computes:
  {
    fragmentation_score: 0.65,      # 0.0 = coherent, 1.0 = highly fragmented
    switch_count: 8,                 # file switches in window
    unique_files: 3,
    explanation: "Fragmented attention: 8 switches across 3 files..."
  }

ReOS Nav Pane displays:
  Fragmentation: 65%
  backend: 3 files, 45m
  frontend: 2 files, 30m

════════════════════════════════════════════════════════════════════════════════
"""

# This file is documentation. Run tests to verify the system works:
#   pytest tests/ -v
# All 8 tests should pass (5 existing + 3 new attention tests)
