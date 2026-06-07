"""
Rebuild archive pipeline statuses according to PATCH5 spec.
Creates statuses in reverse order (last→first) so that the first status
ends up with the highest sort value and appears leftmost in kanban.

Usage:
    python3 src/rebuild_archive_statuses.py --dry-run   # Preview
    python3 src/rebuild_archive_statuses.py             # Apply
"""
import requests
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('AMO_ACCESS_TOKEN')
BASE = os.getenv('AMO_BASE_DOMAIN', 'tokutools.amocrm.ru')
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}
SYSTEM_IDS = {142, 143}
DELAY = 1.5

DRY_RUN = '--dry-run' in sys.argv

# Pipeline IDs
ARCHIVE_DIRECTIONS = 10984454  # Архив — Направления
ARCHIVE_SOZ = 10985038         # Архив — СОЗ

# Statuses per PATCH5 spec (in display order left→right)
# We will CREATE them in REVERSE order so last created = highest sort = leftmost
ARCHIVE_DIRECTIONS_STATUSES = [
    {'name': 'Специнструмент по чертежам', 'color': '#98cbff'},
    {'name': 'HSS ГОСТ', 'color': '#d6eaff'},
    {'name': 'Твердосплав', 'color': '#ffce5a'},
    {'name': 'Алмазный', 'color': '#f3beff'},
    {'name': 'Не наш ассортимент', 'color': '#ffa8a8'},
    {'name': 'Дубли / мусор', 'color': '#ffa8a8'},
    {'name': 'Требуется проверка', 'color': '#fffeb2'},
]

ARCHIVE_SOZ_STATUSES = [
    {'name': 'Ждём реальные торги', 'color': '#98cbff'},
    {'name': 'К обзвону', 'color': '#ffce5a'},
    {'name': 'Повторить через 30 дней', 'color': '#ccc8f9'},
    {'name': 'Повторить через 90 дней', 'color': '#f3beff'},
    {'name': 'Интересный завод', 'color': '#87f2c0'},
    {'name': 'Неактуально', 'color': '#ffa8a8'},
]


def api_get(url):
    time.sleep(DELAY)
    r = requests.get(url, headers=HEADERS, timeout=30)
    return r


def api_delete(url):
    time.sleep(DELAY)
    r = requests.delete(url, headers=HEADERS, timeout=30)
    return r


def api_post(url, data):
    time.sleep(DELAY)
    r = requests.post(url, headers=HEADERS, json=data, timeout=30)
    return r


def api_patch(url, data):
    time.sleep(DELAY)
    r = requests.patch(url, headers=HEADERS, json=data, timeout=30)
    return r


def rebuild_pipeline(pipeline_id, pipeline_name, target_statuses):
    print(f'\n{"="*60}')
    print(f'  {pipeline_name} (ID: {pipeline_id})')
    print(f'{"="*60}')

    # 1. Get current statuses
    r = api_get(f'https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses')
    if r.status_code != 200:
        print(f'  ERROR: Cannot get statuses: {r.status_code}')
        return False

    current = r.json().get('_embedded', {}).get('statuses', [])
    to_delete = [s for s in current if s['id'] not in SYSTEM_IDS
                 and s.get('type', 0) == 0]  # skip system unsorted

    print(f'\n  Current statuses to delete: {len(to_delete)}')
    for s in to_delete:
        print(f'    - {s["name"] or "(пусто)"} (id={s["id"]}, sort={s["sort"]})')

    print(f'\n  Target statuses (left→right): {len(target_statuses)}')
    for i, s in enumerate(target_statuses, 1):
        print(f'    {i}. {s["name"]} ({s["color"]})')

    if DRY_RUN:
        print('\n  [DRY-RUN] No changes applied.')
        return True

    # 2. Delete old statuses
    print('\n  Deleting old statuses...')
    for s in to_delete:
        r = api_delete(f'https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses/{s["id"]}')
        status = '✅' if r.status_code == 204 else f'❌ {r.status_code}'
        print(f'    {status} DEL {s["name"] or "(пусто)"} (id={s["id"]})')

    # 3. Create in REVERSE order (last displayed → first displayed)
    print('\n  Creating statuses (reverse order for correct sort)...')
    reversed_statuses = list(reversed(target_statuses))
    created = []

    for s in reversed_statuses:
        r = api_post(
            f'https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses',
            [{'name': s['name']}]
        )
        if r.status_code == 200:
            new_id = r.json()['_embedded']['statuses'][0]['id']
            new_sort = r.json()['_embedded']['statuses'][0]['sort']
            created.append({'id': new_id, **s})
            print(f'    ✅ {s["name"]} → id={new_id} sort={new_sort}')
        else:
            print(f'    ❌ {s["name"]}: {r.status_code} {r.text[:80]}')

    # 4. Patch colors
    print('\n  Patching colors...')
    for c in created:
        r = api_patch(
            f'https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses/{c["id"]}',
            {'name': c['name'], 'color': c['color']}
        )
        status = '✅' if r.status_code == 200 else f'❌ {r.status_code}'
        print(f'    {status} {c["name"]} → {c["color"]}')

    # 5. Verify
    print('\n  Final verification:')
    r = api_get(f'https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses')
    final = r.json().get('_embedded', {}).get('statuses', [])
    custom = [s for s in final if s['id'] not in SYSTEM_IDS and s.get('type', 0) == 0]
    for s in sorted(custom, key=lambda x: -x['sort']):
        print(f'    sort={s["sort"]:>5} | {s["name"]} | {s["color"]}')

    return True


if __name__ == '__main__':
    if DRY_RUN:
        print('🔍 DRY-RUN MODE — no changes will be made\n')
    else:
        print('🚀 APPLYING CHANGES to amoCRM\n')

    rebuild_pipeline(ARCHIVE_DIRECTIONS, 'Архив — Направления', ARCHIVE_DIRECTIONS_STATUSES)
    rebuild_pipeline(ARCHIVE_SOZ, 'Архив — СОЗ', ARCHIVE_SOZ_STATUSES)

    print('\n✅ Done!')
