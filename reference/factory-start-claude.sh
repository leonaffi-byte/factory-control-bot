#!/bin/bash
PROJECT="$1"
[ -z "$PROJECT" ] && echo "Usage: fsc <project-name>" && ls ~/projects/ && exit 1
[ ! -d "$HOME/projects/$PROJECT" ] && echo "ERROR: Project not found" && exit 1
[ -f "$HOME/projects/$PROJECT/CLAUDE.md" ] || cp ~/factory-template/CLAUDE.md "$HOME/projects/$PROJECT/CLAUDE.md"

echo "Starting Claude factory: $PROJECT"
tmux kill-session -t "claude-$PROJECT" 2>/dev/null
tmux new-session -d -s "claude-$PROJECT" -c "$HOME/projects/$PROJECT" \
    "claude --dangerously-skip-permissions -p 'Read CLAUDE.md then run /factory. Follow all phases 0-7. Maintain audit log. Use zen MCP for external models. Be fully autonomous.' 2>&1 | tee ~/projects/$PROJECT/artifacts/reports/factory-run.log"

echo "✅ Running in background"
echo "  Monitor: tmux attach -t claude-$PROJECT"
echo "  Logs:    tail -f ~/projects/$PROJECT/artifacts/reports/factory-run.log"
echo "  Stop:    tmux kill-session -t claude-$PROJECT"
