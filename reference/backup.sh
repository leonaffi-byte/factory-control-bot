#!/bin/bash
BACKUP_DIR=~/backups/$(date +%Y-%m-%d)
mkdir -p $BACKUP_DIR
cp ~/.factory-env $BACKUP_DIR/
cp -r ~/knowledge-base $BACKUP_DIR/ 2>/dev/null
for proj in ~/projects/*/; do
    name=$(basename "$proj")
    mkdir -p $BACKUP_DIR/projects/$name
    cp "$proj/CLAUDE.md" $BACKUP_DIR/projects/$name/ 2>/dev/null
    cp "$proj/GEMINI.md" $BACKUP_DIR/projects/$name/ 2>/dev/null
    cp -r "$proj/artifacts/requirements" $BACKUP_DIR/projects/$name/ 2>/dev/null
    cp -r "$proj/artifacts/architecture" $BACKUP_DIR/projects/$name/ 2>/dev/null
    cp -r "$proj/artifacts/reports" $BACKUP_DIR/projects/$name/ 2>/dev/null
done
find ~/backups -maxdepth 1 -mtime +7 -exec rm -rf {} \;
echo "Backup: $BACKUP_DIR"
