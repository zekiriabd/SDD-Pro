"""Claude Code hooks (PreToolUse, PostToolUse, SubagentStop).

Each hook is a standalone script callable as:
    python .claude/python/sdd_hooks/<name>.py

Reads JSON payload from stdin, emits warnings on stderr, exit 0/2.
"""
