# Third-party notices

CoreFrame is GPL-3.0-or-later (see `LICENSE.md`). It bundles and links the
following third-party components. Each one remains under its own license, and
those licenses apply to their code, not to CoreFrame as a whole.

The versions below are the ones pinned in `requirements.txt` and installed in the
build environment. Licenses were read from each package's own metadata
(`License-Expression` / `License` / `Classifier` fields), not guessed.

## Bundled in the frozen build (Python)

| Component | Version | License (SPDX) | Upstream |
|---|---|---|---|
| Flask | 3.1.2 | BSD-3-Clause | https://palletsprojects.com/p/flask/ |
| Werkzeug | 3.1.9 | BSD-3-Clause | https://palletsprojects.com/p/werkzeug/ |
| Jinja2 | 3.1.6 | BSD-3-Clause | https://palletsprojects.com/p/jinja/ |
| click | 8.5.0 | BSD-3-Clause | https://palletsprojects.com/p/click/ |
| itsdangerous | 2.2.0 | BSD-3-Clause | https://palletsprojects.com/p/itsdangerous/ |
| blinker | 1.9.0 | MIT | https://github.com/pallets-eco/blinker |
| MarkupSafe | 3.0.4 | BSD-3-Clause | https://palletsprojects.com/p/markupsafe/ |
| Flask-SocketIO | 5.6.1 | MIT | https://github.com/miguelgrinberg/Flask-SocketIO |
| python-socketio | 5.17.0 | MIT | https://github.com/miguelgrinberg/python-socketio |
| python-engineio | 4.14.0 | MIT | https://github.com/miguelgrinberg/python-engineio |
| bidict | 0.24.1 | MPL-2.0 | https://github.com/jab/bidict |
| eventlet | 0.41.0 | MIT | https://github.com/eventlet/eventlet |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | https://github.com/python-greenlet/greenlet |
| psutil | 7.2.0 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| GPUtil | 1.4.0 | MIT | https://github.com/anderskm/gputil |
| requests | 2.32.3 | Apache-2.0 | https://requests.readthedocs.io/ |
| urllib3 | 2.8.0 | MIT | https://github.com/urllib3/urllib3 |
| certifi | 2026.7.22 | MPL-2.0 | https://github.com/certifi/python-certifi |
| charset-normalizer | 3.5.2 | MIT | https://github.com/jawah/charset_normalizer |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| Pillow | 12.1.0 | MIT-CMU | https://python-pillow.org/ |
| hidapi | 0.15.0 | BSD-3-Clause (binding) | https://github.com/trezor/cython-hidapi |
| pywebview | 6.2.1 | BSD-3-Clause | https://pywebview.flowrl.com/ |
| proxy-tools | 0.1.0 | MIT | https://github.com/jtushman/proxy_tools |
| bottle | 0.13.4 | MIT | https://bottlepy.org/ |
| dnspython | 2.9.0 | ISC | https://www.dnspython.org/ |
| typing_extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |

## Bundled in the frontend

| Component | License (SPDX) | Upstream |
|---|---|---|
| Socket.IO client (`static/js/socket.io.min.js`) | MIT | https://github.com/socketio/socket.io-client |
| Feather Icons | MIT | https://feathericons.com/ |

Feather is loaded from jsDelivr at runtime and is not redistributed by this
repository; the notice is kept because the app depends on it.

## What the bundle already carries, and what it does not

CoreFrame's own `LICENSE.md`, `NOTICE` and `AUTHORS` are packed into the exe by
`_legal_datas` in `CoreFrame.spec` / `CoreFrame-onedir.spec`, together with this
file.

For the dependencies, PyInstaller copies whatever license metadata the wheel
itself ships. Measured on a real Windows build (2026-11-24, `pyi-archive_viewer`
against `dist/CoreFrame.exe`), the bundle contains exactly these:

    click-8.5.0         licenses/LICENSE.txt
    flask-3.1.2         licenses/LICENSE.txt
    itsdangerous-2.2.0  LICENSE.txt
    markupsafe-3.0.4    licenses/LICENSE.txt
    werkzeug-3.1.9      licenses/LICENSE.txt
    _tk_data/license.terms   (Tcl/Tk)

Everything else in the table above does **not** travel inside the exe: requests
(Apache-2.0, which also requires its upstream `NOTICE`), urllib3, certifi,
charset-normalizer, idna, psutil, Pillow, eventlet, greenlet, GPUtil, hidapi,
pywebview, bottle, proxy-tools, dnspython, typing_extensions, Jinja2, blinker and
the Socket.IO stack. The `LICENSE` files that show up under `pip-*` and
`setuptools-*` belong to pip's own vendored copies and do not cover the runtime
package of the same name.

A public binary release is therefore still not fully compliant for those
packages. The fix is a build step that collects each distribution's license from
its `dist-info`, writes them into a `licenses/` folder and packs that folder the
same way the files above are packed.

