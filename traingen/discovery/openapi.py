"""OpenAPI → endpoints[] (FEATURE_INVENTORY §4.2). The task-verb backbone.
Exact and deterministic — one record per operation, facts only, with *_hint
breadcrumbs the synthesizer (Layer 2) may override."""
from __future__ import annotations

from .resource import resource_hint as _hint

_METHODS = ("get", "post", "put", "patch", "delete")

# Canonical short meanings; falls back to the response description otherwise.
_STATUS_MEANING = {
    200: "ok", 201: "created", 202: "accepted", 204: "no_content",
    400: "bad_request", 401: "unauthorized", 403: "forbidden",
    404: "not_found", 409: "conflict", 422: "validation_error", 500: "server_error",
}


def _resolve_ref(spec: dict, ref: str) -> dict:
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def _schema_fields(spec: dict, schema: dict) -> list:
    if not schema:
        return []
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    required = set(schema.get("required", []))
    fields = []
    for name, prop in (schema.get("properties") or {}).items():
        if isinstance(prop, dict) and "$ref" in prop:
            prop = _resolve_ref(spec, prop["$ref"])
        enum = prop.get("enum") if isinstance(prop, dict) else None
        ftype = "enum" if enum else (prop.get("type", "object") if isinstance(prop, dict) else "object")
        field = {"name": name, "type": ftype, "required": name in required}
        if enum:
            field["enum"] = enum
        fields.append(field)
    return fields


def _resource_hint(path: str, scope=None) -> str:
    segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    return _hint(segments, scope)


def _verb_hint(method: str, path: str) -> str:
    method = method.upper()
    segs = [s for s in path.strip("/").split("/") if s]
    has_id = "{" in path
    trailing_param = path.rstrip("/").endswith("}")
    last = segs[-1] if segs else ""
    if method == "GET":
        if last == "search":
            return "search"
        return "view" if trailing_param else "list"
    if method in ("PUT", "PATCH"):
        return "edit"
    if method == "DELETE":
        return "remove"
    if method == "POST":
        if has_id and not trailing_param and not last.startswith("{"):
            return last            # action endpoint, e.g. POST /partners/{id}/publish
        return "create"
    return method.lower()


def _security(spec: dict, operation: dict) -> list:
    reqs = operation.get("security")
    if reqs is None:
        reqs = spec.get("security", [])
    out = []
    for req in reqs or []:
        for scheme, scopes in (req or {}).items():
            out.extend(scopes or [scheme])
    seen, result = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


def _request_fields(spec: dict, operation: dict) -> list:
    body = operation.get("requestBody") or {}
    schema = ((body.get("content") or {}).get("application/json") or {}).get("schema") or {}
    return _schema_fields(spec, schema)


def _response_states(operation: dict) -> list:
    states = []
    for status, resp in (operation.get("responses") or {}).items():
        try:
            code = int(status)
        except (ValueError, TypeError):
            continue
        meaning = _STATUS_MEANING.get(code) or (resp or {}).get("description") or str(code)
        states.append({"status": code, "meaning": meaning})
    states.sort(key=lambda s: s["status"])
    return states


def extract_endpoints(spec: dict, scope_segments=None) -> list:
    endpoints = []
    for path, item in (spec.get("paths") or {}).items():
        for method in _METHODS:
            op = (item or {}).get(method)
            if not op:
                continue
            tags = op.get("tags") or []
            endpoints.append({
                "operation_id": op.get("operationId") or f"{method}_{path}",
                "method": method.upper(),
                "path": path,
                "tag": tags[0] if tags else _resource_hint(path, scope_segments),
                "summary": op.get("summary", ""),
                "description": op.get("description", ""),
                "resource_hint": _resource_hint(path, scope_segments),
                "task_verb_hint": _verb_hint(method, path),
                "request_fields": _request_fields(spec, op),
                "security": _security(spec, op),
                "response_states": _response_states(op),
                "provenance": "openapi",
            })
    endpoints.sort(key=lambda e: (e["path"], e["method"]))
    return endpoints
