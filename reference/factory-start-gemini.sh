#!/bin/bash
PROJECT="$1"
[ -z "$PROJECT" ] && echo "Usage: fsg <project-name>" && ls ~/projects/ && exit 1
[ ! -d "$HOME/projects/$PROJECT" ] && echo "ERROR: Project not found" && exit 1
[ -f "$HOME/projects/$PROJECT/GEMINI.md" ] || cp ~/factory-template/GEMINI.md "$HOME/projects/$PROJECT/GEMINI.md"

echo "Starting Gemini factory: $PROJECT"
tmux kill-session -t "gemini-$PROJECT" 2>/dev/null
tmux new-session -d -s "gemini-$PROJECT" -c "$HOME/projects/$PROJECT" \
    "gemini --yolo -p 'Read GEMINI.md then run the full factory pipeline phases 0-7. Maintain audit log. Use zen MCP for external models. Be fully autonomous.' 2>&1 | tee ~/projects/$PROJECT/artifacts/reports/factory-run.log"

echo "✅ Running in background"
echo "  Monitor: tmux attach -t gemini-$PROJECT"
echo "  Logs:    tail -f ~/projects/$PROJECT/artifacts/reports/factory-run.log"
echo "  Stop:    tmux kill-session -t gemini-$PROJECT"
