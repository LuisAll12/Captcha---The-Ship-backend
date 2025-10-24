import os, json, redis

REDIS_URL = os.environ.get("REDIS_URL")

# CORS Allowlist
ALLOWED_ORIGINS_ENV = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
if not ALLOWED:
    ALLOWED = ["*"]  # nur für Tests

_redis = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

def _cors_origin(request):
    origin = None
    try:
        headers = request.get("headers") or {}
        origin = headers.get("origin") or headers.get("Origin")
    except Exception:
        pass
    if "*" in ALLOWED:
        return "*"
    return origin if origin in ALLOWED else None

def _resp(status: int, body: dict, origin: str | None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers.update({
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Vary": "Origin",
        })
    return {"statusCode": status, "headers": headers, "body": json.dumps(body)}

def handler(request):
    origin = _cors_origin(request)

    # Preflight
    if request["method"] == "OPTIONS":
        return _resp(204, {}, origin)

    # Body
    try:
        data = json.loads(request.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "invalid json"}, origin)

    tok = data.get("one_time_token")
    if not tok:
        return _resp(400, {"error": "missing one_time_token"}, origin)

    if not _redis:
        # Ohne Redis kann Serverless die Einmaligkeit nicht garantieren
        return _resp(200, {"ok": True, "note": "no Redis configured"}, origin)

    # Atomisch einlösen (GETDEL, Fallback Pipeline)
    try:
        val = _redis.execute_command("GETDEL", f"one_time:{tok}")
        if not val:
            return _resp(400, {"error": "invalid_or_used_token"}, origin)
    except Exception:
        pipe = _redis.pipeline()
        pipe.get(f"one_time:{tok}")
        pipe.delete(f"one_time:{tok}")
        got, _ = pipe.execute()
        if not got:
            return _resp(400, {"error": "invalid_or_used_token"}, origin)

    return _resp(200, {"ok": True}, origin)
