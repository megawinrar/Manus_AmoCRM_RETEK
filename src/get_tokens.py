"""
Обмен authorization code на access_token + refresh_token,
затем получение всех статусов, пользователей и кастомных полей.
"""
import json
import time
import requests

DOMAIN = "tokutools.amocrm.ru"
CLIENT_ID = "13b2e6f9-5634-4dd0-82e3-409a438d075a"
CLIENT_SECRET = "RHj23DMYtuFK3vobFY4B5pXy9N9HRLJkbuE1fB7AxlkDrVDe4QslLZ4bT9cTgv9y"
AUTH_CODE = "def5020054fe10a3d3401075435e45583af71d9a98f24f4d88282ce9b430f4707aa68fa9cd30bfee4c9228dd50abaeeb27bbbae38a7e01483b8f2d01b5d597ada3e50ddd378014bbaa73c201b41979c93c06b9581396e7fbd5bedb132718820474833581cb604d836a1c71483c7d077bd1ca17b86e87672bcacd68f5871543ccea87984b5b41478c6976ff5167336508f87af4ab2a246a01880c3e7da8514240dadfad5eb9c1d66c51edf8cdf5253a9101d07940a23743faa7724f7053eab0e223fd5a9893634cb15558cb231ab4f4f52a3c2eb765b46bf39526dde446411d3425373a1000ccf2d56a6c21c4e1f175c2d7d0502c24d357c789006188888368d4e9fb105c31b09b8fe37e8755a546a495338492a525017e5e2e989f9fd0cd5879cbde850c61e53f02906fa1227c63813f272c1cef52aa35256ee31e694a0b0efbf62a58182a5feb94b286c4a7cf693bf8ca3bf60e9196b25a5f94e0cceab5c0067a0541c173d97dd11a1be4a0483ece4ce391ed01b62c5128ae3f0443965e509267538a1e7ce626e91295d2f14eb20d874e4e75d96f4edcb48fdc2328991fae7d187ad185827cf2294a623f1e8044e21b8437a170a25e0af2234851c4672954e25d5de4cb1cf2997f090702f6e68bfe36dc6c0767dabc541616de95f905467c8f151f02b452f9eb2716ba6076e375"
LONG_LIVED_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjdmMmFkZWU1NDg1MTA2YzdkNjNkNmJlY2ZiODBkYTNkMzhkYmQzMmU3Y2UyYzc2NmE0NzRhMDMzMjg3ZGU1YWQ3MmUzZmE1MzlmY2ZkZDQ5In0.eyJhdWQiOiIxM2IyZTZmOS01NjM0LTRkZDAtODJlMy00MDlhNDM4ZDA3NWEiLCJqdGkiOiI3ZjJhZGVlNTQ4NTEwNmM3ZDYzZDZiZWNmYjgwZGEzZDM4ZGJkMzJlN2NlMmM3NjZhNDc0YTAzMzI4N2RlNWFkNzJlM2ZhNTM5ZmNmZGQ0OSIsImlhdCI6MTc4MDg3MzY2OCwibmJmIjoxNzgwODczNjY4LCJleHAiOjE3ODU0NTYwMDAsInN1YiI6IjEzOTAyNjQ2IiwiZ3JhbnRfdHlwZSI6IiIsImFjY291bnRfaWQiOjMzMDg5Njc0LCJiYXNlX2RvbWFpbiI6ImFtb2NybS5ydSIsInZlcnNpb24iOjIsInNjb3BlcyI6WyJwdXNoX25vdGlmaWNhdGlvbnMiLCJmaWxlcyIsImNybSIsImZpbGVzX2RlbGV0ZSIsIm5vdGlmaWNhdGlvbnMiXSwiaGFzaF91dWlkIjoiNjAwOGVmMTgtZDgyNi00Mzc2LThiZGEtMDYxNDFmYzI4NDZkIiwiYXBpX2RvbWFpbiI6ImFwaS1iLmFtb2NybS5ydSJ9.aacZUq-1dLhuxrWwzowQ_NTUbE2teoUDeYww23ocjyucMO_K4v_G9n347ciKD_0kjg6Oeh1PJGGNjCpnMLr1vi_yxkKLs3yHTwH6bofrF9iRY1D68vSsKaJMRfp-GxNYt_euGtTJ6yv0wKVyzhmNPzi7ZA925pmsH1P-tQKhZ72Rsze09XXpTS_ip35bbk1bYN6ecZYI9prE6l_S8S0Ccw4pNFbrkEyKl6WcOk_FsydRXv6I4pvA_vONWgawu_Lpmr08nwkixF_v4L1CPZlGAVP65KeRL1fPXj3qJ_17XItF6IJtycEweFR_d3mB-xvPCw4sPNZktOdo13dTiUcVeQ"

BASE_URL = f"https://{DOMAIN}"

# ─── 1. Обмен кода на токены ─────────────────────────────────────────────────
print("=" * 60)
print("1. Обмен authorization_code на токены...")
resp = requests.post(
    f"{BASE_URL}/oauth2/access_token",
    json={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": AUTH_CODE,
        "redirect_uri": "https://example.com/callback",
    },
    timeout=15,
)
print(f"Status: {resp.status_code}")
token_data = resp.json()
print(json.dumps(token_data, ensure_ascii=False, indent=2))

if resp.status_code == 200:
    ACCESS_TOKEN = token_data["access_token"]
    REFRESH_TOKEN = token_data["refresh_token"]
    EXPIRES_IN = token_data.get("expires_in", 86400)
    EXPIRES_AT = int(time.time()) + EXPIRES_IN
    print(f"\n✅ OAuth токены получены!")
else:
    print(f"\n⚠️  OAuth обмен не удался. Используем долгосрочный токен.")
    ACCESS_TOKEN = LONG_LIVED_TOKEN
    REFRESH_TOKEN = ""
    EXPIRES_AT = 1785456000  # из JWT payload (exp)

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

# ─── Проверка токена ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Проверка токена через /api/v4/account...")
r = requests.get(f"{BASE_URL}/api/v4/account", headers=HEADERS, timeout=15)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    acc = r.json()
    print(f"✅ Аккаунт: {acc.get('name')} (ID={acc.get('id')})")
else:
    print(f"❌ Ошибка: {r.text[:300]}")
    exit(1)

# ─── 2. Получение статусов всех воронок ──────────────────────────────────────
print("\n" + "=" * 60)
print("2. Получение статусов воронок...")

PIPELINE_IDS = {
    "active": 10984442,
    "archive_directions": 10984454,
    "archive_soz": 10985038,
}

all_statuses = {}
for name, pid in PIPELINE_IDS.items():
    r = requests.get(
        f"{BASE_URL}/api/v4/leads/pipelines/{pid}/statuses",
        headers=HEADERS,
        timeout=15,
    )
    if r.status_code == 200:
        data = r.json()
        statuses = data.get("_embedded", {}).get("statuses", [])
        all_statuses[name] = statuses
        print(f"\n  Воронка '{name}' (ID={pid}):")
        for s in statuses:
            print(f"    {s['id']:>12} | {s['name']}")
    else:
        print(f"  Ошибка для воронки {name}: {r.status_code} {r.text[:200]}")
        all_statuses[name] = []

# ─── 3. Получение пользователей ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. Получение пользователей...")
r = requests.get(f"{BASE_URL}/api/v4/users", headers=HEADERS, timeout=15)
users = []
if r.status_code == 200:
    data = r.json()
    users = data.get("_embedded", {}).get("users", [])
    for u in users:
        print(f"  {u['id']:>12} | {u['name']} | {u.get('email','')}")
else:
    print(f"  Ошибка: {r.status_code} {r.text[:200]}")

# ─── 4. Получение кастомных полей сделок ─────────────────────────────────────
print("\n" + "=" * 60)
print("4. Получение кастомных полей сделок...")
r = requests.get(
    f"{BASE_URL}/api/v4/leads/custom_fields",
    headers=HEADERS,
    params={"limit": 250},
    timeout=15,
)
fields = []
if r.status_code == 200:
    data = r.json()
    fields = data.get("_embedded", {}).get("custom_fields", [])
    for f in fields:
        print(f"  {f['id']:>12} | {f['name']}")
else:
    print(f"  Ошибка: {r.status_code} {r.text[:200]}")

# ─── 5. Сохранение результатов ───────────────────────────────────────────────
active_statuses = {s["name"]: s["id"] for s in all_statuses.get("active", [])}
arch_dir_statuses = {s["name"]: s["id"] for s in all_statuses.get("archive_directions", [])}
arch_soz_statuses = {s["name"]: s["id"] for s in all_statuses.get("archive_soz", [])}
user_map = {u["name"]: u["id"] for u in users}
field_map = {f["name"]: f["id"] for f in fields}

result = {
    "access_token": ACCESS_TOKEN,
    "refresh_token": REFRESH_TOKEN,
    "expires_at": EXPIRES_AT,
    "active_statuses": active_statuses,
    "arch_dir_statuses": arch_dir_statuses,
    "arch_soz_statuses": arch_soz_statuses,
    "users": user_map,
    "fields": field_map,
}

with open("/home/ubuntu/retek-amocrm-integration/amo_data.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("\n✅ Данные сохранены в amo_data.json")
