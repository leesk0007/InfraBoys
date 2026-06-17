import requests
 
# =============================================
# test_webhook.py
# AlertManager 역할 대신 가짜 알람 전송
# 실제 프로젝트에서는 AlertManager가 자동 전송
# =============================================
 
# =============================================
# 3가지 알람 동시에 전송
# critical → Gemini 분석 + Discord + DB 저장
# warning  → Discord + DB 저장
# info     → DB 저장만
# =============================================
fake_alert = {
    "alerts": [
        # CRITICAL 알람 - Gemini 분석 + Discord + DB
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "instance":  "ec2-1",
                "severity":  "critical"
            },
            "annotations": {
                "summary":     "CPU usage above 90%",
                "description": "EC2-1 CPU is 95% for 5 minutes - OOM 발생"
            }
        },
        # WARNING 알람 - Discord + DB (Gemini 생략)
        {
            "status": "firing",
            "labels": {
                "alertname": "HighMemory",
                "instance":  "ec2-2",
                "severity":  "warning"
            },
            "annotations": {
                "summary":     "Memory usage above 70%",
                "description": "EC2-2 Memory is 72%"
            }
        },
        # INFO 알람 - DB 저장만 (Gemini, Discord 생략)
        {
            "status": "firing",
            "labels": {
                "alertname": "SlowResponse",
                "instance":  "ec2-1",
                "severity":  "info"
            },
            "annotations": {
                "summary":     "Response time elevated",
                "description": "EC2-1 response time 900ms"
            }
        }
    ]
}
 
res = requests.post("http://localhost:8001/webhook/troubleshoot", json=fake_alert)
print("응답 코드:", res.status_code)
print("응답 내용:", res.json())