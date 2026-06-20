import json

path = '/root/project2/grafana/provisioning/dashboards/infra_boys_last.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

templating = data.get('templating', {}).get('list', [])
for v in templating:
    if v.get('name') == 'server_ip':
        v['query'] = {"query": "label_values(node_uname_info{instance=\"$node\"}, instance)", "refId": "PrometheusVariableQueryEditor-VariableQuery"}
        v['definition'] = 'label_values(node_uname_info{instance="$node"}, instance)'

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("변수 수정 완료!")
