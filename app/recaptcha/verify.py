import os, uuid, json, requests, redis

RECAPTCHA_SECRET = os.environ.get("RECAPTCHA_SECRET")
REDIS_URL = os.environ.get("REDIS_URL")

# CORS Allowlist aus ENV
ALLOWED_ORIGINS_ENV = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
if not ALLOWED:
    ALLOWED = ["*"]  # nur für Tests; in Prod exakt Origins setzen

# Redis
_redis = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
ONE_TIME_TTL_SECONDS = 300

def _cors_origin(request):
    origin = None
    try:
        headers = request.get("headers") or {}
        origin = headers.get("origin") or headers.get("Origin")
    except Exception:
        pass
    if "*" in ALLOWED:
        return "*"  # nur wenn keine Cookies/Credentials verwendet werden
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

    token = data.get("token")
    if not token:
        return _resp(400, {"error": "missing token"}, origin)
    if not RECAPTCHA_SECRET:
        return _resp(500, {"error": "RECAPTCHA_SECRET not configured"}, origin)

    # Google Verify
    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": RECAPTCHA_SECRET, "response": token},
            timeout=10,
        )
    except requests.RequestException as e:
        return _resp(502, {"error": "upstream request failed", "detail": str(e)}, origin)

    if "application/json" not in (r.headers.get("content-type") or ""):
        return _resp(502, {"error": "upstream non-json", "upstream": r.text[:200]}, origin)

    js = r.json()
    if not js.get("success"):
        return _resp(400, {"error": "recaptcha invalid", "details": js}, origin)

    # One-time Token
    one_time = str(uuid.uuid4())
    if _redis:
        _redis.setex(f"one_time:{one_time}", ONE_TIME_TTL_SECONDS, "1")

    return _resp(201, {"one_time_token": one_time, "ttl": ONE_TIME_TTL_SECONDS}, origin)
