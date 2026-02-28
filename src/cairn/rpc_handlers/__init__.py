"""RPC handler modules for ui_rpc_server.

This package contains handler functions organized by domain:
- play: Play (Acts/Scenes) operations
- providers: LLM provider management (Ollama)
- chat: Chat and conversation handlers
- planning: Code planning and execution handlers
"""

from __future__ import annotations

from cairn.rpc.types import RpcError

__all__ = ["RpcError"]
