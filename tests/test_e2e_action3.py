"""
E2E Test: Action 3 — Yandex Disk path in note triggers file recognition.

Flow:
1. Create a test lead in amoCRM
2. Add a note with Yandex Disk path
3. Simulate webhook call to the VM
4. Check that the lead fields are populated

NOTE: This test uses real amoCRM API and Yandex Disk.
Run with: python3 tests/test_e2e_action3.py
"""

import os
import sys
import time
import json
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

AMO_DOMAIN = os.getenv("AMO_DOMAIN", "tokutools.amocrm.ru")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
PIPELINE_ID = int(os.getenv("AMO_PIPELINE_ACTIVE_ID", "10984442"))
WEBHOOK_URL = "http://89.169.142.160/webhook"

# Test folder on Yandex Disk (known to contain tender files)
TEST_YADISK_PATH = "/ТОРГИ/09.06.2026/Протон-ПМ - Твердосплав зенкер/"

HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"


def create_test_lead():
    """Create a test lead in amoCRM."""
    payload = [{
        "name": "[E2E-TEST] Action3 — Протон-ПМ зенкер",
        "pipeline_id": PIPELINE_ID,
        "status_id": 86357690,  # "1. LLM распознал"
    }]
    
    resp = requests.post(
        f"{BASE_URL}/leads",
        headers=HEADERS,
        json=payload,
        timeout=10,
    )
    
    if resp.status_code not in (200, 201):
        print(f"❌ Failed to create lead: {resp.status_code} {resp.text[:200]}")
        return None
    
    data = resp.json()
    lead_id = data["_embedded"]["leads"][0]["id"]
    print(f"✅ Created test lead: {lead_id}")
    return lead_id


def add_note_with_yadisk_path(lead_id: int):
    """Add a note with Yandex Disk path to the lead."""
    payload = [{
        "note_type": "common",
        "params": {
            "text": f"распознай disk:{TEST_YADISK_PATH}"
        }
    }]
    
    resp = requests.post(
        f"{BASE_URL}/leads/{lead_id}/notes",
        headers=HEADERS,
        json=payload,
        timeout=10,
    )
    
    if resp.status_code not in (200, 201):
        print(f"❌ Failed to add note: {resp.status_code} {resp.text[:200]}")
        return None
    
    data = resp.json()
    note_id = data["_embedded"]["notes"][0]["id"]
    print(f"✅ Added note {note_id} with path: disk:{TEST_YADISK_PATH}")
    return note_id


def simulate_webhook(lead_id: int, note_id: int):
    """Send a webhook payload to the VM simulating amoCRM notes[add] event."""
    # amoCRM sends form-encoded webhook data
    webhook_data = {
        "leads[status][0][id]": str(lead_id),
        "leads[status][0][pipeline_id]": str(PIPELINE_ID),
        "leads[status][0][status_id]": "86357690",
    }
    
    # Also simulate notes[add] event
    note_webhook_data = {
        "notes[add][0][id]": str(note_id),
        "notes[add][0][entity_id]": str(lead_id),
        "notes[add][0][entity_type]": "leads",
        "notes[add][0][note_type]": "common",
        "notes[add][0][text]": f"распознай disk:{TEST_YADISK_PATH}",
    }
    
    print(f"📡 Sending webhook to {WEBHOOK_URL}...")
    
    try:
        resp = requests.post(
            WEBHOOK_URL,
            data=note_webhook_data,
            timeout=30,
        )
        print(f"   Response: {resp.status_code} {resp.text[:200]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ Webhook failed: {e}")
        return False


def check_lead_fields(lead_id: int, max_wait: int = 60):
    """Wait and check if lead fields were populated by Action 3."""
    print(f"⏳ Waiting up to {max_wait}s for fields to be populated...")
    
    # Key fields to check
    FIELD_CUSTOMER = 380299
    FIELD_NMC = 380315
    FIELD_DIRECTION = 380311
    
    for i in range(0, max_wait, 10):
        time.sleep(10)
        
        resp = requests.get(
            f"{BASE_URL}/leads/{lead_id}",
            headers=HEADERS,
            timeout=10,
        )
        
        if resp.status_code != 200:
            print(f"   [{i+10}s] Failed to get lead: {resp.status_code}")
            continue
        
        lead = resp.json()
        custom_fields = lead.get("custom_fields_values") or []
        
        # Check if any fields were filled
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
            return True
        else:
            print(f"   [{i+10}s] ... no fields yet")
    
    print(f"❌ Fields not populated after {max_wait}s")
    return False


def main():
    print("=" * 60)
    print("E2E TEST: Action 3 — Yandex Disk → File Recognition")
    print("=" * 60)
    print()
    
    # Step 1: Create lead
    lead_id = create_test_lead()
    if not lead_id:
        sys.exit(1)
    
    # Small delay to avoid rate limiting
    time.sleep(2)
    
    # Step 2: Add note with Yandex Disk path
    note_id = add_note_with_yadisk_path(lead_id)
    if not note_id:
        sys.exit(1)
    
    time.sleep(2)
    
    # Step 3: Simulate webhook (amoCRM should also send one, but we trigger manually)
    webhook_ok = simulate_webhook(lead_id, note_id)
    
    # Step 4: Check if fields were populated
    result = check_lead_fields(lead_id, max_wait=90)
    
    print()
    print("=" * 60)
    if result:
        print("🎉 E2E TEST PASSED: Action 3 works correctly!")
    else:
        print("⚠️  E2E TEST: Fields not auto-populated (may need manual check)")
        print(f"   Lead URL: https://{AMO_DOMAIN}/leads/detail/{lead_id}")
    print("=" * 60)
    
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
