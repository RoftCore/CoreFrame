from PyInstaller.utils.hooks.gi import GiModuleInfo
from PyInstaller.utils.hooks import get_hook_config


def hook(hook_api):
    module_versions = get_hook_config(hook_api, 'gi', 'module-versions')
    if module_versions:
        version = module_versions.get('WebKit2', '4.0')
    else:
        version = '4.0'

    module_info = GiModuleInfo('WebKit2', version, hook_api=hook_api)
    if not module_info.available:
        version = '4.1'
        module_info = GiModuleInfo('WebKit2', version, hook_api=hook_api)
        if not module_info.available:
            return

    binaries, datas, hiddenimports = module_info.collect_typelib_data()
    hook_api.add_datas(datas)
    hook_api.add_binaries(binaries)
    hook_api.add_imports(*hiddenimports)
