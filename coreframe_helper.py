"""
CoreFrame Helper - Elevated operations runner.
Launched via ShellExecuteW("runas") for UAC elevation.
Accepts JSON operations via temp file, returns results via temp file.
"""
import os
import sys
import json
import time
import tempfile


def write_registry(params):
    import winreg
    hive_map = {
        'HKEY_LOCAL_MACHINE': winreg.HKEY_LOCAL_MACHINE,
        'HKEY_CURRENT_USER': winreg.HKEY_CURRENT_USER,
        'HKEY_CLASSES_ROOT': winreg.HKEY_CLASSES_ROOT,
        'HKEY_USERS': winreg.HKEY_USERS,
    }
    hive_name = params.get('hive', 'HKEY_CURRENT_USER')
    hive = hive_map.get(hive_name, winreg.HKEY_CURRENT_USER)
    subkey = params['key']
    name = params.get('name', '')
    value = params.get('value', '')
    vtype = params.get('type', 'string')
    type_map = {
        'string': winreg.REG_SZ,
        'dword': winreg.REG_DWORD,
        'qword': winreg.REG_QWORD,
        'binary': winreg.REG_BINARY,
        'expand_string': winreg.REG_EXPAND_SZ,
        'multi_string': winreg.REG_MULTI_SZ,
    }
    reg_type = type_map.get(vtype, winreg.REG_SZ)

    access = winreg.KEY_SET_VALUE | winreg.KEY_READ
    try:
        key = winreg.OpenKey(hive, subkey, 0, access)
    except FileNotFoundError:
        key = winreg.CreateKey(hive, subkey)

    if vtype == 'binary' and isinstance(value, str):
        value = bytes.fromhex(value)

    winreg.SetValueEx(key, name, 0, reg_type, value)
    winreg.CloseKey(key)
    return {'success': True, 'message': f'Registry key written: {subkey}\\{name}'}


def run_system_command(params):
    import subprocess as sp
    cmd = params.get('command', '')
    timeout = params.get('timeout', 30)
    cwd = params.get('cwd', None)
    env = params.get('env', None)

    startupinfo = sp.STARTUPINFO()
    startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW

    result = sp.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
        startupinfo=startupinfo,
        creationflags=sp.CREATE_NO_WINDOW,
    )
    return {
        'stdout': result.stdout,
        'stderr': result.stderr,
        'returncode': result.returncode,
    }


def write_file(params):
    path = params['path']
    content = params.get('content', '')
    mode = params.get('mode', 'overwrite')
    encoding = params.get('encoding', 'utf-8')

    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

    file_mode = 'w' if mode == 'overwrite' else 'a'
    with open(path, file_mode, encoding=encoding) as f:
        f.write(content)

    return {'success': True, 'path': path, 'bytes_written': len(content.encode(encoding))}


def edit_file(params):
    path = params['path']
    old = params['old']
    new = params['new']
    encoding = params.get('encoding', 'utf-8')

    with open(path, 'r', encoding=encoding) as f:
        content = f.read()

    count = content.count(old)
    if count == 0:
        return {'error': f'old text not found in {path}'}

    content = content.replace(old, new)
    with open(path, 'w', encoding=encoding) as f:
        f.write(content)

    return {'success': True, 'path': path, 'replacements': count}


def delete_file(params):
    import shutil
    path = params['path']
    recursive = params.get('recursive', False)

    if not os.path.exists(path):
        return {'error': f'Path not found: {path}'}

    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)

    return {'success': True, 'deleted': path}


def create_directory(params):
    path = params['path']
    exist_ok = params.get('exist_ok', True)
    os.makedirs(path, exist_ok=exist_ok)
    return {'success': True, 'path': path}


def service_control(params):
    import subprocess as sp
    action = params.get('action', 'status')
    service_name = params.get('service', '')

    if action == 'status':
        result = sc_query(service_name)
    elif action == 'start':
        result = sc_command(f'sc start "{service_name}"')
    elif action == 'stop':
        result = sc_command(f'sc stop "{service_name}"')
    elif action == 'restart':
        sc_command(f'sc stop "{service_name}"')
        time.sleep(2)
        result = sc_command(f'sc start "{service_name}"')
    elif action == 'enable':
        result = sc_command(f'sc config "{service_name}" start= auto')
    elif action == 'disable':
        result = sc_command(f'sc config "{service_name}" start= disabled')
    else:
        return {'error': f'Unknown service action: {action}'}

    return result


def sc_query(service_name):
    import subprocess as sp
    startupinfo = sp.STARTUPINFO()
    startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
    result = sp.run(
        f'sc query "{service_name}"',
        shell=True, capture_output=True, text=True, timeout=10,
        startupinfo=startupinfo, creationflags=sp.CREATE_NO_WINDOW,
    )
    return {'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode}


def sc_command(cmd):
    import subprocess as sp
    startupinfo = sp.STARTUPINFO()
    startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
    result = sp.run(
        cmd, shell=True, capture_output=True, text=True, timeout=30,
        startupinfo=startupinfo, creationflags=sp.CREATE_NO_WINDOW,
    )
    return {'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode}


def network_adapter_control(params):
    import subprocess as sp
    action = params.get('action', 'status')
    adapter = params.get('adapter', '')

    startupinfo = sp.STARTUPINFO()
    startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW

    if action == 'disable':
        cmd = f'netsh interface set interface "{adapter}" admin=disable'
    elif action == 'enable':
        cmd = f'netsh interface set interface "{adapter}" admin=enable'
    elif action == 'status':
        cmd = f'netsh interface show interface "{adapter}"'
    else:
        return {'error': f'Unknown adapter action: {action}'}

    result = sp.run(cmd, shell=True, capture_output=True, text=True, timeout=30,
                    startupinfo=startupinfo, creationflags=sp.CREATE_NO_WINDOW)
    return {'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode}


HANDLERS = {
    'registry_write': write_registry,
    'system_command': run_system_command,
    'bash': run_system_command,
    'exec': run_system_command,
    'write_file': write_file,
    'edit_file': edit_file,
    'replace_file': edit_file,
    'delete_file': delete_file,
    'create_directory': create_directory,
    'service_control': service_control,
    'adapter_control': network_adapter_control,
    'batch': None,  # handled separately
}


def run_batch(params):
    """Execute multiple operations in one elevated session. Single UAC prompt."""
    operations = params.get('operations', [])
    results = []
    for i, op in enumerate(operations):
        op_type = op.get('type', '')
        handler = HANDLERS.get(op_type)
        if handler is None:
            results.append({'index': i, 'type': op_type, 'error': f'Unknown operation: {op_type}'})
            continue
        try:
            r = handler(op.get('params', {}))
            results.append({'index': i, 'type': op_type, 'result': r})
        except Exception as e:
            results.append({'index': i, 'type': op_type, 'error': f'{type(e).__name__}: {e}'})
    ok_count = sum(1 for r in results if 'error' not in r)
    return {'ok': ok_count == len(operations), 'total': len(operations), 'ok_count': ok_count, 'results': results}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: coreframe_helper.exe <op_file>'}))
        sys.exit(1)

    op_file = sys.argv[1]
    result_file = sys.argv[2] if len(sys.argv) > 2 else op_file + '.result'

    try:
        with open(op_file, 'r', encoding='utf-8') as f:
            op = json.load(f)
    except Exception as e:
        result = {'error': f'Failed to read operation: {e}'}
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f)
        print(json.dumps(result))
        sys.exit(1)

    op_type = op.get('type', '')

    if op_type == 'batch':
        result = run_batch(op.get('params', {}))
    else:
        handler = HANDLERS.get(op_type)
        if not handler:
            result = {'error': f'Unknown operation: {op_type}'}
        else:
            try:
                result = handler(op.get('params', {}))
            except Exception as e:
                result = {'error': f'{type(e).__name__}: {e}'}

    try:
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f)
    except Exception:
        pass

    print(json.dumps(result))
    sys.exit(0)


if __name__ == '__main__':
    main()
