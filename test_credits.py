#!/usr/bin/env python3
"""
Credits System Integration Test
Tests: key creation, credits balance, 402 rejection, job submission,
       simulated completion, credit deduction, account job history.

Usage:
    python3 test_credits.py
    python3 test_credits.py --url https://www.racoonn.me --password adminPiigu888
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="https://www.racoonn.me")
parser.add_argument("--password", default="adminPiigu888")
args = parser.parse_args()

BASE = args.url.rstrip("/")
PASS = args.password
CREDITS_PER_SECOND = 0.035
TEST_DURATION = 10
EXPECTED_COST = round(TEST_DURATION * CREDITS_PER_SECOND, 4)

PASS_MARK = "✅"
FAIL_MARK = "❌"
results = []


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def request(method, path, body=None, api_key=None, admin=False):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if admin:
        headers["X-Admin-Password"] = PASS
    if api_key:
        headers["X-API-Key"] = api_key
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, condition, detail=""):
    mark = PASS_MARK if condition else FAIL_MARK
    print(f"  {mark} {name}" + (f"  ({detail})" if detail else ""))
    results.append((name, condition))
    return condition


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── Tests ─────────────────────────────────────────────────────────────────────

section("1. Health Check")
code, body = request("GET", "/health")
check("Service is up", code == 200, f"status={body.get('status')}")

# ── 2. Admin Auth ─────────────────────────────────────────────────────────────
section("2. Admin Authentication")
code, _ = request("GET", "/v1/admin/keys")
check("No password → 401", code == 401)

code, _ = request("GET", "/v1/admin/keys", admin=True)
check("Correct password → 200", code == 200)

code, body = request("GET", "/v1/admin/keys",
                     api_key=None,
                     admin=False)
# override headers manually for wrong password test
import urllib.request as _ur
req = _ur.Request(BASE + "/v1/admin/keys",
                  headers={"X-Admin-Password": "wrongpassword", "Content-Type": "application/json"},
                  method="GET")
try:
    with _ur.urlopen(req, timeout=10) as r:
        code, body = r.status, json.loads(r.read())
except urllib.error.HTTPError as e:
    code, body = e.code, json.loads(e.read())
check("Wrong password → 403", code == 403)

# ── 3. Create API Keys ────────────────────────────────────────────────────────
section("3. Create API Keys")

# Key with enough credits
code, body = request("POST", "/v1/admin/keys",
                     {"name": f"__test_full_{int(time.time())}", "credits": 10.0},
                     admin=True)
check("Create key with 10 credits → 200", code == 200)
check("Response has api_key field", "api_key" in body)
FULL_KEY = body.get("api_key", "")
print(f"     api_key: {FULL_KEY[:24]}...")

# Key with 0 credits
code, body = request("POST", "/v1/admin/keys",
                     {"name": f"__test_zero_{int(time.time())}", "credits": 0.0},
                     admin=True)
check("Create key with 0 credits → 200", code == 200)
ZERO_KEY = body.get("api_key", "")

# ── 4. View raw_key in listing ────────────────────────────────────────────────
section("4. API Key Visibility")
code, body = request("GET", "/v1/admin/keys", admin=True)
check("List keys → 200", code == 200)

keys = body.get("keys", [])
test_keys = [k for k in keys if k["name"].startswith("__test_full_")]
if test_keys:
    k = test_keys[0]
    check("raw_key stored and returned", bool(k.get("raw_key")),
          f"raw_key={k.get('raw_key','')[:20]}...")
else:
    check("raw_key stored and returned", False, "test key not found in list")

# ── 5. Account Usage ──────────────────────────────────────────────────────────
section("5. Account Usage Endpoint")
code, body = request("GET", "/v1/account/usage", api_key=FULL_KEY)
check("GET /v1/account/usage → 200", code == 200)
check("credits = 10.0", abs(body.get("credits", 0) - 10.0) < 0.001,
      f"credits={body.get('credits')}")
check("credits_used = 0.0", body.get("credits_used", -1) == 0.0)
print(f"     credits={body.get('credits')}, credits_used={body.get('credits_used')}")

# ── 6. Credits Check at Submit ────────────────────────────────────────────────
section("6. Credits Check at Submit (402)")

# Use a real image URL for the test
DUMMY_IMAGE = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/240px-PNG_transparency_demonstration_1.png"

code, body = request("POST", "/v1/generate",
                     {"image_url": DUMMY_IMAGE, "position": "cowgirl", "duration": 10},
                     api_key=ZERO_KEY)
check("0-credit key → 402", code == 402)
detail = body.get("detail", {})
check("Error says 'Insufficient credits'", detail.get("error") == "Insufficient credits",
      f"error={detail.get('error')}")
check(f"required = {EXPECTED_COST}", abs(detail.get("required", 0) - EXPECTED_COST) < 0.001,
      f"required={detail.get('required')}")
check("available = 0.0", detail.get("available", -1) == 0.0,
      f"available={detail.get('available')}")

# ── 7. Submit Job (full-credit key) ──────────────────────────────────────────
section("7. Submit Generate Job")
code, body = request("POST", "/v1/generate",
                     {"image_url": DUMMY_IMAGE, "position": "cowgirl", "duration": TEST_DURATION},
                     api_key=FULL_KEY)
check("Submit with enough credits → 200", code == 200, f"status={body.get('status')}")
check("Response has job_id", "job_id" in body)
JOB_ID = body.get("job_id", "")
print(f"     job_id: {JOB_ID}, queue_position: {body.get('position_in_queue')}")

# ── 8. Simulate Job Completion + Credit Deduction ─────────────────────────────
section("8. Simulate Completion & Credit Deduction")
if not JOB_ID:
    check("Job ID available for simulation", False, "skipping")
else:
    time.sleep(1)  # let the job settle in Redis
    code, body = request("POST", f"/v1/admin/simulate-complete?job_id={JOB_ID}", admin=True)
    check("Simulate complete → 200", code == 200, f"body={body}")
    check("Credits deducted (deduction_ok=True)", body.get("deduction_ok") is True,
          f"deduction_ok={body.get('deduction_ok')}")
    check(f"Cost = {EXPECTED_COST}", abs(body.get("credits_deducted", 0) - EXPECTED_COST) < 0.001,
          f"deducted={body.get('credits_deducted')}")
    print(f"     deducted={body.get('credits_deducted')}, ok={body.get('deduction_ok')}")

# ── 9. Verify Balance After Deduction ────────────────────────────────────────
section("9. Balance After Deduction")
time.sleep(1)
code, body = request("GET", "/v1/account/usage", api_key=FULL_KEY)
check("GET /v1/account/usage → 200", code == 200)

expected_remaining = round(10.0 - EXPECTED_COST, 4)
actual_credits = round(body.get("credits", 0), 4)
actual_used = round(body.get("credits_used", 0), 4)

check(f"credits = {expected_remaining}", abs(actual_credits - expected_remaining) < 0.001,
      f"actual={actual_credits}")
check(f"credits_used = {EXPECTED_COST}", abs(actual_used - EXPECTED_COST) < 0.001,
      f"actual={actual_used}")
print(f"     Before: 10.0 → After: {actual_credits} (used {actual_used})")

# ── 10. Account Job History ───────────────────────────────────────────────────
section("10. Account Job History")
code, body = request("GET", "/v1/account/jobs", api_key=FULL_KEY)
check("GET /v1/account/jobs → 200", code == 200)
check("total >= 1", body.get("total", 0) >= 1, f"total={body.get('total')}")

if body.get("jobs"):
    j = body["jobs"][0]
    check("Job has credits_charged", j.get("credits_charged", -1) >= 0,
          f"credits_charged={j.get('credits_charged')}")
    print(f"     job_id={j['job_id']}, status={j['status']}, credits_charged={j.get('credits_charged')}")

# ── 11. Admin Jobs List with Runtime ─────────────────────────────────────────
section("11. Admin Jobs List (runtime field)")
code, body = request("GET", "/v1/admin/jobs?page=1&limit=5&status=completed", admin=True)
check("GET /v1/admin/jobs → 200", code == 200)

if body.get("jobs"):
    j = body["jobs"][0]
    check("runtime_seconds present", j.get("runtime_seconds") is not None,
          f"runtime={j.get('runtime_seconds')}s")
    check("prompt field present", "prompt" in j)
    print(f"     runtime={j.get('runtime_seconds')}s, prompt='{j.get('prompt','')[:40]}'")

# ── 12. Top Up Credits ────────────────────────────────────────────────────────
section("12. Top Up Credits")
zero_key_hash = None
code, listing = request("GET", "/v1/admin/keys", admin=True)
for k in listing.get("keys", []):
    if k.get("raw_key") == ZERO_KEY:
        zero_key_hash = k["key_hash"]
        break

if zero_key_hash:
    code, body = request("PATCH", f"/v1/admin/keys/{zero_key_hash}/topup",
                         {"add_credits": 5.0}, admin=True)
    check("Top up 5 credits → 200", code == 200, f"body={body}")
    # Verify balance updated
    time.sleep(1)
    code, usage = request("GET", "/v1/account/usage", api_key=ZERO_KEY)
    check("Balance updated to 5.0", abs(usage.get("credits", 0) - 5.0) < 0.001,
          f"credits={usage.get('credits')}")
else:
    check("Top up (key hash found)", False, "could not find zero key in listing")

# ── 13. Disable / Enable Key ──────────────────────────────────────────────────
section("13. Disable / Enable Key")
# Use the full key
full_key_hash = None
code, listing = request("GET", "/v1/admin/keys", admin=True)
for k in listing.get("keys", []):
    if k.get("raw_key") == FULL_KEY:
        full_key_hash = k["key_hash"]
        break

if full_key_hash:
    # Disable
    code, body = request("PATCH", f"/v1/admin/keys/{full_key_hash}/disable",
                         {"disabled": True}, admin=True)
    check("Disable key → 200", code == 200)
    time.sleep(1)
    code, _ = request("GET", "/v1/account/usage", api_key=FULL_KEY)
    check("Disabled key → 403", code == 403)

    # Re-enable
    code, body = request("PATCH", f"/v1/admin/keys/{full_key_hash}/disable",
                         {"disabled": False}, admin=True)
    check("Re-enable key → 200", code == 200)
    time.sleep(1)
    code, _ = request("GET", "/v1/account/usage", api_key=FULL_KEY)
    check("Re-enabled key → 200", code == 200)
else:
    check("Disable/enable (key hash found)", False, "could not find full key in listing")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"  Passed: {passed}/{total}")
if failed:
    print(f"\n  Failed tests:")
    for name, ok in results:
        if not ok:
            print(f"    {FAIL_MARK} {name}")
print()
sys.exit(0 if failed == 0 else 1)
