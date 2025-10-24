import os, json, redis

REDIS_URL = os.environ.get("REDIS_URL")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

_redis = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Vary": "Origin"
        },
        "body": json.dumps(body),
    }

def handler(request):
    if request["method"] == "OPTIONS":
        return _resp(204, {})

    try:
        data = json.loads(request.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "invalid json"})

    tok = data.get("one_time_token")
    if not tok:
        return _resp(400, {"error": "missing one_time_token"})

    if not _redis:
        return _resp(200, {"ok": True, "note": "no Redis configured"})

    # Atomisch einlösen
    try:
        val = _redis.execute_command("GETDEL", f"one_time:{tok}")
        if not val:
            return _resp(400, {"error": "invalid_or_used_token"})
    except Exception:
        pipe = _redis.pipeline()
        pipe.get(f"one_time:{tok}")
        pipe.delete(f"one_time:{tok}")
        got, _ = pipe.execute()
        if not got:
            return _resp(400, {"error": "invalid_or_used_token"})

    return _resp(200, {"ok": True})
