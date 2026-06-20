import re
import json
import asyncio
from datetime import datetime
from google import genai
from fastapi.concurrency import run_in_threadpool
import config

GEMINI_MODEL = "gemini-2.5-flash"
client = genai.Client(api_key=config.GEMINI_API_KEY)

def mask_pii(text: str) -> str:
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[MASKED_IP]', text)
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[MASKED_EMAIL]', text)
    text = re.sub(r'(?i)(password|passwd|pwd)\s*=\s*\S+', r'\1=[MASKED]', text)
    text = re.sub(r'(?i)(api_key|apikey|gemini_api_key|aws_access_key|secret_key)\s*=\s*\S+', r'\1=[MASKED]', text)
    text = re.sub(r'(postgresql|mysql|mongodb)://[^\s]+', r'\1://[MASKED]', text)
    text = re.sub(r'AKIA[0-9A-Z]{16}', '[MASKED_AWS_KEY]', text)
    text = re.sub(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', '[MASKED_JWT]', text)
    return text

async def analyze_with_gemini(masked_log: str, alerts_summary: str) -> dict:
    now = datetime.now()

    if config.circuit_state == config.CIRCUIT_OPEN:
        if now < config.circuit_open_until:
            remaining = int((config.circuit_open_until - now).total_seconds() / 60)
            print(f"   Circuit Breaker OPEN - {remaining}분 후 재시도 가능")
            return {
                "cause": f"AI 분석 일시 중단 (API 한도 초과 - {remaining}분 후 재시도)",
                "severity": "알 수 없음",
                "recommendation": "알 수 없음",
                "runbook": "알 수 없음",
                "actions": ["수동으로 로그 확인 필요", "잠시 후 자동 재시도 예정"],
                "recommendation_reason": "Circuit Breaker 작동 중"
            }
        else:
            config.circuit_state = config.CIRCUIT_HALF_OPEN
            print("   Circuit Breaker HALF-OPEN - 테스트 호출 시도")

    runbook_list = """
- was_restart_nginx.yml         : Nginx 프로세스 비정상 종료 시 재시작
- was_cleanup_disk.yml          : 디스크 용량 95% 초과 시 임시 파일 정리
- was_kill_process.yml          : 좀비 프로세스 또는 CPU 100% 점유 프로세스 종료
- db_kill_idle_connections.yml  : PostgreSQL 커넥션 풀 고갈 시 idle 커넥션 정리
- db_restart_container.yml      : PostgreSQL 프로세스 다운 시 DB 컨테이너 재시작
"""

    prompt = f"""
당신은 클라우드 인프라 장애 분석 전문가입니다.

[발생한 알람 목록]
{alerts_summary}

[서버 에러 로그]
{masked_log}

[사용 가능한 런북 목록]
{runbook_list}

위 내용을 종합 분석하고 런북 목록 중 하나를 선택해서
반드시 아래 JSON 형식으로만 답변하세요.
다른 말은 절대 하지 마세요. JSON만 출력하세요.

{{
  "cause": "장애 원인 한 줄 요약",
  "severity": "낮음 또는 중간 또는 높음",
  "recommendation": "A 또는 B 또는 C",
  "recommendation_reason": "추천 이유 한 줄",
  "actions": ["즉시 조치 1", "즉시 조치 2", "즉시 조치 3"],
  "runbook": "런북 목록에서 선택한 파일명"
}}

스케일링 옵션:
A = 현상유지
B = 보수적 (인스턴스 1대 추가)
C = 공격적 (최대치 즉시 확장)
"""

    max_retry    = 5
    wait_seconds = 15
    for attempt in range(max_retry):
        try:
            print(f"   Gemini 요청 중... (시도 {attempt + 1}/{max_retry})")

            response = await run_in_threadpool(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt
            )

            config.circuit_error_count = 0
            config.circuit_state       = config.CIRCUIT_CLOSED

            raw = response.text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()

            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {
                    "cause": raw,
                    "severity": "알 수 없음",
                    "recommendation": "알 수 없음",
                    "runbook": "알 수 없음",
                    "actions": [],
                    "recommendation_reason": ""
                }

        except Exception as e:
            print(f"   Gemini 오류: {e}")
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                config.circuit_error_count += 1
                print(f"   Circuit Breaker 에러 카운트: {config.circuit_error_count}/{config.CIRCUIT_ERROR_THRESHOLD}")

                if config.circuit_error_count >= config.CIRCUIT_ERROR_THRESHOLD:
                    config.circuit_state      = config.CIRCUIT_OPEN
                    config.circuit_open_until = datetime.now() + config.CIRCUIT_OPEN_DURATION
                    print("   Circuit Breaker OPEN - 1시간 차단 시작")
                    return {
                        "cause": "API 한도 초과로 AI 분석 중단",
                        "severity": "알 수 없음",
                        "recommendation": "알 수 없음",
                        "runbook": "알 수 없음",
                        "actions": ["수동으로 로그 확인 필요"],
                        "recommendation_reason": "Circuit Breaker 작동"
                    }

                return {
                    "cause": "API 한도 초과",
                    "severity": "알 수 없음",
                    "recommendation": "알 수 없음",
                    "runbook": "알 수 없음",
                    "actions": ["잠시 후 재시도 예정"],
                    "recommendation_reason": f"429 에러 ({config.circuit_error_count}/{config.CIRCUIT_ERROR_THRESHOLD})"
                }

            if attempt < max_retry - 1:
                print(f"   {wait_seconds}초 후 재시도...")
                await asyncio.sleep(wait_seconds)
                wait_seconds *= 2
            else:
                print("    최대 재시도 횟수 초과")
                return {
                    "cause": "Gemini 분석 실패 (서버 오류)",
                    "severity": "알 수 없음",
                    "recommendation": "알 수 없음",
                    "runbook": "알 수 없음",
                    "actions": ["수동으로 로그 확인 필요"],
                    "recommendation_reason": "AI 분석 불가"
                }
