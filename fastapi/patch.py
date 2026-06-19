import re

with open("/root/project2/fastapi/src/main.py", "r") as f:
    content = f.read()

# Replace get_local_logs() with getting target_ip and using get_logs_on_demand
old_code = """    print("① 로그 수집 중...")
    raw_logs = data_handler.get_local_logs()

    print("② 마스킹 중...")"""

new_code = """    print("① 로그 수집 중...")
    
    # Extract target_ip from instance label
    target_ip = instances.split(",")[0].split(":")[0].strip() if instances else None
    
    if target_ip and target_ip != "unknown":
        raw_logs = await data_handler.get_logs_on_demand(target_ip)
    else:
        raw_logs = "IP 정보를 찾을 수 없습니다."

    print("② 마스킹 중...")"""

content = content.replace(old_code, new_code)

with open("/root/project2/fastapi/src/main.py", "w") as f:
    f.write(content)

print("Patched main.py")
