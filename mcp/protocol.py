"""JSON-RPC 2.0 framing for the stdio transport."""

import json
import sys

JSONRPC = "2.0"
PROTOCOL_VERSION = "2024-11-05"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def success(msg_id, result):
    return {"jsonrpc": JSONRPC, "id": msg_id, "result": result}


def failure(msg_id, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC, "id": msg_id, "error": error}


# --------------------------------------------------------------------------- #
# stdio framing: `Content-Length: N\r\n\r\n{json}` (LSP style, as used by MCP)
# --------------------------------------------------------------------------- #
def read_message(stream=None):
    stream = stream or sys.stdin.buffer
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if b":" in line:
            key, _, value = line.partition(b":")
            headers[key.strip().lower()] = value.strip()
    if not headers:
        return None
    length = headers.get(b"content-length")
    if length is None:
        raise RpcError(PARSE_ERROR, "missing Content-Length header")
    payload = stream.read(int(length))
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RpcError(PARSE_ERROR, "invalid JSON payload: %s" % exc)


def write_message(message, stream=None):
    stream = stream or sys.stdout.buffer
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body))
    stream.write(body)
    stream.flush()

