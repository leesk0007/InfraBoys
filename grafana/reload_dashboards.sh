#!/bin/bash
# ==============================================================================
# [트러블슈팅 해결] Grafana Dashboard Provisioning 무중단 리로드 스크립트
# 도커 볼륨은 실시간 동기화되나, Grafana 애플리케이션의 메모리 캐시로 인해 
# 대시보드가 옛날 버전으로 보이는 현상 해결 (Downtime 0초 보장)
# ==============================================================================

GRAFANA_URL="http://admin:admin@localhost:3000"
API_ENDPOINT="/api/admin/provisioning/dashboards/reload"

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${GRAFANA_URL}${API_ENDPOINT}")

if [ "$HTTP_STATUS" -eq 200 ]; then
    echo "성공: 대시보드 무중단 동기화 완료! (Grafana 컨테이너 재시작 불필요)"
else
    echo "실패: Grafana API 호출 에러 (HTTP $HTTP_STATUS)"
    exit 1
fi
