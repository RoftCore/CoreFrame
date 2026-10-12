"""Host-process support code for the launcher (run_coreframe.pyw).

Kept out of the launcher so crash forensics and early-boot helpers are testable
and cannot drift into the window code. Nothing here imports webview or Flask:
these run before the window exists.
"""