# api/recaptcha/consume.py
import os, json, redis

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
REDIS_URL = os.environ.get("REDIS_URL")

_redis = redis.from_url(REDIS_URL) if REDIS_URL else None

def _resp(status: int, body: dict, origin: str = "*"):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }

def handler(request):
    if request["method"] == "OPTIONS":
        return _resp(204, {}, ALLOWED_ORIGINS)

    try:
        data = json.loads(request.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "invalid json"}, ALLOWED_ORIGINS)

    tok = data.get("one_time_token")
    if not tok:
        return _resp(400, {"error": "missing one_time_token"}, ALLOWED_ORIGINS)

    if not _redis:
        # ohne Redis kann Serverless den Single-Use nicht garantieren
        return _resp(200, {"ok": True, "note": "no Redis configured"}, ALLOWED_ORIGINS)

    try:
        val = _redis.execute_command("GETDEL", f"one_time:{tok}")
        if not val:
            return _resp(400, {"error": "invalid_or_used_token"}, ALLOWED_ORIGINS)
    except Exception:
        pipe = _redis.pipeline()
        pipe.get(f"one_time:{tok}")
        pipe.delete(f"one_time:{tok}")
        got, _ = pipe.execute()
        if not got:
            return _resp(400, {"error": "invalid_or_used_token"}, ALLOWED_ORIGINS)

    return _resp(200, {"ok": True}, ALLOWED_ORIGINS)
