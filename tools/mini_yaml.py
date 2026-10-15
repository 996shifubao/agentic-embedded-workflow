"""Minimal YAML subset loader (standard library only).

Supports the subset used by this repo:
  - nested maps by indentation (2 spaces)
  - lists with "- "
  - "- key: value" list items that continue on deeper-indented lines
  - inline lists [a, b, c]
  - quoted strings, ints, floats, true/false/null
  - "#" comments
Not supported: anchors, multi-document, block scalars, flow maps.
"""

import re


def _strip_comment(s):
    out, quote = [], None
    for ch in s:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _scalar(tok):
    tok = tok.strip()
    if tok == "":
        return None
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    low = tok.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", "none"):
        return None
    if tok.startswith("[") and tok.endswith("]"):
        inner = tok[1:-1].strip()
        return [] if inner == "" else [_scalar(x) for x in _split_inline(inner)]
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def _split_inline(s):
    parts, buf, quote = [], [], None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip() != ""]


def _is_map_start(rest):
    if rest[:1] in ("'", '"'):
        return False
    return bool(re.match(r"^[A-Za-z0-9_\-.]+:\s", rest + " "))


def _parse_map(lines, i, indent):
    result = {}
    while i < len(lines) and lines[i][0] == indent:
        content = lines[i][1]
        if content.startswith("- "):
            break
        key, sep, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                result[key], i = _parse_block(lines, i, lines[i][0])
            else:
                result[key] = None
        else:
            result[key] = _scalar(rest)
            i += 1
    return result, i


def _parse_list(lines, i, indent):
    result = []
    while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("-"):
        content = lines[i][1]
        rest = content[1:].strip()
        if rest == "":
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                val, i = _parse_block(lines, i, lines[i][0])
            else:
                val = None
            result.append(val)
        elif _is_map_start(rest):
            base = indent + 2
            sub = [(base, rest)]
            i += 1
            while i < len(lines) and lines[i][0] > indent:
                sub.append(lines[i])
                i += 1
            val, _ = _parse_block(sub, 0, base)
            result.append(val)
        else:
            result.append(_scalar(rest))
            i += 1
    return result, i


def _parse_block(lines, i, indent):
    if i < len(lines) and lines[i][1].startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def loads(text):
    lines = []
    for raw in text.splitlines():
        body = _strip_comment(raw).rstrip()
        if body.strip() == "":
            continue
        indent = len(body) - len(body.lstrip(" "))
        lines.append((indent, body.strip()))
    if not lines:
        return None
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return loads(f.read())
