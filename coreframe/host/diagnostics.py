"""Crash forensics for the host process.

Single-shot boot net plus sparse rotating snapshots. Never a repeating full-stack
dump: the segfault site was PyTraceBack_Print itself, so dumping every 15 s rolled
those dice forever (pitfall 28).
"""
import faulthandler
import os
import threading
import time

_SNAP_INTERVAL_S = 300
_BOOT_DUMP_DELAY_S = 15

_snap_files = []
_snap_idx = [0]
boot_log_file = None


def start_stack_dumper(data_dir):
    """One dump 15 s after launch, to catch a crash before the first poll."""
    global boot_log_file
    try:
        os.makedirs(data_dir, exist_ok=True)
        boot_log_file = open(os.path.join(data_dir, 'coreframe.log'), 'a', encoding='utf-8')
        boot_log_file.write('\n===== %s launch =====\n' % time.strftime('%H:%M:%S'))
        boot_log_file.flush()
        faulthandler.dump_traceback_later(_BOOT_DUMP_DELAY_S, file=boot_log_file)
    except Exception:
        pass


def start_snapshotter(data_dir):
    """Rewrite two alternating stack snapshots every 5 min; the last one survives a crash."""
    try:
        for i in (1, 2):
            _snap_files.append(
                open(os.path.join(data_dir, 'stacksnap%d.log' % i), 'w', encoding='utf-8'))

        def _snap():
            while True:
                time.sleep(_SNAP_INTERVAL_S)
                try:
                    f = _snap_files[_snap_idx[0] % 2]
                    f.seek(0)
                    f.truncate()
                    f.write('===== %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
                    faulthandler.dump_traceback(file=f)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        pass
                    _snap_idx[0] += 1
                except Exception:
                    pass

        threading.Thread(target=_snap, daemon=True, name='stacksnap').start()
    except Exception:
        pass