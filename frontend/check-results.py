import json

d = json.load(open("test-results-fixed.json", encoding="utf-8"))
print(f"TOTAL: {d['numTotalTests']}  PASSED: {d['numPassedTests']}  FAILED: {d['numFailedTests']}")
for t in d["testResults"]:
    if t["status"] != "failed":
        continue
    for a in t.get("assertionResults", []):
        if a.get("status") == "failed":
            print(f"  FAIL: {a.get('fullName', a.get('name', 'unknown'))}")
