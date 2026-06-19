import os
import time
import httpx
import ntplib
import pytz
import boto3
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

KST = pytz.timezone('Asia/Seoul')
# =========================================
# 깃허브 / AWS 환경변수 불러오기 
# =========================================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY") 


# ====================================================================
# Grafana 대시보드에서 예약한 시간에 스케쥴을 작동시키기 위한 스케쥴러 실행
# ====================================================================
def calculate_ntp_offset():
    servers = ['time.kriss.re.kr', 'kr.pool.ntp.org', 'time.google.com']
    for server in servers:
        try:
            client = ntplib.NTPClient()
            response = client.request(server, version=3, timeout=5)
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    print(f" Scheduler started")
    print(f"   정확한 한국 시간: {now_kst()}")
    print(f"   EC2 한계: 최소 {EC2_MIN_COUNT}대 / 최대 {EC2_MAX_COUNT}대")
    print(f"   AWS region: {AWS_REGION}")
    yield
    scheduler.shutdown()

# ==================
# EC2 대수 활성화
# ==================
# Grafana 대시보드에서 실제 운영중인 EC2보다 많은 대수의 EC2를 스케일 인 해버리지 않기 위해 불러오기
AWS_REGION = "ap-northeast-2"
EC2_MIN_COUNT = 1
EC2_MAX_COUNT = 8

ec2_client = boto3.client('ec2', region_name=AWS_REGION)


def get_current_ec2_count() -> int:
    """현재 running/pending 상태인 모든 EC2 개수 반환"""
    try:
        response = ec2_client.describe_instances(
            Filters=[
                {'Name': 'instance-state-name', 'Values': ['running', 'pending']}
            ]
        )
        count = 0
        for reservation in response['Reservations']:
            count += len(reservation['Instances'])
        print(f" 현재 EC2 대수: {count}대")
        return count
    except Exception as e:
        print(f" EC2 조회 실패: {e}")
        raise HTTPException(500, f"EC2 상태 조회 실패: {e}")


app = FastAPI(lifespan=lifespan)


# ============================================
# 브라우저 보안정책 명시 (추후 변경)
# ============================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)




# ===============================================
# 요청을 받아주는 형식 (Grafana, alertmanager)
# ===============================================

# grafana를 통한 즉시 auto scale 및 autoscale
class ScaleRequest(BaseModel):
    action: str
    delta: int = 1
    user: str = "user"

# grafana를 통한 긴급 롤백
class RollbackRequest(BaseModel):
    action: str = "rollback"
    user: str = "user"

# grafana를 통한 예약 autoscale
class ReserveScaleRequest(BaseModel):
    schedule_id: str
    reserve_at: str
    capacity: int
    duration: int
    user: str = "user"

# ==============
# 라우트
# ==============
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


@app.get("/api/ec2_count")
async def ec2_count():
    """현재 EC2 대수 조회"""
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
            {
                "id": j.id,
                "next_run_time": str(j.next_run_time),
                "args": str(j.args)
            } for j in jobs
        ]
    }

# ==========================================================
# grafana에서의 즉시 scale in / scale out + ec2 대수 확인까지 
# ==========================================================
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

    return {
        "status": "success",
        "message": f"Scale-Out +{req.delta} triggered",
        "current": current,
        "after_expected": after,
    }

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

    return {
        "status": "success",
        "message": f"Scale-In -{req.delta} triggered",
        "current": current,
        "after_expected": after,
    }
# grafana에서 예약 autoscale
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
        raise HTTPException(
            400,
            f" Target Capacity는 {EC2_MIN_COUNT} ~ {EC2_MAX_COUNT} 범위여야 합니다. "
            f"(요청: {req.capacity})"
        )

    job = scheduler.add_job(
        trigger_github_action,
        'date',
        run_date=run_time,
        args=["scheduled-scale", {
            "require_ec2": req.capacity,
            "duration": req.duration,
            "user": "grafana"
        }],
        id=req.schedule_id,
        replace_existing=True,
        misfire_grace_time=60
    )
    return {
        "status": "success",
        "schedule_id": req.schedule_id,
        "scheduled_at": str(job.next_run_time)
    }

# grafana에서 예약 autoscale 삭제
@app.delete("/api/reserve_scale/{schedule_id}")
async def cancel_reserve_scale(schedule_id: str):
    job = scheduler.get_job(schedule_id)
    if job is None:
        return {"status": "not_found", "message": "존재하지 않거나 이미 실행됨"}
    scheduler.remove_job(schedule_id)
    return {"status": "success", "message": "예약 취소 완료"}


# 긴급 롤백
@app.post("/api/rollback")
async def rollback(req: RollbackRequest):
    await trigger_github_action("rollback", {"user": "grafana"})
    return {"status": "success", "message": "Rollback triggered"}

# grafana 대시보드에서 새로고침, 창 닫기 해도 다시 예약된 목록을 불러오기
@app.get("/api/reserve_scale")
async def list_reserve_scale():
    """등록된 모든 예약 목록 반환"""
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
                "user": payload.get("grafana")
            })
    
    return {
        "count": len(schedules),
        "schedules": schedules
    }
# ===================================
# alert manager에서 보내는 요청 처리
# ===================================

@app.post("/webhook/scale-out")
async def webhook_scale_out(request: Request):
    data = await request.json()
    alerts = data.get("alerts", [])

    # firing만 처리 (resolved 무시)
    firing = [a for a in alerts if a.get("status") == "firing"]
    if not firing:
        return {"status": "skipped"}

    # 가장 높은 level 찾기 (여러 알람 묶여 들어올 수 있음)
    max_level = max(
        int(a["labels"].get("level", 0)) for a in firing
    )

    # level → 증설 대수
    replicas = 1 if max_level == 1 else 2

    # GitHub Actions 호출
    await trigger_github_action("scale-out", {
        "require_ec2": replicas,
        "sender": "alertmanager"
    })

    return {"status": "triggered", "replicas": replicas}


@app.post("/webhook/scale-in")
async def webhook_scale_in(request: Request):
    data = await request.json()
    alerts = data.get("alerts", [])

    firing = [a for a in alerts if a.get("status") == "firing"]
    if not firing:
        return {"status": "skipped"}

    # scale-in은 항상 1대 감소
    await trigger_github_action("scale-in", {
        "require_ec2": 1,
        "sender": "alertmanager"
    })

    return {"status": "triggered", "replicas": 1}
# ===============
# aiops 부분
# ===============
last_webhook = {}
@app.post("/aiops/webhook")
async def aiops_webhook(request: Request):
    global last_webhook
    last_webhook = await request.json()
    return {"ok": True}

@app.get("/aiops/last")
async def get_last():
    return last_webhook
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
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code != 204:
            print(f" GitHub 실패: {r.text}")
            raise HTTPException(500, f"GitHub API failed: {r.text}")
    print(f" GitHub {event_type} 성공!")
    return {"triggered": True}