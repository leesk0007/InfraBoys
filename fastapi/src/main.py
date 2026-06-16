import os
import re
import json
import time
import httpx
import ntplib
import pytz
import boto3
import asyncio
from datetime import datetime, timedelta
from collections import deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from psycopg2 import pool as pg_pool
import sys, requests

KST = pytz.timezone('Asia/Seoul')

# =========================================
# 깃허브 환경변수
# =========================================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

# =========================================
# AIOps 환경변수
# =========================================
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
LOG_FILE            = os.getenv("LOG_FILE", "/app/nginx.log")

if not GEMINI_API_KEY:
    print(" 오류: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

if not DISCORD_WEBHOOK_URL:
    print(" 오류: DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

GEMINI_MODEL = "gemini-2.5-flash"
client = genai.Client(api_key=GEMINI_API_KEY)

DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

db_connection_pool = None

# =============================================
# Circuit Breaker 설정 
# =============================================
CIRCUIT_CLOSED    = "CLOSED"
CIRCUIT_OPEN      = "OPEN"
CIRCUIT_HALF_OPEN = "HALF_OPEN"

circuit_state       = CIRCUIT_CLOSED
circuit_error_count = 0
circuit_open_until  = None

CIRCUIT_ERROR_THRESHOLD = 3
CIRCUIT_OPEN_DURATION   = timedelta(hours=1)

# =============================================
# DB 초기화 함수 
# =============================================
def init_db():
    global db_connection_pool
    conn = None
    try:
        db_connection_pool = pg_pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            **DB_CONFIG
        )
        print(" DB 연결 풀 생성 완료 (최소 1개, 최대 5개)")

        conn = db_connection_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS aiops_logs (
                    id             SERIAL PRIMARY KEY,
                    alert_name     TEXT,
                    instance       TEXT,
                    cause          TEXT,
                    severity       TEXT,
                    recommendation TEXT,
                    runbook        TEXT,
                    created_at     TIMESTAMP DEFAULT NOW()
                )
            """)
        conn.commit()
        print(" DB 테이블 확인 완료")
        return True

    except Exception as e:
        print(f" DB 초기화 실패 (DB 연결 안 됨): {e}")
        print(" DB 없이 서버 계속 실행합니다.")
        db_connection_pool = None
        return False
    finally:
        if conn and db_connection_pool:
            db_connection_pool.putconn(conn)

async def retry_db_connection():
    while db_connection_pool is None:
        print(" DB 재연결 시도 중... (30초 대기)")
        await asyncio.sleep(30)
        success = await run_in_threadpool(init_db)
        if success:
            print(" DB 재연결 성공!")
            break

# =============================================
# 로그 수집 / 마스킹 
# =============================================
def get_logs():
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            last_100 = deque(f, maxlen=100)
            return "".join(last_100)
    except FileNotFoundError:
        return "로그 파일 없음"

def mask_pii(text: str) -> str:
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[MASKED_IP]', text)
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[MASKED_EMAIL]', text)
    text = re.sub(r'(?i)(password|passwd|pwd)\s*=\s*\S+', r'\1=[MASKED]', text)
    text = re.sub(r'(?i)(api_key|apikey|gemini_api_key|aws_access_key|secret_key)\s*=\s*\S+', r'\1=[MASKED]', text)
    text = re.sub(r'(postgresql|mysql|mongodb)://[^\s]+', r'\1://[MASKED]', text)
    text = re.sub(r'AKIA[0-9A-Z]{16}', '[MASKED_AWS_KEY]', text)
    text = re.sub(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', '[MASKED_JWT]', text)
    return text

# =============================================
# Gemini 분석 함수 
# =============================================
async def analyze_with_gemini(masked_log: str, alerts_summary: str) -> dict:
    global circuit_state, circuit_error_count, circuit_open_until

    now = datetime.now()

    if circuit_state == CIRCUIT_OPEN:
        if now < circuit_open_until:
            remaining = int((circuit_open_until - now).total_seconds() / 60)
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
            circuit_state = CIRCUIT_HALF_OPEN
            print("   Circuit Breaker HALF-OPEN - 테스트 호출 시도")

    runbook_list = """
- runbook-scale-out.yml   : CPU/메모리 과부하, 트래픽 폭증 시 EC2 추가
- runbook-db-restart.yml  : DB 연결 실패, DB 오류 발생 시 DB 재시작
- runbook-rollback.yml    : 배포 후 에러 급증 시 이전 버전으로 롤백
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

            circuit_error_count = 0
            circuit_state       = CIRCUIT_CLOSED

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
                circuit_error_count += 1
                print(f"   Circuit Breaker 에러 카운트: {circuit_error_count}/{CIRCUIT_ERROR_THRESHOLD}")

                if circuit_error_count >= CIRCUIT_ERROR_THRESHOLD:
                    circuit_state      = CIRCUIT_OPEN
                    circuit_open_until = datetime.now() + CIRCUIT_OPEN_DURATION
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
                    "recommendation_reason": f"429 에러 ({circuit_error_count}/{CIRCUIT_ERROR_THRESHOLD})"
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

# =============================================
# Discord 전송
# =============================================
def send_discord(result: dict, alert_names: str, instances: str):
    color_map = {"높음": 0xFF0000, "중간": 0xFF8C00, "낮음": 0x00FF00}
    color = color_map.get(result.get("severity", ""), 0x5865F2)
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    actions_text = "\n".join(
        [f"{i+1}. {a}" for i, a in enumerate(result.get("actions", []))]
    )

    payload = {
        "username": "AIOps 분석 봇",
        "embeds": [{
            "title": f"장애 감지 - {alert_names}",
            "color": color,
            "fields": [
                {"name": "서버",      "value": instances,                               "inline": True},
                {"name": "감지 시각", "value": now,                                     "inline": True},
                {"name": "장애 원인", "value": result.get("cause", "알 수 없음"),       "inline": False},
                {"name": "심각도",    "value": result.get("severity", ""),              "inline": True},
                {"name": "추천 대응", "value": result.get("recommendation", ""),        "inline": True},
                {"name": "추천 이유", "value": result.get("recommendation_reason", ""), "inline": False},
                {"name": "즉시 조치", "value": actions_text,                            "inline": False},
                {"name": "추천 런북", "value": result.get("runbook", ""),               "inline": False},
            ],
            "footer": {"text": "Privacy AIOps - 로그는 마스킹 처리 후 AI 분석됨"}
        }]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if res.status_code == 204:
            print(" Discord 전송 성공")
        else:
            print(f" Discord 전송 실패: {res.status_code}")
    except requests.RequestException as e:
        print(f" Discord 전송 실패 (무시하고 계속): {e}")

# =============================================
# DB 저장 
# =============================================
def save_to_db(result: dict, alert_name: str, instance: str):
    if db_connection_pool is None:
        print(" DB 연결 풀 없음 - 저장 건너뜀")
        return

    conn = None
    try:
        conn = db_connection_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO aiops_logs (
                    alert_name, instance, cause,
                    severity, recommendation, runbook, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (
                alert_name,
                instance,
                result.get("cause", ""),
                result.get("severity", ""),
                result.get("recommendation", ""),
                result.get("runbook", "")
            ))
        conn.commit()
        print(" DB 저장 완료")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f" DB 저장 실패: {e}")
    finally:
        if conn:
            db_connection_pool.putconn(conn)

# ====================================================================
#  NTP / 스케줄러
# ====================================================================
def calculate_ntp_offset():
    servers = ['time.kriss.re.kr', 'kr.pool.ntp.org', 'time.google.com']
    for server in servers:
        try:
            ntp_client = ntplib.NTPClient()
            response = ntp_client.request(server, version=3, timeout=5)
            print(f" NTP 동기화 성공: {server}, 오프셋: {response.offset:.2f}초")
            return response.offset
        except Exception as e:
            print(f" {server} 실패: {e}")
    print(" 모든 NTP 서버 실패")
    return 0.0

NTP_OFFSET = calculate_ntp_offset()
_original_time = time.time
time.time = lambda: _original_time() + NTP_OFFSET

def now_kst():
    return datetime.fromtimestamp(time.time(), tz=KST)

scheduler = AsyncIOScheduler(timezone=KST)

AWS_REGION = "ap-northeast-2"
EC2_MIN_COUNT = 1
EC2_MAX_COUNT = 8
ec2_client = boto3.client('ec2', region_name=AWS_REGION)

def get_current_ec2_count() -> int:
    try:
        response = ec2_client.describe_instances(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'pending']}]
        )
        count = 0
        for reservation in response['Reservations']:
            count += len(reservation['Instances'])
        print(f" 현재 EC2 대수: {count}대")
        return count
    except Exception as e:
        print(f" EC2 조회 실패: {e}")
        raise HTTPException(500, f"EC2 상태 조회 실패: {e}")

# =============================================
# lifespan — 스케줄러 + DB 초기화 같이 실행
# =============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    print(f" Scheduler started")
    print(f"   정확한 한국 시간: {now_kst()}")
    print(f"   EC2 한계: 최소 {EC2_MIN_COUNT}대 / 최대 {EC2_MAX_COUNT}대")
    print(f"   AWS region: {AWS_REGION}")

    success = await run_in_threadpool(init_db)
    if not success:
        print(" DB 없이 시작 → 백그라운드에서 계속 재시도")
        asyncio.create_task(retry_db_connection())

    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScaleRequest(BaseModel):
    action: str
    delta: int = 1
    user: str = "user"

class RollbackRequest(BaseModel):
    action: str = "rollback"
    user: str = "user"

class ReserveScaleRequest(BaseModel):
    schedule_id: str
    reserve_at: str
    capacity: int
    duration: int
    user: str = "user"

@app.get("/")
async def root():
    return {
        "status": "running",
        "real_korea_time": str(now_kst()),
        "ntp_offset": f"{NTP_OFFSET:.2f}초",
        "scheduler_running": scheduler.running,
        "ec2_min": EC2_MIN_COUNT,
        "ec2_max": EC2_MAX_COUNT,
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/ec2_count")
async def ec2_count():
    current = get_current_ec2_count()
    return {
        "current": current,
        "min": EC2_MIN_COUNT,
        "max": EC2_MAX_COUNT,
        "available_scale_out": max(0, EC2_MAX_COUNT - current),
        "available_scale_in": max(0, current - EC2_MIN_COUNT),
    }

@app.get("/api/jobs")
async def list_jobs():
    jobs = scheduler.get_jobs()
    return {
        "now": str(now_kst()),
        "count": len(jobs),
        "jobs": [
            {"id": j.id, "next_run_time": str(j.next_run_time), "args": str(j.args)}
            for j in jobs
        ]
    }

@app.post("/api/scale-out")
async def scale_out(req: ScaleRequest):
    if req.delta < 1:
        raise HTTPException(400, "scale-out 하는 ec2는 1대 이상이어야 합니다.")
    current = get_current_ec2_count()
    after = current + req.delta
    if after > EC2_MAX_COUNT:
        available = max(0, EC2_MAX_COUNT - current)
        raise HTTPException(
            400,
            f" Scale-Out 불가: 현재 {current}대 + 요청 {req.delta}대 = {after}대 → "
            f"최대 {EC2_MAX_COUNT}대 초과 (가능: +{available}대까지)"
        )
    await trigger_github_action("scale-out", {"require_ec2": req.delta, "sender": "grafana"})
    return {"status": "success", "message": f"Scale-Out +{req.delta} triggered", "current": current, "after_expected": after}

@app.post("/api/scale-in")
async def scale_in(req: ScaleRequest):
    if req.delta < 1:
        raise HTTPException(400, "scale-in 하는 ec2는 1대 이상이어야 합니다.")
    current = get_current_ec2_count()
    after = current - req.delta
    if after < EC2_MIN_COUNT:
        available = max(0, current - EC2_MIN_COUNT)
        raise HTTPException(
            400,
            f" Scale-In 불가: 현재 {current}대 - 요청 {req.delta}대 = {after}대 → "
            f"최소 {EC2_MIN_COUNT}대 미만 (가능: -{available}대까지)"
        )
    await trigger_github_action("scale-in", {"require_ec2": req.delta, "sender": "grafana"})
    return {"status": "success", "message": f"Scale-In -{req.delta} triggered", "current": current, "after_expected": after}

@app.post("/api/reserve_scale")
async def reserve_scale(req: ReserveScaleRequest):
    try:
        run_time = datetime.fromisoformat(req.reserve_at)
        if run_time.tzinfo is None:
            run_time = KST.localize(run_time)
    except ValueError:
        raise HTTPException(400, f"잘못된 시간 형식: {req.reserve_at}")
    if run_time <= now_kst():
        raise HTTPException(400, f"예약 시간은 현재({now_kst()}) 이후여야 합니다.")
    if req.capacity < EC2_MIN_COUNT or req.capacity > EC2_MAX_COUNT:
        raise HTTPException(400, f" Target Capacity는 {EC2_MIN_COUNT} ~ {EC2_MAX_COUNT} 범위여야 합니다. (요청: {req.capacity})")
    job = scheduler.add_job(
        trigger_github_action,
        'date',
        run_date=run_time,
        args=["scheduled-scale", {"capacity": req.capacity, "duration": req.duration, "user": "grafana"}],
        id=req.schedule_id,
        replace_existing=True,
        misfire_grace_time=60
    )
    return {"status": "success", "schedule_id": req.schedule_id, "scheduled_at": str(job.next_run_time)}

@app.delete("/api/reserve_scale/{schedule_id}")
async def cancel_reserve_scale(schedule_id: str):
    job = scheduler.get_job(schedule_id)
    if job is None:
        return {"status": "not_found", "message": "존재하지 않거나 이미 실행됨"}
    scheduler.remove_job(schedule_id)
    return {"status": "success", "message": "예약 취소 완료"}

@app.post("/api/rollback")
async def rollback(req: RollbackRequest):
    await trigger_github_action("rollback", {"user": req.user})
    return {"status": "success", "message": "Rollback triggered"}

@app.get("/api/reserve_scale")
async def list_reserve_scale():
    jobs = scheduler.get_jobs()
    schedules = []
    for job in jobs:
        if len(job.args) >= 2 and isinstance(job.args[1], dict):
            payload = job.args[1]
            schedules.append({
                "schedule_id": job.id,
                "reserve_at": job.next_run_time.isoformat() if job.next_run_time else None,
                "capacity": payload.get("capacity"),
                "duration": payload.get("duration"),
                "user": payload.get("user")
            })
    return {"count": len(schedules), "schedules": schedules}

@app.post("/webhook/scale-out")
async def webhook_scale_out(request: Request):
    data = await request.json()
    alerts = data.get("alerts", [])
    firing = [a for a in alerts if a.get("status") == "firing"]
    if not firing:
        return {"status": "skipped"}
    max_level = max(int(a["labels"].get("level", 0)) for a in firing)
    replicas = 1 if max_level == 1 else 2
    await trigger_github_action("scale-out", {"require_ec2": replicas, "sender": "alertmanager"})
    return {"status": "triggered", "replicas": replicas}

@app.post("/webhook/scale-in")
async def webhook_scale_in(request: Request):
    data = await request.json()
    alerts = data.get("alerts", [])
    firing = [a for a in alerts if a.get("status") == "firing"]
    if not firing:
        return {"status": "skipped"}
    await trigger_github_action("scale-in", {"require_ec2": 1, "sender": "alertmanager"})
    return {"status": "triggered", "replicas": 1}

# =============================================
# AIOps 부분 — troubleshoot 엔드포인트
# =============================================
@app.post("/webhook/troubleshoot")
async def troubleshoot(request: Request):
    data = await request.json()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "="*50)
    print(f"[{now}] AIOps 알림 수신!")
    print("="*50)

    alerts = data.get("alerts", [])

    if not alerts:
        return {"status": "no alerts", "count": 0}

    alert_names = ", ".join([a.get("labels", {}).get("alertname", "unknown") for a in alerts])
    instances   = ", ".join([a.get("labels", {}).get("instance",   "unknown") for a in alerts])
    alerts_summary = "\n".join([
        f"- {a.get('labels', {}).get('alertname')} | {a.get('labels', {}).get('instance')} | {a.get('annotations', {}).get('summary', '')}"
        for a in alerts
    ])

    severities = [a.get("labels", {}).get("severity", "unknown").lower() for a in alerts]

    if "critical" in severities:
        priority = "critical"
    elif "warning" in severities:
        priority = "warning"
    else:
        priority = "low"

    print(f"장애 수  : {len(alerts)}건")
    print(f"장애명   : {alert_names}")
    print(f"서버     : {instances}")
    print(f"우선순위 : {priority}")
    print("-"*50)

    print("① 로그 수집 중...")
    raw_logs = get_logs()

    print("② 마스킹 중...")
    masked_logs = mask_pii(raw_logs)

    if priority == "critical":
        print("③ Gemini 분석 중... (CRITICAL 알람)")
        result = await analyze_with_gemini(masked_logs, alerts_summary)
        print(f"   장애 원인 : {result.get('cause')}")
        print(f"   심각도    : {result.get('severity')}")
        print(f"   추천 런북 : {result.get('runbook')}")

        print("④ Discord 전송 중...")
        send_discord(result, alert_names, instances)

        print("⑤ DB 저장 중...")
        await run_in_threadpool(save_to_db, result, alert_names, instances)

    elif priority == "warning":
        print("③ Gemini 생략 (WARNING 알람)")
        result = {
            "cause": "WARNING 수준 알람 - 상세 분석 생략",
            "severity": "중간",
            "recommendation": "B",
            "recommendation_reason": "WARNING 알람 모니터링 필요",
            "actions": ["로그 확인", "모니터링 강화", "추이 관찰"],
            "runbook": "없음"
        }
        print("④ Discord 전송 중...")
        send_discord(result, alert_names, instances)
        print("⑤ DB 저장 중...")
        await run_in_threadpool(save_to_db, result, alert_names, instances)

    else:
        print("③ Gemini 생략 (낮은 우선순위)")
        print("④ Discord 생략 (낮은 우선순위)")
        result = {
            "cause": "낮은 우선순위 알람",
            "severity": "낮음",
            "recommendation": "A",
            "recommendation_reason": "모니터링만 필요",
            "actions": ["로그 확인"],
            "runbook": "없음"
        }
        print("⑤ DB 저장 중...")
        await run_in_threadpool(save_to_db, result, alert_names, instances)

    print("="*50)
    return {"status": "received", "count": len(alerts), "priority": priority}

# ============================
# github로 요청 날리는 형식 
# ============================
async def trigger_github_action(event_type: str, payload: dict):
    print(f" [{now_kst()}] GitHub {event_type} 호출")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    body = {"event_type": event_type, "client_payload": payload}
    async with httpx.AsyncClient(timeout=30.0) as client_http:
        r = await client_http.post(url, headers=headers, json=body)
        if r.status_code != 204:
            print(f" GitHub 실패: {r.text}")
            raise HTTPException(500, f"GitHub API failed: {r.text}")
    print(f" GitHub {event_type} 성공!")
    return {"triggered": True}