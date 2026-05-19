"""Wave 10q audit: cross-check K6-derived remaining list (63) against on-disk .aepkg presence."""
import json, os

with open('projects/v11-aep/publish-ready/aep/V15_WAVE10Q_MANIFEST.json', encoding='utf-8') as f:
    m = json.load(f)
remaining = m['remaining_for_this_wave']
print('=== 63 REMAINING — DISK CROSS-CHECK ===')
on_disk_aepkg = 0
on_disk_no_aepkg = 0
disk_yes = []
disk_no = []
for r in remaining:
    aepkg = r.replace('.html', '.aepkg')
    # Strip absolute prefix and use OS-native path
    rel = aepkg.replace('c:/users/example-user/downloads_clean/aepkit/', '').replace('/', os.sep)
    if os.path.exists(rel):
        on_disk_aepkg += 1
        disk_yes.append(rel)
    else:
        on_disk_no_aepkg += 1
        disk_no.append(rel)
print('aepkg already on disk (no K6 row but file exists):', on_disk_aepkg)
print('aepkg NOT on disk (TRUE gap for conversion):', on_disk_no_aepkg)
print()
print('--- first 5 on-disk-but-no-K6 ---')
for p in disk_yes[:5]:
    print(' ', p)
print('--- first 5 NOT-on-disk ---')
for p in disk_no[:5]:
    print(' ', p)
