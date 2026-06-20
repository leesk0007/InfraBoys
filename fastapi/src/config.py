import os
import sys
import time
import asyncio
from datetime import timedelta, datetime
import pytz
import ntplib
import boto3
from psycopg2 import pool as pg_pool
from fastapi.concurrency import run_in_threadpool
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID  = os.getenv("DISCORD_CHANNEL_ID")
LOG_FILE            = os.getenv("LOG_FILE", "/app/nginx.log")

# SSH 환경변수 (On-Demand 로깅)
SSH_USER     = os.getenv("SSH_USER", "ec2-user")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/app/keys/project02-was-key.pem")

if not GEMINI_API_KEY:
    print(" 오류: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

if not DISCORD_WEBHOOK_URL:
    print(" 오류: DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

# =========================================
# AWS 설정
# =========================================
AWS_REGION = "ap-northeast-2"
EC2_MIN_COUNT = 1
EC2_MAX_COUNT = 8
ec2_client = boto3.client('ec2', region_name=AWS_REGION)

# =========================================
# DB 설정
# =========================================
DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

db_connection_pool = None

# =============================================
# Circuit Breaker 전역 상태
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
# NTP 시간 동기화 및 스케줄러
# =============================================
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

# ============================
# github로 요청 날리는 형식 
# ============================
import httpx
from fastapi import HTTPException

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

# ============================================
# 런북 → GitHub Actions 매핑 (라우팅)
# ============================================
RUNBOOK_ACTION_MAP = {
    # 기존 런북
    "runbook-scale-out.yml": {
        "event_type": "scale-out",  # predictive-scaling.yml 을 트리거함
        "payload": {
            "require_ec2": 2, 
            "sender": "AIOps Discord Bot",
            "reason": "AI 장애 분석 결과에 따른 스케일 아웃 승인"
        },
        "description": "EC2 인스턴스 2대 스케일 아웃"
    },
    "runbook-db-restart.yml": {
        "event_type": "db-restart",
        "payload": {"sender": "AIOps Discord Bot"},
        "description": "DB 인스턴스 재시작"
    },
    "runbook-rollback.yml": {
        "event_type": "app-rollback",
        "payload": {"sender": "AIOps Discord Bot"},
        "description": "이전 버전 애플리케이션 롤백"
    },
    # AIOps 장애 전용 런북 추가
    "was_restart_nginx.yml": {
        "event_type": "incident-response",
        "payload": {"playbook": "was_restart_nginx.yml", "sender": "AIOps Discord Bot"},
        "description": "Nginx 프로세스 재시작"
    },
    "was_cleanup_disk.yml": {
        "event_type": "incident-response",
        "payload": {"playbook": "was_cleanup_disk.yml", "sender": "AIOps Discord Bot"},
        "description": "디스크 임시 파일 정리"
    },
    "was_kill_process.yml": {
        "event_type": "incident-response",
        "payload": {"playbook": "was_kill_process.yml", "sender": "AIOps Discord Bot"},
        "description": "고부하/좀비 프로세스 강제 종료"
    },
    "db_kill_idle_connections.yml": {
        "event_type": "incident-response",
        "payload": {"playbook": "db_kill_idle_connections.yml", "sender": "AIOps Discord Bot"},
        "description": "PostgreSQL Idle 커넥션 풀 강제 정리"
    },
    "db_restart_container.yml": {
        "event_type": "incident-response",
        "payload": {"playbook": "db_restart_container.yml", "sender": "AIOps Discord Bot"},
        "description": "PostgreSQL DB 컨테이너 재시작"
    }
}
