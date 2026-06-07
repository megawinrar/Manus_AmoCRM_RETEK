import os
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

AMOCRM_DOMAIN = os.getenv("AMOCRM_DOMAIN")
ACCESS_TOKEN = os.getenv("AMOCRM_ACCESS_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# IDs for pipelines and statuses (to be filled from config)
ACTIVE_PIPELINE_ID = int(os.getenv("ACTIVE_PIPELINE_ID", 0))
STATUS_TO_ARCHIVE = int(os.getenv("STATUS_TO_ARCHIVE", 0))

ARCHIVE_DIR_PIPELINE_ID = int(os.getenv("ARCHIVE_DIR_PIPELINE_ID", 0))
ARCHIVE_SOZ_PIPELINE_ID = int(os.getenv("ARCHIVE_SOZ_PIPELINE_ID", 0))

def get_leads_to_archive():
    """Fetch leads from the active pipeline that are in 'К архивированию' status."""
    url = f"https://{AMOCRM_DOMAIN}/api/v4/leads"
    params = {
        "filter[pipeline_id]": ACTIVE_PIPELINE_ID,
        "filter[statuses][0][pipeline_id]": ACTIVE_PIPELINE_ID,
        "filter[statuses][0][status_id]": STATUS_TO_ARCHIVE,
        "with": "custom_fields_values"
    }
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        return response.json().get("_embedded", {}).get("leads", [])
    return []

def determine_archive_destination(lead):
    """
    Determine the target pipeline and status based on lead custom fields.
    Returns (pipeline_id, status_id)
    """
    # TODO: Implement logic based on "Архивное назначение итоговое" field
    # Example fallback:
    return ARCHIVE_DIR_PIPELINE_ID, 0 # Replace 0 with actual status ID

def move_lead_to_archive(lead_id, target_pipeline_id, target_status_id):
    """Move lead to the specified archive pipeline and status."""
    url = f"https://{AMOCRM_DOMAIN}/api/v4/leads"
    payload = [
        {
            "id": lead_id,
            "pipeline_id": target_pipeline_id,
            "status_id": target_status_id
        }
    ]
    response = requests.patch(url, headers=HEADERS, json=payload)
    return response.status_code == 200

def main():
    print("Starting archiver microservice...")
    while True:
        leads = get_leads_to_archive()
        for lead in leads:
            print(f"Processing lead {lead['id']}")
            target_pipeline, target_status = determine_archive_destination(lead)
            if target_pipeline and target_status:
                success = move_lead_to_archive(lead['id'], target_pipeline, target_status)
                if success:
                    print(f"Successfully archived lead {lead['id']}")
                else:
                    print(f"Failed to archive lead {lead['id']}")
        
        # Sleep for a while before checking again
        time.sleep(60)

if __name__ == "__main__":
    # main()
    pass
