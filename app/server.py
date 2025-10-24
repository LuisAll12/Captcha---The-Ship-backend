# recaptcha_token_server.py
import uuid
import time
from decimal import Decimal
from flask import Flask, request, jsonify
import requests
import os

# Optional: use redis if available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

app = Flask(__name__)

GOOGLE_SECRET = os.environ.get("RECAPTCHA_SECRET")  # set secret in env
ONE_TIME_TTL_SECONDS = 300  # 5 minutes

if REDIS_AVAILABLE:
    r = redis.StrictRedis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
else:
    # fallback: in-memory store {token: (expiry_ts, used_flag, metadata)}
    INMEM = {}

def store_token(token: str, ttl: int = ONE_TIME_TTL_SECONDS, meta: dict = None):
    if REDIS_AVAILABLE:
        key = f"one_time:{token}"
        payload = "unused"
        r.setex(key, ttl, payload)
        if meta:
            r.hset(f"{key}:meta", mapping=meta)
    else:
        INMEM[token] = (time.time() + ttl, False, meta or {})

def consume_token(token: str):
    if REDIS_AVAILABLE:
        key = f"one_time:{token}"
        val = r.get(key)
        if not val:
            return False
        # delete to consume (atomic)
        r.delete(key)
        return True
    else:
        tup = INMEM.get(token)
        if not tup:
            return False
        expiry, used, meta = tup
        if time.time() > expiry or used:
            INMEM.pop(token, None)
            return False
        # mark used (or remove)
        INMEM.pop(token, None)
        return True

@app.route("/recaptcha/verify", methods=["POST"])
def verify_recaptcha():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    if not token:
        return jsonify(error="missing token"), 400
    if not GOOGLE_SECRET:
        return jsonify(error="server misconfiguration: no RECAPTCHA_SECRET"), 500

    # verify with Google
    r = requests.post("https://www.google.com/recaptcha/api/siteverify", data={
        "secret": GOOGLE_SECRET,
        "response": token
    }, timeout=10)
    if r.status_code != 200:
        return jsonify(error="verification failed with Google"), 502
    js = r.json()
    if not js.get("success"):
        return jsonify(error="recaptcha invalid", details=js), 400

    # success: create one-time token
    one_time = str(uuid.uuid4())
    meta = {"remote_ip": request.remote_addr, "score": js.get("score")}
    store_token(one_time, ONE_TIME_TTL_SECONDS, meta)
    return jsonify(one_time_token=one_time, ttl=ONE_TIME_TTL_SECONDS), 201

@app.route("/hack/consume", methods=["POST"])
def hack_consume():
    data = request.get_json(silent=True) or {}
    token = data.get("one_time_token")
    player_id = data.get("player_id")  # optional: map to player
    if not token:
        return jsonify(error="missing one_time_token"), 400

    ok = consume_token(token)
    if not ok:
        return jsonify(error="invalid or used token"), 400

    # Simulated reward: mark player as "hacker" or credit points
    # In CTF: just return success and award only virtual points.
    # Example:
    points = 100
    # TODO: update player score in DB or Redis
    return jsonify(ok=True, awarded_points=points, message="Token consumed. You are registered as hacker in the simulation."), 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=True)
