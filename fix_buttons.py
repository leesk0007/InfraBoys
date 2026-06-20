import json
import re

path = '/root/project2/grafana/provisioning/dashboards/infra_boys_last.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for panel in data.get('panels', []):
    if panel.get('title') == '⚡ Manual Auto Scale':
        options = panel.get('options', {})
        
        # 1. Fix afterRender duplicate event listeners
        after_render = options.get('afterRender', '')
        if 'dataset.initialized' not in after_render:
            after_render = after_render.replace(
                "const input = root.querySelector('#ec2-count');",
                "if (root.dataset.initialized === 'true') return;\nroot.dataset.initialized = 'true';\n\nconst input = root.querySelector('#ec2-count');"
            )
            options['afterRender'] = after_render
            
        # 2. Fix CSS in defaultContent to make buttons smaller
        content = options.get('defaultContent', '')
        # Decrease padding and font-size
        content = re.sub(r'padding:\s*16px\s*24px;', 'padding: 10px 16px;', content)
        content = re.sub(r'font-size:\s*16px;', 'font-size: 14px;', content)
        content = re.sub(r'padding:\s*12px\s*20px;', 'padding: 8px 12px;', content)
        content = re.sub(r'font-size:\s*15px;', 'font-size: 13px;', content)
        content = re.sub(r'width:\s*48px;', 'width: 36px;', content)
        content = re.sub(r'height:\s*48px;', 'height: 36px;', content)
        
        options['defaultContent'] = content

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("버튼 및 이벤트 리스너 수정 완료!")
