"""User decisions about extensions, kept apart from the generated registry.

`extensions.json` is metadata: `coreframe/app.py::_save_registry()` rewrites it
on every boot, heals entries from the manifests on disk, and every install
path recreates the entry it touched. A `disabled` flag stored only there is
lost the moment that file cannot be parsed: the boot heals it from disk, the
flag is not part of any manifest, and the extension comes back on its own.

That is not hypothetical. On 2026-10-22 10:45 the log shows

    Registry saved: 25 extensions
    ... audio_recorder | msd_deck | overlay_windows | spotify_player
        -> subprocess isolation

with those four disabled since 2026-10-15, and no "is disabled, skipping" line
in between: the file had been truncated by a non-atomic write, the heal
rebuilt it from the manifests, and every flag was gone.

So the decision lives in its own file (`extensions.state.json`), is written
atomically with a `.bak`, and is never rebuilt from memory. `extensions.json`
keeps a mirror of the flag for anything that reads it, but the state file is
what decides.
"""

import json
import os
import shutil
import tempfile

from coreframe.config import DATA_DIR, REGISTRY_PATH, log

STATE_PATH = os.path.join(DATA_DIR, 'extensions.state.json')
STATE_VERSION = 1

# mtime_ns of the state file as last read, plus the parsed set. is_disabled()
# runs once per extension at boot and again on every load, so a full re-parse
# each time is waste; the mtime check keeps it honest after an external edit.
_cache = {'mtime': None, 'disabled': set()}


def read_json_status(path):
    """(data, status) where status is 'ok', 'missing' or 'corrupt'."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, 'missing'
    except (OSError, ValueError) as e:
        log.error("Unreadable JSON (%s): %s", path, e)
        return {}, 'corrupt'
    if not isinstance(data, dict):
        log.error("Unreadable JSON (%s): top level is not an object", path)
        return {}, 'corrupt'
    return data, 'ok'


def read_json(path):
    """Tolerant read: anything unreadable is an empty dict, and it says so.

    Callers must not treat the result as "the file said nothing": a corrupt
    file is logged with the path, and `write_json` keeps the old bytes as
    `<path>.bak` before replacing it. Use `read_json_status` when overwriting
    a corrupt file would destroy data.
    """
    return read_json_status(path)[0]


def write_json(path, data):
    """Atomic write with a backup of the previous content.

    `open(path, 'w')` truncates before anything is written: a crash, a full
    disk or a killed process between the truncate and the dump leaves an empty
    file, which is exactly how the disabled flags were lost. Writing to a
    temp file in the same directory and renaming makes the swap atomic on both
    Windows and POSIX, and the `.bak` keeps the last good copy.
    """
    folder = os.path.dirname(path) or '.'
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix='.tmp-', suffix='.json', dir=folder)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + '.bak')
            except OSError as e:
                log.warning("Could not back up %s: %s", path, e)
        os.replace(tmp, path)
        return True
    except OSError as e:
        log.error("Could not write %s: %s", path, e)
        return False
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _parse(data):
    raw = data.get('disabled')
    if isinstance(raw, list):
        return {str(x) for x in raw if x}
    # Legacy shape: {"disabled": {"id": true}} if it ever gets written that way.
    if isinstance(raw, dict):
        return {str(k) for k, v in raw.items() if v}
    return set()


def _load():
    """State as a set of disabled ids, migrating the legacy registry once."""
    try:
        mtime = os.stat(STATE_PATH).st_mtime_ns
    except OSError:
        mtime = None
    if mtime is not None and mtime == _cache['mtime']:
        return _cache['disabled']

    if mtime is None:
        # No state file yet: the first boot after the upgrade. Seed from the
        # registry, which is the only place the flag was kept until today.
        disabled = {ext_id for ext_id, entry in read_json(REGISTRY_PATH).items()
                    if isinstance(entry, dict) and entry.get('disabled')}
        if disabled:
            log.info("Migrating %d disabled flag(s) out of extensions.json", len(disabled))
        _save(disabled)
        _cache['disabled'] = disabled
        try:
            _cache['mtime'] = os.stat(STATE_PATH).st_mtime_ns
        except OSError:
            _cache['mtime'] = None
        return disabled

    data, status = read_json_status(STATE_PATH)
    if status == 'corrupt':
        # The state file is the only copy of the decision: a corrupt one used to
        # mean "nothing is disabled", which is the resurrection this module
        # exists to prevent. Recover from the last atomic write's backup.
        data, status = read_json_status(STATE_PATH + '.bak')
        if status == 'ok':
            log.warning("extensions.state.json was corrupt: recovered from the .bak")
            write_json(STATE_PATH, data)
        else:
            log.error("extensions.state.json corrupt and no usable backup: falling back "
                      "to the disabled flags in extensions.json (best effort)")
            data = {'disabled': [k for k, v in read_json(REGISTRY_PATH).items()
                                 if isinstance(v, dict) and v.get('disabled')]}
    disabled = _parse(data)
    _cache['disabled'] = disabled
    try:
        _cache['mtime'] = os.stat(STATE_PATH).st_mtime_ns
    except OSError:
        _cache['mtime'] = mtime
    return disabled


def _save(disabled):
    ok = write_json(STATE_PATH, {
        'version': STATE_VERSION,
        'disabled': sorted(disabled),
    })
    if ok:
        # The cache is what the next is_disabled() answers from: without this it
        # returns the set from before the write until the mtime changes.
        _cache['disabled'] = set(disabled)
        try:
            _cache['mtime'] = os.stat(STATE_PATH).st_mtime_ns
        except OSError:
            _cache['mtime'] = None
    return ok


def disabled_ids():
    return sorted(_load())


def is_disabled(ext_id):
    return ext_id in _load()


def set_disabled(ext_id, flag):
    """Persist the decision, then mirror it into extensions.json.

    The mirror is best-effort: if the registry is unreadable it is left alone
    instead of being replaced by a single-entry file, and the state file still
    holds the answer.
    """
    disabled = set(_load())
    if flag:
        if ext_id in disabled:
            ok = True
        else:
            disabled.add(ext_id)
            ok = _save(disabled)
    else:
        if ext_id not in disabled:
            ok = True
        else:
            disabled.discard(ext_id)
            ok = _save(disabled)
    _mirror(ext_id, bool(flag))
    return ok


def _mirror(ext_id, flag):
    """Keep the `disabled` field in extensions.json truthful, never authoritative."""
    try:
        registry, status = read_json_status(REGISTRY_PATH)
        if status == 'corrupt':
            # Writing here would replace every entry with this one. The state
            # file already holds the answer; the registry heals on next boot.
            log.warning("Not mirroring disabled=%s for %s: extensions.json is unreadable",
                        flag, ext_id)
            return
        entry = registry.get(ext_id)
        if not isinstance(entry, dict):
            if not flag:
                return
            entry = {'name': ext_id, 'version': '1.0', 'author': '', 'category': 'general'}
        if 'disabled' in entry and bool(entry['disabled']) == flag:
            return
        entry['disabled'] = flag
        registry[ext_id] = entry
        write_json(REGISTRY_PATH, registry)
    except Exception as e:
        log.warning("Could not mirror disabled=%s for %s: %s", flag, ext_id, e)
