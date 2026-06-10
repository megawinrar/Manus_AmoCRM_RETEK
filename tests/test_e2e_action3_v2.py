"""
E2E Test v2: Action 3 — Yandex Disk path in note triggers file recognition.
Fixed: sends entity_id in webhook payload (not just id).

Run with: python3 tests/test_e2e_action3_v2.py
"""

import os
import sys
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

AMO_DOMAIN = os.getenv("AMO_DOMAIN", "tokutools.amocrm.ru")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
PIPELINE_ID = int(os.getenv("AMO_PIPELINE_ACTIVE_ID", "10984442"))
WEBHOOK_URL = "http://89.169.142.160/webhook"
TEST_YADISK_PATH = "/ТОРГИ/09.06.2026/Протон-ПМ - Твердосплав зенкер/"

HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"


def create_test_lead():
    """Create a test lead in amoCRM."""
    payload = [{
        "name": "[E2E-TEST-v2] Action3 — Протон-ПМ зенкер",
        "pipeline_id": PIPELINE_ID,
        "status_id": 86357690,
    }]
    resp = requests.post(f"{BASE_URL}/leads", headers=HEADERS, json=payload, timeout=10)
    if resp.status_code not in (200, 201):
        print(f"❌ Failed to create lead: {resp.status_code} {resp.text[:200]}")
        return None
    lead_id = resp.json()["_embedded"]["leads"][0]["id"]
    print(f"✅ Created test lead: {lead_id}")
    return lead_id


def simulate_webhook_with_entity_id(lead_id: int):
    """Send a webhook payload with correct entity_id."""
    note_text = f"распознай disk:{TEST_YADISK_PATH}"
    
    # amoCRM sends form-encoded data with these fields for notes[add]
    webhook_data = {
        "notes[add][0][id]": "99999999",  # note_id (should be ignored)
        "notes[add][0][entity_id]": str(lead_id),  # THIS is the real lead_id
        "notes[add][0][entity_type]": "leads",
        "notes[add][0][note_type]": "common",
        "notes[add][0][text]": note_text,
    }
    
    print(f"📡 Sending webhook to {WEBHOOK_URL} with entity_id={lead_id}...")
    
    try:
        resp = requests.post(WEBHOOK_URL, data=webhook_data, timeout=30)
        print(f"   Response: {resp.status_code} {resp.text[:300]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ Webhook failed: {e}")
        return False


def check_lead_fields(lead_id: int, max_wait: int = 90):
    """Wait and check if lead fields were populated by Action 3."""
    print(f"⏳ Waiting up to {max_wait}s for fields to be populated...")
    
    FIELD_CUSTOMER = 380299
    FIELD_NMC = 380315
    FIELD_DIRECTION = 380311
    
    for i in range(0, max_wait, 10):
        time.sleep(10)
        
        resp = requests.get(f"{BASE_URL}/leads/{lead_id}", headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"   [{i+10}s] Failed to get lead: {resp.status_code}")
            continue
        
        lead = resp.json()
        custom_fields = lead.get("custom_fields_values") or []
        
        filled = {}
        for cf in custom_fields:
            fid = cf["field_id"]
            val = cf.get("values", [{}])[0].get("value", "")
            if fid == FIELD_CUSTOMER and val:
                filled["customer"] = val
            elif fid == FIELD_NMC and val:
                filled["nmc"] = val
            elif fid == FIELD_DIRECTION and val:
                filled["direction"] = val
        
        if filled:
            print(f"   [{i+10}s] ✅ Fields populated: {filled}")
            return True, filled
        else:
            print(f"   [{i+10}s] ... no fields yet")
    
    print(f"❌ Fields not populated after {max_wait}s")
    return False, {}


def main():
    print("=" * 60)
    print("E2E TEST v2: Action 3 — Yandex Disk → File Recognition")
    print("=" * 60)
    print()
    
    # Step 1: Create lead
    lead_id = create_test_lead()
    if not lead_id:
        return 1
    
    time.sleep(2)
    
    # Step 2: Simulate webhook with correct entity_id
    webhook_ok = simulate_webhook_with_entity_id(lead_id)
    if not webhook_ok:
        return 1
    
    # Step 3: Check if fields were populated
    result, fields = check_lead_fields(lead_id, max_wait=90)
    
    print()
    print("=" * 60)
    if result:
        print("🎉 E2E TEST PASSED: Action 3 works correctly!")
        print(f"   Fields: {fields}")
    else:
        print("⚠️  E2E TEST: Fields not auto-populated (check logs)")
        print(f"   Lead URL: https://{AMO_DOMAIN}/leads/detail/{lead_id}")
    print("=" * 60)
    
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
