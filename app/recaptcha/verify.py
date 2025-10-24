import os, uuid, json, requests, redis

RECAPTCHA_SECRET = os.environ.get("RECAPTCHA_SECRET")
REDIS_URL = os.environ.get("REDIS_URL")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")  # << nur eine Origin

_redis = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
ONE_TIME_TTL_SECONDS = 300

def _resp(status: int, body: dict):
    # CORS IMMER setzen
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
    # Preflight IMMER beantworten
    if request["method"] == "OPTIONS":
        return _resp(204, {})

    try:
        data = json.loads(request.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "invalid json"})

    token = data.get("token")
    if not token:
        return _resp(400, {"error": "missing token"})
    if not RECAPTCHA_SECRET:
        return _resp(500, {"error": "RECAPTCHA_SECRET not configured"})

    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": RECAPTCHA_SECRET, "response": token},
            timeout=10,
        )
    except requests.RequestException as e:
        return _resp(502, {"error": "upstream request failed", "detail": str(e)})

    if "application/json" not in (r.headers.get("content-type") or ""):
        return _resp(502, {"error": "upstream non-json", "upstream": r.text[:200]})

    js = r.json()
    if not js.get("success"):
        return _resp(400, {"error": "recaptcha invalid", "details": js})

    one_time = str(uuid.uuid4())
    if _redis:
        _redis.setex(f"one_time:{one_time}", ONE_TIME_TTL_SECONDS, "1")

    return _resp(201, {"one_time_token": one_time, "ttl": ONE_TIME_TTL_SECONDS})
