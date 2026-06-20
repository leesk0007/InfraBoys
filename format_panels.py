import json

path = '/root/project2/grafana/provisioning/dashboards/infra_boys_last.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for panel in data.get('panels', []):
    title = panel.get('title', 'No Title')
    if title == 'Panel Title' and panel.get('type') == 'timeseries':
        title = 'Predictive ML Metrics'
    elif title == 'Panel Title' and panel.get('type') == 'marcusolsson-dynamictext-panel':
        title = 'Scheduled Scaling Controller'
    print(f"Panel: {title}")
    print(f"  Type: {panel.get('type')}")
    print(f"  GridPos: {panel.get('gridPos')}")
    print("---")
