import json

path = '/root/project2/grafana/provisioning/dashboards/infra_boys_last.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

def fix_script(s):
    if not isinstance(s, str): return s
    s = s.replace("fetch(`localhost:8001", "fetch(`http://${window.location.hostname}:8001")
    s = s.replace("fetch('localhost:8001/api/rollback'", "fetch(`http://${window.location.hostname}:8001/api/rollback`")
    s = s.replace("const API_BASE = 'localhost:8001/api';", "const API_BASE = `http://${window.location.hostname}:8001/api`;")
    return s

for panel in data.get('panels', []):
    if 'options' in panel and 'afterRender' in panel['options']:
        panel['options']['afterRender'] = fix_script(panel['options']['afterRender'])

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("JSON 수정 완료!")
