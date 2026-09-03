import os
import json
import threading
from datetime import datetime
from typing import Optional

from coreframe.config import log, DATA_DIR

# ── Permission Levels ───────────────────────────────────────────────
# 0 = basic    : UI only, no access
# 1 = storage  : own data_dir only
# 2 = user_files: mediated by user (file dialogs, whitelists)
# 3 = network  : outbound HTTP/HTTPS
# 4 = system   : read system info, processes, registry read
# 5 = admin    : full control, registry write, services, filesystem

PERMISSION_LEVELS = {
    'basic': 0,
    'storage': 1,
    'user_files': 2,
    'network': 3,
    'system': 4,
    'admin': 5,
}

PERMISSION_NAMES = {v: k for k, v in PERMISSION_LEVELS.items()}

# Levels that require explicit user consent before the extension can function
REQUIRES_CONSENT = {3, 4, 5}

# Human-readable descriptions for consent modals
PERMISSION_DESCRIPTIONS = {
    0: 'Sin acceso a recursos del sistema',
    1: 'Solo accede a sus propios datos locales',
    2: 'Accede a archivos que el usuario seleccione manualmente',
    3: 'Realiza conexiones de red salientes (HTTP/HTTPS)',
    4: 'Accede a información del sistema (CPU, RAM, procesos, archivos)',
    5: 'Control total del sistema: archivos, registro, servicios, procesos',
}

PERMISSION_LABELS = {
    0: 'Basico',
    1: 'Almacenamiento',
    2: 'Archivos del usuario',
    3: 'Red',
    4: 'Sistema',
    5: 'Admin',
}

# ── Escalation method groups ───────────────────────────────────────
# Methods that require elevated permissions beyond the base level

ESCALATION_METHODS = {
    'bash': 5,
    'exec': 5,
    'system_command': 5,
    'registry_write': 5,
    'service_control': 5,
    'adapter_control': 5,
    'write_file': 4,
    'edit_file': 4,
    'replace_file': 4,
    'delete_file': 5,
    'list_dir': 4,
    'read_file': 3,
}

ESCALATION_LABELS = {
    5: 'Ejecucion de codigo / Comandos del sistema',
    4: 'Escritura de archivos / Acceso a disco',
    3: 'Lectura de archivos',
}


def _atomic_write(path: str, data: dict):
    """Thread-safe atomic write to JSON file."""
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        log.error("Failed to write %s: %s", path, e)
        try:
            os.remove(tmp)
        except Exception:
            pass


class ExtensionPermissionManager:
    """Manages permissions, consents, and file whitelists for extensions."""

    def __init__(self):
        self._consent_path = os.path.join(DATA_DIR, 'permissions_consent.json')
        self._whitelist_path = os.path.join(DATA_DIR, 'file_whitelists.json')
        self._denied_path = os.path.join(DATA_DIR, 'permissions_denied.json')
        self._consents = self._load_json(self._consent_path)
        self._whitelists = self._load_json(self._whitelist_path)
        self._denied = self._load_json(self._denied_path)
        self._lock = threading.Lock()
        self._socketio = None

    def set_socketio(self, socketio):
        self._socketio = socketio

    def _load_json(self, path: str) -> dict:
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_consents(self):
        _atomic_write(self._consent_path, self._consents)

    def _save_whitelists(self):
        _atomic_write(self._whitelist_path, self._whitelists)

    def _save_denied(self):
        _atomic_write(self._denied_path, self._denied)

    # ── Config parsing ─────────────────────────────────────────────

    def get_required_level(self, ext_config: dict) -> int:
        """Extract required permission level from extension.json config."""
        perms = ext_config.get('permissions', {})
        if not perms:
            return -1  # No permissions field = legacy
        level_str = perms.get('level', 'basic')
        return PERMISSION_LEVELS.get(level_str, 0)

    def get_escalation(self, ext_config: dict) -> dict:
        """Extract escalation rules from extension.json config."""
        perms = ext_config.get('permissions', {})
        return perms.get('escalation', {})

    def get_requires(self, ext_config: dict) -> list:
        """Extract required permissions list from extension.json config."""
        perms = ext_config.get('permissions', {})
        return perms.get('requires', [])

    def is_mediated(self, ext_config: dict) -> bool:
        """Check if extension uses user-mediated file access."""
        perms = ext_config.get('permissions', {})
        return perms.get('mediated', False)

    def get_permission_info(self, ext_config: dict) -> dict:
        """Get full permission info for an extension."""
        level = self.get_required_level(ext_config)
        return {
            'level': level,
            'level_name': PERMISSION_NAMES.get(level, 'unknown') if level >= 0 else 'legacy',
            'level_label': PERMISSION_LABELS.get(level, 'Desconocido') if level >= 0 else 'Legacy (sin permisos)',
            'requires': self.get_requires(ext_config),
            'mediated': self.is_mediated(ext_config),
            'escalation': self.get_escalation(ext_config),
            'description': PERMISSION_DESCRIPTIONS.get(level, '') if level >= 0 else 'Extension sin permisos declarados. Se detecta como legacy.',
        }

    # ── Consent management ─────────────────────────────────────────

    def has_consent(self, ext_id: str) -> bool:
        """Check if extension has user consent."""
        return ext_id in self._consents

    def get_granted_level(self, ext_id: str) -> int:
        """Get the permission level granted to an extension."""
        consent = self._consents.get(ext_id)
        if consent:
            return consent.get('level', 0)
        return 0

    def get_granted_escalations(self, ext_id: str) -> list:
        """Get list of escalation permissions granted to an extension."""
        consent = self._consents.get(ext_id)
        if consent:
            esc = consent.get('escalations', []) or []
            perm = consent.get('permanent_escalations', []) or []
            tmp = consent.get('temp_escalations', []) or []
            return list(set(esc + perm + tmp))
        return []

    def check(self, ext_id: str, required_level: int) -> bool:
        """Verify extension has sufficient permission level."""
        granted = self.get_granted_level(ext_id)
        return granted >= required_level

    def check_escalation(self, ext_id: str, method: str) -> bool:
        """Verify if an extension has permission for a specific escalation method. Consumes temp grants."""
        with self._lock:
            consent = self._consents.get(ext_id)
            if not consent:
                return False
            # Permanent
            perm = consent.get('permanent_escalations', []) or []
            if method in perm:
                return True
            esc = consent.get('escalations', []) or []
            if method in esc:
                return True
            tmp = consent.get('temp_escalations', []) or []
            if method in tmp:
                # Consume once
                tmp.remove(method)
                consent['temp_escalations'] = tmp
                self._save_consents()
                log.info("Escalation temp consumed for %s: %s", ext_id, method)
                return True
        return False

    def grant(self, ext_id: str, level: int, escalations: list = None, permanent_escalations: list = None):
        """Grant permission to an extension."""
        with self._lock:
            entry = {
                'level': level,
                'escalations': escalations or [],
                'permanent_escalations': permanent_escalations or [],
                'granted_at': datetime.now().isoformat(),
            }
            self._consents[ext_id] = entry
            self._save_consents()
        log.info("Permission granted to %s: level=%d, escalations=%s", ext_id, level, escalations)

    def grant_escalation(self, ext_id: str, method: str, once: bool = False):
        """Grant a specific escalation permission. If once=True, grant for one use only."""
        with self._lock:
            if ext_id not in self._consents:
                self._consents[ext_id] = {
                    'level': 0,
                    'escalations': [],
                    'permanent_escalations': [],
                    'temp_escalations': [],
                    'granted_at': datetime.now().isoformat(),
                }
            perm = self._consents[ext_id]
            if once:
                te = perm.get('temp_escalations', [])
                if method not in te:
                    te.append(method)
                    perm['temp_escalations'] = te
                    self._save_consents()
                log.info("Escalation granted (once) to %s: %s", ext_id, method)
            else:
                pe = perm.get('permanent_escalations', [])
                if method not in pe:
                    pe.append(method)
                    perm['permanent_escalations'] = pe
                    self._save_consents()
                log.info("Escalation granted to %s: %s", ext_id, method)

    def revoke(self, ext_id: str):
        """Revoke all permissions from an extension."""
        with self._lock:
            self._consents.pop(ext_id, None)
            self._save_consents()
        log.info("Permission revoked from %s", ext_id)

    def revoke_escalation(self, ext_id: str, method: str):
        """Revoke a specific escalation permission."""
        with self._lock:
            perm = self._consents.get(ext_id)
            if perm:
                pe = perm.get('permanent_escalations', [])
                if method in pe:
                    pe.remove(method)
                    perm['permanent_escalations'] = pe
                    self._save_consents()
        log.info("Escalation revoked from %s: %s", ext_id, method)

    # ── Denied consent tracking ────────────────────────────────────

    def is_denied(self, ext_id: str) -> bool:
        """Check if extension consent was explicitly denied."""
        return ext_id in self._denied

    def mark_denied(self, ext_id: str, ext_name: str = '', level: int = 0):
        """Mark extension consent as denied (persists across restarts)."""
        with self._lock:
            self._denied[ext_id] = {
                'name': ext_name,
                'level': level,
                'denied_at': datetime.now().isoformat(),
            }
            self._save_denied()
        log.info("Consent denied for %s (saved)", ext_id)

    def clear_denied(self, ext_id: str):
        """Clear denied state (e.g. when user grants consent later)."""
        with self._lock:
            if ext_id in self._denied:
                del self._denied[ext_id]
                self._save_denied()
        log.info("Denied state cleared for %s", ext_id)

    def get_all_denied(self) -> dict:
        """Return all denied consents."""
        return dict(self._denied)

    # ── File whitelist (for mediated extensions) ───────────────────

    def add_to_whitelist(self, ext_id: str, file_path: str):
        """Add a file path to extension's whitelist (user selected it)."""
        with self._lock:
            if ext_id not in self._whitelists:
                self._whitelists[ext_id] = []
            normalized = os.path.normpath(file_path)
            if normalized not in self._whitelists[ext_id]:
                self._whitelists[ext_id].append(normalized)
                self._save_whitelists()
        log.debug("Whitelist add: %s -> %s", ext_id, normalized)

    def is_file_allowed(self, ext_id: str, file_path: str, ext_config: dict) -> bool:
        """Check if extension can access a specific file."""
        if not self.is_mediated(ext_config):
            # Non-mediated: check by level
            level = self.get_required_level(ext_config)
            return self.check(ext_id, level)
        # Mediated: check whitelist
        normalized = os.path.normpath(file_path)
        whitelist = self._whitelists.get(ext_id, [])
        return normalized in whitelist

    def remove_from_whitelist(self, ext_id: str, file_path: str):
        """Remove a file from extension's whitelist."""
        with self._lock:
            whitelist = self._whitelists.get(ext_id, [])
            normalized = os.path.normpath(file_path)
            if normalized in whitelist:
                whitelist.remove(normalized)
                self._whitelists[ext_id] = whitelist
                self._save_whitelists()

    def get_whitelist(self, ext_id: str) -> list:
        """Get all whitelisted files for an extension."""
        return self._whitelists.get(ext_id, [])

    # ── Legacy migration ───────────────────────────────────────────

    def is_legacy(self, ext_config: dict) -> bool:
        """Check if extension is legacy (no permissions field)."""
        return 'permissions' not in ext_config

    def migrate_extension(self, ext_path: str, ext_config: dict, level: str, escalations: list = None):
        """Write permissions to extension.json (permanent migration)."""
        perms = {
            'level': level,
            'requires': escalations or [],
        }
        if level == 'user_files':
            perms['mediated'] = True
        ext_config['permissions'] = perms
        config_path = os.path.join(ext_path, 'extension.json')
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(ext_config, f, indent=2, ensure_ascii=False)
            log.info("Migrated %s with permissions: %s", ext_path, perms)
            return True
        except Exception as e:
            log.error("Failed to migrate %s: %s", ext_path, e)
            return False

    # ── Consent status tracking ────────────────────────────────────

    def get_pending_consent(self, ext_id: str) -> Optional[dict]:
        """Check if extension needs consent (returns info or None)."""
        if self.has_consent(ext_id):
            return None
        # The caller must provide ext_config to determine level
        return {'ext_id': ext_id, 'needs_consent': True}

    def emit_needs_consent(self, ext_id: str, ext_name: str, level: int, permissions: dict):
        """Send WebSocket event that extension needs consent."""
        if self._socketio:
            self._socketio.emit('extension_needs_consent', {
                'id': ext_id,
                'name': ext_name,
                'level': level,
                'level_name': PERMISSION_NAMES.get(level, 'unknown'),
                'level_label': PERMISSION_LABELS.get(level, 'Desconocido'),
                'description': PERMISSION_DESCRIPTIONS.get(level, ''),
                'permissions': permissions,
            })

    def emit_escalation_request(self, ext_id: str, ext_name: str, method: str, level: int):
        """Send WebSocket event that extension needs escalation for a method."""
        if self._socketio:
            self._socketio.emit('extension_escalation_request', {
                'id': ext_id,
                'name': ext_name,
                'method': method,
                'level': level,
                'level_label': PERMISSION_LABELS.get(level, 'Desconocido'),
                'description': ESCALATION_LABELS.get(level, method),
            })

    # ── Serialization ──────────────────────────────────────────────

    def get_all_consents(self) -> dict:
        """Return all consents (for API)."""
        return dict(self._consents)

    def get_all_whitelists(self) -> dict:
        """Return all whitelists (for API)."""
        return dict(self._whitelists)


# Global singleton
_perm_manager: Optional[ExtensionPermissionManager] = None


def get_permission_manager() -> ExtensionPermissionManager:
    global _perm_manager
    if _perm_manager is None:
        _perm_manager = ExtensionPermissionManager()
    return _perm_manager
