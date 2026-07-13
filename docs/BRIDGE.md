# Multi-language Bridge — JSON-RPC Protocol

CoreFrame can run extensions written in any language that supports stdin/stdout, through a subprocess bridge.

## How it works

```
CoreFrame ──── JSON (stdin) ────→ [child process]
            ←── JSON (stdout) ────
```

Each line in stdin is a request. Each line in stdout is a response. The `id` in each message pairs the request with the response.

## Configuration

In `extension.json`:

```json
{
  "id": "mi_extension",
  "language": "node",
  "main": "server.js",
  "widgets": [
    { "id": "status", "type": "text", "label": "Status", "action": "get_status" }
  ]
}
```

| Parameter | Description |
|-----------|-------------|
| `language` | `"node"` for Node.js. Maps to the system interpreter. |
| `main` | Relative path to the main script (inside the extension folder). |

## Protocol

### Request (CoreFrame → process)

```json
{"method": "get_status", "params": {}, "id": 1}
```

- `method`: string — name of the method to execute (corresponds to the widget's `action`)
- `params`: object — parameters (for POST methods, contains the body)
- `id`: int/string — unique identifier to pair the response

### Successful response (process → CoreFrame)

```json
{"result": {"percent": 45, "status": "ok"}, "id": 1}
```

- `result`: any JSON value — returned to the widget as `{"value": result}`
- `id`: must match the request's `id`

### Error response

```json
{"error": "Error message", "id": 1}
```

## Examples by language

### Node.js

```javascript
const readline = require('readline');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false
});

rl.on('line', (line) => {
  const { method, params, id } = JSON.parse(line);

  switch (method) {
    case 'get_status':
      process.stdout.write(JSON.stringify({
        result: { status: 'online', uptime: process.uptime() },
        id
      }) + '\n');
      break;
    case 'set_config':
      // params contains the POST body
      process.stdout.write(JSON.stringify({ result: 'ok', id }) + '\n');
      break;
    default:
      process.stdout.write(JSON.stringify({ error: `Unknown: ${method}`, id }) + '\n');
  }
});
```

### Python (as subprocess bridge)

```python
import sys, json

for line in sys.stdin:
    req = json.loads(line.strip())
    method = req['method']
    params = req.get('params', {})
    rid = req['id']

    if method == 'get_status':
        print(json.dumps({"result": {"value": "OK"}, "id": rid}), flush=True)
    else:
        print(json.dumps({"error": "Unknown method", "id": rid}), flush=True)
```

### Go (example)

```go
package main

import (
    "bufio"
    "encoding/json"
    "os"
)

type Request struct {
    Method string                 `json:"method"`
    Params map[string]interface{} `json:"params"`
    ID     int                    `json:"id"`
}

type Response struct {
    Result interface{} `json:"result,omitempty"`
    Error  string      `json:"error,omitempty"`
    ID     int         `json:"id"`
}

func main() {
    scanner := bufio.NewScanner(os.Stdin)
    for scanner.Scan() {
        var req Request
        json.Unmarshal(scanner.Bytes(), &req)

        resp := Response{ID: req.ID}
        switch req.Method {
        case "get_status":
            resp.Result = map[string]interface{}{"value": "OK from Go"}
        default:
            resp.Error = "Unknown method"
        }

        data, _ := json.Marshal(resp)
        os.Stdout.Write(data)
        os.Stdout.Write([]byte("\n"))
    }
}
```

## Considerations

- **Timeout**: the bridge waits 30s for a response. After that time, it returns an error to the widget.
- **Lifecycle**: the child process is launched when the extension loads. If it dies, the extension becomes unusable. When CoreFrame closes, it sends `SIGTERM` (and `SIGKILL` if it doesn't respond within 5s).
- **stderr**: it is captured and logged, but does not affect the protocol.
- **Buffer**: use `flush=True` in Python or equivalent to avoid buffering.
- **Multiple requests**: the bridge is synchronous (waits for a response before sending the next one). The arrival order determines the response order.
- **Idempotency**: each request has a unique `id`. If the child process receives a repeated `id` (extremely rare), it must respond to both.

## Adding a new language

Edit `_LANG_MAP` in the `SubprocessBridge` class inside `app.py`:

```python
_LANG_MAP = {
    'node': 'node',
    'go': 'go',           # <-- add
    'rust': 'cargo',      # <-- or the corresponding binary
}
```

The value is the name of the interpreter/compiler executable. If the script requires prior compilation, do it manually and point `main` to the compiled binary.
