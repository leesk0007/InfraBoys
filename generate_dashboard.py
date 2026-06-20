import json

path = '/root/project2/grafana/provisioning/dashboards/infra_boys_last.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1. Add server_ip variable to cleanly match IP across exporters
templating = data.get('templating', {}).get('list', [])
if not any(v.get('name') == 'server_ip' for v in templating):
    templating.append({
        "allValue": None,
        "current": {},
        "datasource": {"type": "prometheus", "uid": "${ds_prometheus}"},
        "definition": "$node",
        "hide": 2,
        "includeAll": False,
        "label": "Server IP",
        "multi": False,
        "name": "server_ip",
        "options": [],
        "query": "$node",
        "refresh": 1,
        "regex": "(.*):\\d+",
        "skipUrlSync": False,
        "sort": 0,
        "type": "query"
    })

# 2. Filter rows
keep_rows = ['Control Tower', 'Quick CPU / Mem / Disk', 'Basic CPU / Mem / Net / Disk', 'Network Traffic']
delete_mode = False
new_panels = []

for p in data.get('panels', []):
    if p.get('type') == 'row':
        title = p.get('title', '')
        if title in keep_rows:
            delete_mode = False
            new_panels.append(p)
        else:
            delete_mode = True
    else:
        # Custom panels are kept
        title = p.get('title', '')
        if title in ['🧠 Predictive ML Analysis (CPU & Memory)', '⚡ Manual Auto Scale', '⏰ Scheduled Scaling Controller']:
            new_panels.append(p)
        elif not delete_mode:
            new_panels.append(p)

# 3. Add Web App Health Row
y_pos = 100 # Put it at the bottom, Grafana will sort it out

new_panels.append({
  "collapsed": False,
  "gridPos": { "h": 1, "w": 24, "x": 0, "y": y_pos },
  "id": 9000,
  "panels": [],
  "title": "🌐 Web Application Health (NGINX & WAS)",
  "type": "row"
})

new_panels.append({
  "datasource": {"type": "prometheus", "uid": "${ds_prometheus}"},
  "gridPos": {"h": 8, "w": 6, "x": 0, "y": y_pos+1},
  "id": 9001,
  "title": "NGINX Active Connections",
  "type": "timeseries",
  "targets": [{"expr": "nginx_connections_active{instance=~\"$server_ip:.*\"}", "legendFormat": "Active Connections", "refId": "A"}],
  "fieldConfig": {
    "defaults": { "custom": { "fillOpacity": 10, "lineWidth": 2 }, "unit": "short", "color": {"mode": "palette-classic"} }
  }
})

new_panels.append({
  "datasource": {"type": "prometheus", "uid": "${ds_prometheus}"},
  "gridPos": {"h": 8, "w": 6, "x": 6, "y": y_pos+1},
  "id": 9002,
  "title": "NGINX Request Rate (RPS)",
  "type": "timeseries",
  "targets": [{"expr": "rate(nginx_http_requests_total{instance=~\"$server_ip:.*\"}[1m])", "legendFormat": "Requests / Sec", "refId": "A"}],
  "fieldConfig": {
    "defaults": { "custom": { "fillOpacity": 10, "lineWidth": 2 }, "unit": "reqps", "color": {"mode": "palette-classic"} }
  }
})

new_panels.append({
  "datasource": {"type": "prometheus", "uid": "${ds_prometheus}"},
  "gridPos": {"h": 8, "w": 6, "x": 12, "y": y_pos+1},
  "id": 9003,
  "title": "WAS Process CPU",
  "type": "timeseries",
  "targets": [{"expr": "rate(namedprocess_namegroup_cpu_seconds_total{instance=~\"$server_ip:.*\"}[1m])", "legendFormat": "{{groupname}}", "refId": "A"}],
  "fieldConfig": {
    "defaults": { "custom": { "fillOpacity": 10, "lineWidth": 2 }, "unit": "percentunit", "color": {"mode": "palette-classic"} }
  }
})

new_panels.append({
  "datasource": {"type": "prometheus", "uid": "${ds_prometheus}"},
  "gridPos": {"h": 8, "w": 6, "x": 18, "y": y_pos+1},
  "id": 9004,
  "title": "WAS Process Memory",
  "type": "timeseries",
  "targets": [{"expr": "namedprocess_namegroup_memory_bytes{instance=~\"$server_ip:.*\"}", "legendFormat": "{{groupname}} - {{memtype}}", "refId": "A"}],
  "fieldConfig": {
    "defaults": { "custom": { "fillOpacity": 10, "lineWidth": 2 }, "unit": "bytes", "color": {"mode": "palette-classic"} }
  }
})

data['panels'] = new_panels

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Dashboard generated successfully!")
