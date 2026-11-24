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

## What is still missing before a public binary release

GPL-compatible or not, the license texts of the components above must travel
with the binaries, not only with this file. BSD-3-Clause and Apache-2.0 require
the notice to appear in binary distributions, and Apache-2.0 additionally
requires its `NOTICE` file when one exists upstream. The wheels installed here
ship a `LICENSE` file for only some of the packages (Werkzeug, psutil,
`itsdangerous`, `requests`, `blinker`), so the texts have to be collected at
build time from PyPI metadata or from the installed distributions. Until that
step exists, a public release does not fully satisfy their terms.
