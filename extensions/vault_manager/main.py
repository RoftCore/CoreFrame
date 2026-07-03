import json
import os
from datetime import datetime

VAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vault.json')


def _load_vault():
    if os.path.exists(VAULT_FILE):
        with open(VAULT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_vault(notes):
    with open(VAULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)


class Extension:
    def __init__(self, config):
        self.config = config

    def note_count(self):
        notes = _load_vault()
        return {"value": len(notes)}

    def recent_notes(self):
        notes = _load_vault()
        notes.sort(key=lambda n: n.get('updated', ''), reverse=True)
        recent = notes[:10]
        return {"value": [{"label": n.get('title', 'Untitled'), "value": n.get('updated', '')[:10]} for n in recent]}

    def list_notes(self):
        notes = _load_vault()
        if not notes:
            return {"value": "No saved notes."}
        lines = []
        for n in notes:
            lines.append(f"[{n.get('updated', '')[:10]}] {n.get('title', 'Untitled')}")
            body = n.get('body', '')
            if body:
                lines.append(f"    {body[:80]}{'...' if len(body) > 80 else ''}")
        return {"value": "\n".join(lines)}

    def new_note(self):
        return {"value": "Use POST /api/extension/vault_manager/create_note with JSON {title, body} to create a note."}

    def create_note(self, data=None):
        data = data or {}
        title = data.get("title", "Untitled")
        body = data.get("body", "")
        notes = _load_vault()
        notes.append({
            "id": len(notes) + 1,
            "title": title,
            "body": body,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat()
        })
        _save_vault(notes)
        return {"value": f"Note '{title}' created."}

    def export_all(self):
        notes = _load_vault()
        return {"value": json.dumps(notes, indent=2, ensure_ascii=False)}
