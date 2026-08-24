import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

with open('static/js/app.js', 'r', encoding='utf-8') as f:
    js = f.read()

print("[*] Validating DOM IDs...")
get_ids = re.findall(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)", js)
missing_in_html = [elem_id for elem_id in get_ids if f'id="{elem_id}"' not in html and f"id='{elem_id}'" not in html]

print(f"Total document.getElementById IDs in JS: {len(get_ids)}")
if missing_in_html:
    print(f"FAILED: Missing IDs in HTML: {missing_in_html}")
else:
    print(f"PASSED: All {len(get_ids)} DOM IDs exist in static/index.html!")

print("\n[*] Validating Query Selectors...")
classes = re.findall(r"document\.querySelectorAll\(['\"]\.(preset-chip|format-pill|filter-pill|tab-btn)['\"]\)", js)
for cls in sorted(set(classes)):
    count = len(re.findall(rf'class=["\'][^"\']*{cls}[^"\']*["\']', html))
    print(f" - .{cls}: {count} elements found in HTML")

print("\n[*] Checking Presets coverage...")
presets = re.findall(r'data-preset=["\']([^"\']+)["\']', html)
print(f"Found presets in HTML: {presets}")

print("\n[*] Checking Formats coverage...")
formats = re.findall(r'data-format=["\']([^"\']+)["\']', html)
print(f"Found formats in HTML: {formats}")
