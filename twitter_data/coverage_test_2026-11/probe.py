"""One cheap request to see whether the account's credit is live. Costs at most $0.05. Prints status and headers only."""
import ssl, certifi, json, pathlib, urllib.parse, urllib.request, urllib.error
tok = (pathlib.Path.home() / ".config/x_api/bearer_token").read_text().strip()
params = {"query": "ivermectin -is:retweet", "max_results": 10, "tweet.fields": "created_at,lang"}
url = "https://api.x.com/2/tweets/search/recent?" + urllib.parse.urlencode(params)
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "User-Agent": "patientpunk-probe"})
try:
    with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as r:
        body = json.loads(r.read().decode())
        print("HTTP", r.status, "| posts returned:", len(body.get("data", [])), "| newest:", (body.get("data") or [{}])[0].get("created_at"))
        print("headers:", {k: v for k, v in r.headers.items() if k.lower().startswith(("x-rate-limit", "x-app", "x-credit", "x-usage", "x-cost"))})
except urllib.error.HTTPError as e:
    print("HTTP", e.code, "|", e.read().decode(errors="replace")[:400])
    print("headers:", {k: v for k, v in e.headers.items() if k.lower().startswith(("x-rate-limit", "x-app", "x-credit", "x-usage", "x-cost", "www-auth"))})
