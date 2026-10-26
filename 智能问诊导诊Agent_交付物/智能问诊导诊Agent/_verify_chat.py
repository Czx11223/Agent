import requests, uuid, re, json

base = "http://127.0.0.1:8000/api/v1"
u = "v_" + uuid.uuid4().hex[:6]
r = requests.post(base + "/auth/register", json={"username": u, "password": "pass123456"}, timeout=15)
r.raise_for_status()
tok = r.json()["token"]
h = {"Authorization": "Bearer " + tok}
cv = requests.post(base + "/conversations", json={"title": "眼睛"}, headers=h, timeout=15).json()["conversation_id"]
resp = requests.post(base + "/chat/stream", headers=h, json={"conversation_id": cv, "content": "我眼睛不舒服"}, timeout=30)
txt = resp.text
print("conv=", cv, "status=", resp.status_code, "len=", len(txt))
events = sorted(set(re.findall(r"event:\s*(\w+)", txt)))
print("events=", events)
texts = re.findall(r'"text":"([^"]*)"', txt)
for t in texts[:3]:
    print("REPLY:", t[:80])