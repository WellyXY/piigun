#!/usr/bin/env python3
"""
Credits System Integration Test
Uses curl for HTTP requests (avoids SSL cert issues on macOS).

Usage:
    python3 test_credits.py
    python3 test_credits.py --url https://www.racoonn.me --password adminPiigu888
"""
import argparse
import json
import subprocess
import sys
import time

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

def curl(method, path, body=None, api_key=None, admin=False):
    """Run curl and return (status_code, parsed_json)."""
    cmd = ["curl", "-s", "-w", "\n__STATUS__%{http_code}", "-X", method]
    cmd += ["-H", "Content-Type: application/json"]
    if admin:
        cmd += ["-H", f"X-Admin-Password: {PASS}"]
    if api_key:
        cmd += ["-H", f"X-API-Key: {api_key}"]
    if body:
        cmd += ["-d", json.dumps(body)]
    cmd.append(BASE + path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout
    # Split body and status code
    if "__STATUS__" in output:
        raw_body, status_str = output.rsplit("__STATUS__", 1)
        status = int(status_str.strip())
    else:
        raw_body = output
        status = 0

    raw_body = raw_body.strip()
    try:
        parsed = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        parsed = {"_raw": raw_body}
    return status, parsed


def check(name, condition, detail=""):
    mark = PASS_MARK if condition else FAIL_MARK
    msg = f"  {mark} {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    results.append((name, condition))
    return condition


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── Tests ─────────────────────────────────────────────────────────────────────

section("1. Health Check")
code, body = curl("GET", "/health")
check("Service is up", code == 200, f"status={body.get('status')}")

# ── 2. Admin Auth ─────────────────────────────────────────────────────────────
section("2. Admin Authentication")
code, _ = curl("GET", "/v1/admin/keys")
check("No password → 401", code == 401)

code, _ = curl("GET", "/v1/admin/keys", admin=True)
check("Correct password → 200", code == 200)

# Test wrong password via curl directly
result = subprocess.run(
    ["curl", "-s", "-w", "\n__STATUS__%{http_code}", "-H", "X-Admin-Password: wrongpassword",
     BASE + "/v1/admin/keys"],
    capture_output=True, text=True, timeout=30
)
out = result.stdout
_, st = out.rsplit("__STATUS__", 1)
check("Wrong password → 403", int(st.strip()) == 403)

# ── 3. Create API Keys ────────────────────────────────────────────────────────
section("3. Create API Keys")
ts = int(time.time())

code, body = curl("POST", "/v1/admin/keys",
                  {"name": f"__test_full_{ts}", "credits": 10.0}, admin=True)
check("Create key with 10 credits → 200", code == 200)
check("Response has api_key", "api_key" in body)
FULL_KEY = body.get("api_key", "")
print(f"     api_key: {FULL_KEY[:24]}...")

code, body = curl("POST", "/v1/admin/keys",
                  {"name": f"__test_zero_{ts}", "credits": 0.0}, admin=True)
check("Create key with 0 credits → 200", code == 200)
ZERO_KEY = body.get("api_key", "")

# ── 4. View raw_key in listing ────────────────────────────────────────────────
section("4. API Key Visibility (raw_key)")
code, body = curl("GET", "/v1/admin/keys", admin=True)
check("List keys → 200", code == 200)
keys = body.get("keys", [])
test_keys = [k for k in keys if k["name"].startswith(f"__test_full_{ts}")]
if test_keys:
    k = test_keys[0]
    has_raw = bool(k.get("raw_key"))
    check("raw_key stored and returned", has_raw,
          f"raw_key={k.get('raw_key','')[:20]}...")
else:
    check("raw_key stored and returned", False, "test key not found in listing")

# ── 5. Account Usage ──────────────────────────────────────────────────────────
section("5. Account Usage")
code, body = curl("GET", "/v1/account/usage", api_key=FULL_KEY)
check("GET /v1/account/usage → 200", code == 200)
check("credits = 10.0", abs(body.get("credits", 0) - 10.0) < 0.001,
      f"credits={body.get('credits')}")
check("credits_used = 0.0", body.get("credits_used", -1) == 0.0)
print(f"     credits={body.get('credits')}, credits_used={body.get('credits_used')}")

# ── 6. Credits Check (402) ────────────────────────────────────────────────────
section("6. Credits Check at Submit (402 Insufficient)")
# 1x1 white JPEG in base64
DUMMY_B64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVIP/2Q=="

code, body = curl("POST", "/v1/generate",
                  {"image_base64": DUMMY_B64, "position": "cowgirl", "duration": TEST_DURATION},
                  api_key=ZERO_KEY)
check("0-credit key → 402", code == 402)
detail = body.get("detail", {})
check("error = 'Insufficient credits'", detail.get("error") == "Insufficient credits",
      f"error={detail.get('error')}")
check(f"required = {EXPECTED_COST}", abs(detail.get("required", 0) - EXPECTED_COST) < 0.001,
      f"required={detail.get('required')}")
check("available = 0.0", detail.get("available", -1) == 0.0,
      f"available={detail.get('available')}")

# ── 7. Submit Job ─────────────────────────────────────────────────────────────
section("7. Submit Generate Job (10 credits key)")
code, body = curl("POST", "/v1/generate",
                  {"image_base64": DUMMY_B64, "position": "cowgirl", "duration": TEST_DURATION},
                  api_key=FULL_KEY)
check("Submit with credits → 200", code == 200, f"status={body.get('status')}")
check("Response has job_id", "job_id" in body)
JOB_ID = body.get("job_id", "")
print(f"     job_id={JOB_ID}, queue_pos={body.get('position_in_queue')}")

# ── 8. Simulate Completion + Deduction ───────────────────────────────────────
section("8. Simulate Job Completion & Credit Deduction")
if not JOB_ID:
    check("Job ID available", False, "skipping")
else:
    time.sleep(1)
    code, body = curl("POST", f"/v1/admin/simulate-complete?job_id={JOB_ID}", admin=True)
    check("simulate-complete → 200", code == 200, str(body))
    check("deduction_ok = True", body.get("deduction_ok") is True,
          f"deduction_ok={body.get('deduction_ok')}")
    check(f"credits_deducted = {EXPECTED_COST}",
          abs(body.get("credits_deducted", 0) - EXPECTED_COST) < 0.001,
          f"deducted={body.get('credits_deducted')}")
    print(f"     deducted={body.get('credits_deducted')}, ok={body.get('deduction_ok')}")

# ── 9. Verify Balance After Deduction ────────────────────────────────────────
section("9. Balance After Deduction")
time.sleep(1)
code, body = curl("GET", "/v1/account/usage", api_key=FULL_KEY)
check("GET /v1/account/usage → 200", code == 200)
expected_remaining = round(10.0 - EXPECTED_COST, 4)
actual = round(body.get("credits", 0), 4)
used = round(body.get("credits_used", 0), 4)
check(f"credits = {expected_remaining}", abs(actual - expected_remaining) < 0.001,
      f"actual={actual}")
check(f"credits_used = {EXPECTED_COST}", abs(used - EXPECTED_COST) < 0.001,
      f"actual={used}")
print(f"     Before: 10.0 → After: {actual}  (used {used})")

# ── 10. Account Job History ───────────────────────────────────────────────────
section("10. Account Job History")
code, body = curl("GET", "/v1/account/jobs", api_key=FULL_KEY)
check("GET /v1/account/jobs → 200", code == 200)
check("total >= 1", body.get("total", 0) >= 1, f"total={body.get('total')}")
if body.get("jobs"):
    j = body["jobs"][0]
    check("credits_charged present", j.get("credits_charged", -1) >= 0,
          f"credits_charged={j.get('credits_charged')}")
    print(f"     job={j['job_id']}, status={j['status']}, credits_charged={j.get('credits_charged')}")

# ── 11. Admin Jobs with Runtime ───────────────────────────────────────────────
section("11. Admin Jobs — Runtime & Prompt Fields")
code, body = curl("GET", "/v1/admin/jobs?page=1&limit=5&status=completed", admin=True)
check("GET /v1/admin/jobs → 200", code == 200)
if body.get("jobs"):
    j = body["jobs"][0]
    check("runtime_seconds present", j.get("runtime_seconds") is not None,
          f"runtime={j.get('runtime_seconds')}s")
    check("prompt field present", "prompt" in j)
    print(f"     runtime={j.get('runtime_seconds')}s, prompt='{j.get('prompt','')[:40]}'")

# ── 12. Top Up Credits ────────────────────────────────────────────────────────
section("12. Top Up Credits")
code, listing = curl("GET", "/v1/admin/keys", admin=True)
zero_hash = next((k["key_hash"] for k in listing.get("keys", [])
                  if k.get("raw_key") == ZERO_KEY), None)
if zero_hash:
    code, body = curl("PATCH", f"/v1/admin/keys/{zero_hash}/topup",
                      {"add_credits": 5.0}, admin=True)
    check("Top up 5 credits → 200", code == 200)
    time.sleep(1)
    code, usage = curl("GET", "/v1/account/usage", api_key=ZERO_KEY)
    check("Balance updated to 5.0",
          abs(usage.get("credits", 0) - 5.0) < 0.001,
          f"credits={usage.get('credits')}")
else:
    check("Top up (key hash found)", False, "zero key not in listing")

# ── 13. Disable / Enable Key ──────────────────────────────────────────────────
section("13. Disable / Enable Key")
code, listing = curl("GET", "/v1/admin/keys", admin=True)
full_hash = next((k["key_hash"] for k in listing.get("keys", [])
                  if k.get("raw_key") == FULL_KEY), None)
if full_hash:
    code, _ = curl("PATCH", f"/v1/admin/keys/{full_hash}/disable",
                   {"disabled": True}, admin=True)
    check("Disable key → 200", code == 200)
    time.sleep(1)
    code, _ = curl("GET", "/v1/account/usage", api_key=FULL_KEY)
    check("Disabled key → 403", code == 403)

    code, _ = curl("PATCH", f"/v1/admin/keys/{full_hash}/disable",
                   {"disabled": False}, admin=True)
    check("Re-enable key → 200", code == 200)
    time.sleep(1)
    code, _ = curl("GET", "/v1/account/usage", api_key=FULL_KEY)
    check("Re-enabled key → 200", code == 200)
else:
    check("Disable/enable (key found)", False, "full key not in listing")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"  Passed: {passed}/{len(results)}")
if failed:
    print(f"\n  Failed:")
    for name, ok in results:
        if not ok:
            print(f"    {FAIL_MARK} {name}")
print()
sys.exit(0 if failed == 0 else 1)
