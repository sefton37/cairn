# Execution Engine

> **Safe execution of atomic operations with undo capability.**

After verification, atomic operations are executed through the execution engine. This system captures state, executes safely, and provides undo capability.

---

## Execution Flow

```
Verified Operation
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXECUTION ENGINE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  1. STATE CAPTURE (Before)                                 │ │
│  │     • File contents (if file operation)                    │ │
│  │     • Process state (if process operation)                 │ │
│  │     • System metrics                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                            │                                     │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  2. EXECUTION                                              │ │
│  │     • Route to appropriate executor                        │ │
│  │     • Apply timeout and resource limits                    │ │
│  │     • Capture stdout/stderr/exit code                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                            │                                     │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  3. STATE CAPTURE (After)                                  │ │
│  │     • Affected files                                       │ │
│  │     • Spawned processes                                    │ │
│  │     • Resource usage                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                            │                                     │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  4. REVERSIBILITY ANALYSIS                                 │ │
│  │     • Determine if operation is reversible                 │ │
│  │     • Generate undo commands if applicable                 │ │
│  │     • Store recovery information                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   Operation Complete
   (with undo capability)
```

---

## Executors

Operations are routed to specialized executors based on their classification:

### Shell Executor

For `process` destination operations.

```python
class ShellExecutor:
    """Execute shell commands with safety constraints."""

    def execute(self, command: str, context: dict) -> ExecutionResult:
        # Apply timeout
        timeout = min(context.get('timeout', 120), 600)  # Max 10 minutes

        # Execute with subprocess
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=context.get('working_dir')
        )

        return ExecutionResult(
            success=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout.decode(),
            stderr=result.stderr.decode(),
            duration_ms=elapsed_ms
        )
```

### Python Executor

For Python code execution.

```python
class PythonExecutor:
    """Execute Python code in isolated context."""

    def execute(self, code: str, context: dict) -> ExecutionResult:
        # Create isolated namespace
        namespace = {'__builtins__': __builtins__}

        # Inject context
        namespace.update(context.get('python_context', {}))

        # Execute
        try:
            exec(code, namespace)
            return ExecutionResult(success=True)
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))
```

### File Executor

For `file` destination operations.

```python
class FileExecutor:
    """Execute file operations with backup."""

    def execute(self, operation: FileOperation, context: dict) -> ExecutionResult:
        target_path = operation.target_path

        # Backup before modification
        if os.path.exists(target_path):
            backup_path = self._create_backup(target_path)
        else:
            backup_path = None

        # Execute operation
        if operation.action == 'write':
            with open(target_path, 'w') as f:
                f.write(operation.content)
        elif operation.action == 'append':
            with open(target_path, 'a') as f:
                f.write(operation.content)
        elif operation.action == 'delete':
            os.remove(target_path)

        return ExecutionResult(
            success=True,
            files_affected=[target_path],
            backup_path=backup_path
        )
```

---

## State Capture

### Before Execution

Capture relevant state to enable undo:

```python
def capture_state_before(operation: AtomicOperation, context: dict) -> dict:
    """Capture system state before execution."""

    state = {
        'timestamp': datetime.now().isoformat(),
        'operation_id': operation.block_id
    }

    # File state
    if operation.destination_type == 'file':
        target_files = _extract_target_files(operation)
        state['files'] = {}
        for f in target_files:
            if os.path.exists(f):
                state['files'][f] = {
                    'exists': True,
                    'content_hash': _hash_file(f),
                    'mtime': os.path.getmtime(f),
                    'backup_path': _create_backup(f)
                }
            else:
                state['files'][f] = {'exists': False}

    # Process state
    if operation.destination_type == 'process':
        state['processes'] = _snapshot_processes()
        state['system_metrics'] = {
            'memory_used': psutil.virtual_memory().used,
            'cpu_percent': psutil.cpu_percent()
        }

    return state
```

### After Execution

Capture state changes:

```python
def capture_state_after(operation: AtomicOperation, state_before: dict) -> dict:
    """Capture state after execution."""

    state = {
        'timestamp': datetime.now().isoformat(),
        'operation_id': operation.block_id
    }

    # File changes
    if 'files' in state_before:
        state['files'] = {}
        for f, before in state_before['files'].items():
            if os.path.exists(f):
                state['files'][f] = {
                    'exists': True,
                    'content_hash': _hash_file(f),
                    'changed': _hash_file(f) != before.get('content_hash')
                }
            else:
                state['files'][f] = {
                    'exists': False,
                    'was_deleted': before.get('exists', False)
                }

    # Process changes
    if 'processes' in state_before:
        current_processes = _snapshot_processes()
        state['new_processes'] = [
            p for p in current_processes
            if p not in state_before['processes']
        ]

    return state
```

---

## Reversibility Analysis

Determine if an operation can be undone:

### Reversibility Categories

| Category | Description | Example | Undo Method |
|----------|-------------|---------|-------------|
| **Fully Reversible** | Can be completely undone | File edit | Restore backup |
| **Partially Reversible** | Some effects undoable | Package install | Uninstall |
| **Irreversible** | Cannot be undone | Sent email | N/A |

### Analysis Logic

```python
def analyze_reversibility(operation: AtomicOperation, state_before: dict, state_after: dict) -> ReversibilityResult:
    """Analyze if operation can be reversed."""

    # File operations - check for backups
    if operation.destination_type == 'file':
        files_with_backups = [
            f for f, s in state_before.get('files', {}).items()
            if s.get('backup_path')
        ]
        if files_with_backups:
            return ReversibilityResult(
                reversible=True,
                method='restore_backup',
                undo_commands=[
                    f"cp {state_before['files'][f]['backup_path']} {f}"
                    for f in files_with_backups
                ]
            )

    # Process operations - check for inverse commands
    if operation.destination_type == 'process':
        inverse = _find_inverse_command(operation.content)
        if inverse:
            return ReversibilityResult(
                reversible=True,
                method='inverse_command',
                undo_commands=[inverse]
            )

    # Default: not reversible
    return ReversibilityResult(
        reversible=False,
        reason='No undo method available'
    )
```

### Inverse Command Patterns

```python
INVERSE_COMMANDS = {
    # Service control
    r'systemctl start (.+)': 'systemctl stop {0}',
    r'systemctl stop (.+)': 'systemctl start {0}',
    r'systemctl enable (.+)': 'systemctl disable {0}',
    r'systemctl disable (.+)': 'systemctl enable {0}',

    # Package management
    r'apt install (.+)': 'apt remove {0}',
    r'apt remove (.+)': 'apt install {0}',
    r'dnf install (.+)': 'dnf remove {0}',
    r'dnf remove (.+)': 'dnf install {0}',

    # Container management
    r'docker start (.+)': 'docker stop {0}',
    r'docker stop (.+)': 'docker start {0}',
}

def _find_inverse_command(command: str) -> str | None:
    """Find inverse command if one exists."""
    for pattern, inverse_template in INVERSE_COMMANDS.items():
        match = re.match(pattern, command)
        if match:
            return inverse_template.format(*match.groups())
    return None
```

---

## Undo System

### Undo Operation

```python
def undo_operation(operation_id: str) -> UndoResult:
    """Attempt to undo an operation."""

    # Get execution record
    execution = get_execution_record(operation_id)
    if not execution:
        return UndoResult(success=False, error='Execution record not found')

    # Check reversibility
    if not execution.reversible:
        return UndoResult(success=False, error=execution.reversibility_reason)

    # Execute undo commands
    for undo_cmd in execution.undo_commands:
        result = shell_executor.execute(undo_cmd, {})
        if not result.success:
            return UndoResult(
                success=False,
                error=f'Undo command failed: {undo_cmd}',
                partial=True
            )

    # Restore backups
    for file_path, backup_path in execution.backup_files.items():
        if backup_path and os.path.exists(backup_path):
            shutil.copy2(backup_path, file_path)

    return UndoResult(success=True)
```

### Backup Management

```python
BACKUP_DIR = Path.home() / '.reos-data' / 'backups'
BACKUP_RETENTION_DAYS = 7

def _create_backup(file_path: str) -> str:
    """Create timestamped backup of file."""

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = file_path.replace('/', '_')
    backup_path = BACKUP_DIR / f"{safe_name}_{timestamp}"

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)

    return str(backup_path)

def cleanup_old_backups():
    """Remove backups older than retention period."""

    cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)

    for backup_file in BACKUP_DIR.iterdir():
        if backup_file.stat().st_mtime < cutoff.timestamp():
            backup_file.unlink()
```

---

## Resource Limits

### Execution Limits

| Resource | Default | Max | Purpose |
|----------|---------|-----|---------|
| Timeout | 120s | 600s | Prevent runaway commands |
| Memory | 1GB | 4GB | Prevent memory exhaustion |
| CPU | 80% | 100% | Maintain system responsiveness |
| Disk I/O | 100MB/s | — | Prevent disk thrashing |
| File size | 100MB | 1GB | Prevent disk filling |

### Enforcement

```python
def enforce_limits(context: dict) -> dict:
    """Apply resource limits to execution context."""

    return {
        'timeout': min(context.get('timeout', 120), 600),
        'memory_limit': min(context.get('memory_limit', 1024), 4096),  # MB
        'cpu_affinity': context.get('cpu_affinity'),
        'nice': 10,  # Lower priority than interactive processes
    }
```

---

## Database Schema

```sql
CREATE TABLE operation_execution (
    id TEXT PRIMARY KEY,
    operation_block_id TEXT NOT NULL,

    -- Executor used
    executor TEXT NOT NULL,             -- 'shell', 'python', 'file'

    -- Execution result
    success BOOLEAN NOT NULL,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    duration_ms INTEGER,

    -- State changes
    files_affected JSON,
    processes_spawned JSON,

    -- State snapshots
    state_before JSON,
    state_after JSON,

    -- Undo information
    reversible BOOLEAN,
    undo_commands JSON,
    backup_files JSON,

    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id)
);

CREATE INDEX idx_execution_operation ON operation_execution(operation_block_id);
CREATE INDEX idx_execution_timestamp ON operation_execution(executed_at);
```

---

## Safety Guarantees

### Pre-Execution

1. **Verification passed** — All 5 layers approved
2. **User approval** — If confidence below threshold
3. **State captured** — Backup created for affected files
4. **Limits applied** — Timeout, memory, CPU limits set

### During Execution

1. **Isolated execution** — Subprocess with constrained environment
2. **Output capture** — All stdout/stderr captured
3. **Timeout enforcement** — Kill on timeout
4. **Resource monitoring** — Track memory/CPU usage

### Post-Execution

1. **State diff** — Compare before/after states
2. **Reversibility analysis** — Determine undo capability
3. **RLHF opportunity** — Collect behavioral feedback
4. **Cleanup** — Remove temp files, maintain backups

---

## Integration with RLHF

Execution results feed into the learning system:

```python
# After execution
if not result.success:
    # Collect behavioral signal
    feedback_collector.collect_behavioral_signals(
        operation_id=operation.block_id,
        user_id=context['user_id'],
        retried=False,  # Will be set if user retries
        abandoned=True  # Operation failed
    )

# If user undoes
def on_undo(operation_id: str, user_id: str, time_since_execution_ms: int):
    feedback_collector.collect_behavioral_signals(
        operation_id=operation_id,
        user_id=user_id,
        undid=True,
        time_to_undo_ms=time_since_execution_ms
    )
```

---

## Related Documentation

- [Foundation](./FOUNDATION.md) — Core philosophy
- [Verification Layers](./verification-layers.md) — Pre-execution verification
- [RLHF Learning](./rlhf-learning.md) — Learning from execution outcomes
- [Atomic Operations](./atomic-operations.md) — Operation classification
