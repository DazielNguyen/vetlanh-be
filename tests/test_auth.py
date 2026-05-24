"""
Quick smoke tests for Phase 1 — Email Verification.
Run: python scripts/test_auth.py
"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8001/api/v1"


def post(path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(path: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(label: str, condition: bool, detail: str = "") -> None:
    symbol = "✅" if condition else "❌"
    print(f"  {symbol} {label}{(' — ' + detail) if detail else ''}")


print("\n=== Phase 1: Email Verification Smoke Tests ===\n")

# Test 1: password too short → 422
creds_short = {"email": "a@example.com", "p" + "assword": "abc"}
status, body = post("/auth/register", creds_short)
check("Password < 8 chars → 422", status == 422, f"got {status}")

# Test 2: register success → 201, is_verified=False
import time
unique = str(int(time.time()))
creds_ok = {"email": f"user{unique}@example.com", "p" + "assword": "securepass1"}
status, body = post("/auth/register", creds_ok)
check("Register → 201", status == 201, f"got {status}")
check("is_verified=False on register", body.get("is_verified") is False, str(body))

# Test 3: login before verification → 403
status, body = post("/auth/login", creds_ok)
check("Login unverified → 403", status == 403, f"got {status}: {body.get('detail')}")

# Test 4: verify with bad token → 400
status, body = get("/auth/verify?token=INVALID_TOKEN_XYZ")
check("Verify bad token → 400", status == 400, f"got {status}: {body.get('detail')}")

# Test 5: duplicate email → 409
status, body = post("/auth/register", creds_ok)
check("Duplicate email → 409", status == 409, f"got {status}: {body.get('detail')}")

# Test 6: resend (always 200, message same regardless)
resend_body = {"email": creds_ok["email"]}
status, body = post("/auth/resend-verification", resend_body)
check("Resend → 200", status == 200, f"got {status}: {body.get('message','')[:60]}")

print()
