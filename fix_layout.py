import json

path = '/root/project2/grafana/provisioning/dashboards/infra_boys_last.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for panel in data.get('panels', []):
    # 1. 시계열 예측 그래프
    if panel.get('type') == 'timeseries' and panel.get('title') == 'Panel Title':
        panel['title'] = '🧠 Predictive ML Analysis (CPU & Memory)'
        panel['gridPos'] = {'h': 12, 'w': 18, 'x': 0, 'y': 0}
    
    # 2. 수동 스케일링 패널
    elif panel.get('title') == 'Auto Scale':
        panel['title'] = '⚡ Manual Auto Scale'
        panel['gridPos'] = {'h': 12, 'w': 6, 'x': 18, 'y': 0}
    
    # 3. 스케줄링 예약 패널
    elif panel.get('type') == 'marcusolsson-dynamictext-panel' and panel.get('title') == 'Panel Title':
        panel['title'] = '⏰ Scheduled Scaling Controller'
        panel['gridPos'] = {'h': 14, 'w': 24, 'x': 0, 'y': 12}

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("레이아웃 수정 완료!")
