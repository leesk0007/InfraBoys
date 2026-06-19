import asyncio
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



# ==================
# EC2 대수 활성화
# ==================
# Grafana 대시보드에서 실제 운영중인 EC2보다 많은 대수의 EC2를 스케일 인 해버리지 않기 위해 불러오기
AWS_REGION = "ap-northeast-2"
EC2_MIN_COUNT = 1
EC2_MAX_COUNT = 8

ec2_client = boto3.client('ec2', region_name=AWS_REGION)

import config
import analyzer
import notifier
import data_handler
from discord_bot import start_discord_bot

def get_current_ec2_count() -> int:
    try:
        response = config.ec2_client.describe_instances(
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.scheduler.start()
    print(f" Scheduler started")
    print(f"   정확한 한국 시간: {config.now_kst()}")
    print(f"   EC2 한계: 최소 {config.EC2_MIN_COUNT}대 / 최대 {config.EC2_MAX_COUNT}대")
    print(f"   AWS region: {config.AWS_REGION}")

    success = await config.run_in_threadpool(config.init_db)
    if not success:
        print(" DB 없이 시작 → 백그라운드에서 계속 재시도")
        asyncio.create_task(config.retry_db_connection())

    # Discord Bot 백그라운드 구동
    bot_task = asyncio.create_task(start_discord_bot())

    yield

    bot_task.cancel()
    config.scheduler.shutdown()

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
        "real_korea_time": str(config.now_kst()),
        "ntp_offset": f"{config.NTP_OFFSET:.2f}초",
        "scheduler_running": config.scheduler.running,
        "ec2_min": config.EC2_MIN_COUNT,
        "ec2_max": config.EC2_MAX_COUNT,
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/ec2_count")
async def ec2_count():
    current = get_current_ec2_count()
    return {
        "current": current,
        "min": config.EC2_MIN_COUNT,
        "max": config.EC2_MAX_COUNT,
        "available_scale_out": max(0, config.EC2_MAX_COUNT - current),
        "available_scale_in": max(0, current - config.EC2_MIN_COUNT),
    }

@app.get("/api/jobs")
async def list_jobs():
    jobs = config.scheduler.get_jobs()
    return {
        "now": str(config.now_kst()),
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
    if after > config.EC2_MAX_COUNT:
        available = max(0, config.EC2_MAX_COUNT - current)
        raise HTTPException(
            400,
            f" Scale-Out 불가: 현재 {current}대 + 요청 {req.delta}대 = {after}대 → "
            f"최대 {config.EC2_MAX_COUNT}대 초과 (가능: +{available}대까지)"
        )
    await config.trigger_github_action("scale-out", {"require_ec2": req.delta, "sender": "grafana"})
    return {"status": "success", "message": f"Scale-Out +{req.delta} triggered", "current": current, "after_expected": after}

@app.post("/api/scale-in")
async def scale_in(req: ScaleRequest):
    if req.delta < 1:
        raise HTTPException(400, "scale-in 하는 ec2는 1대 이상이어야 합니다.")
    current = get_current_ec2_count()
    after = current - req.delta
    if after < config.EC2_MIN_COUNT:
        available = max(0, current - config.EC2_MIN_COUNT)
        raise HTTPException(
            400,
            f" Scale-In 불가: 현재 {current}대 - 요청 {req.delta}대 = {after}대 → "
            f"최소 {config.EC2_MIN_COUNT}대 미만 (가능: -{available}대까지)"
        )
    await config.trigger_github_action("scale-in", {"require_ec2": req.delta, "sender": "grafana"})
    return {"status": "success", "message": f"Scale-In -{req.delta} triggered", "current": current, "after_expected": after}

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
            run_time = config.KST.localize(run_time)
    except ValueError:
        raise HTTPException(400, f"잘못된 시간 형식: {req.reserve_at}")
    if run_time <= config.now_kst():
        raise HTTPException(400, f"예약 시간은 현재({config.now_kst()}) 이후여야 합니다.")
    if req.capacity < config.EC2_MIN_COUNT or req.capacity > config.EC2_MAX_COUNT:
        raise HTTPException(400, f" Target Capacity는 {config.EC2_MIN_COUNT} ~ {config.EC2_MAX_COUNT} 범위여야 합니다. (요청: {req.capacity})")
    job = config.scheduler.add_job(
        config.trigger_github_action,
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
    job = config.scheduler.get_job(schedule_id)
    if job is None:
        return {"status": "not_found", "message": "존재하지 않거나 이미 실행됨"}
    config.scheduler.remove_job(schedule_id)
    return {"status": "success", "message": "예약 취소 완료"}

@app.post("/api/rollback")
async def rollback(req: RollbackRequest):
    await config.trigger_github_action("rollback", {"user": req.user})
    return {"status": "success", "message": "Rollback triggered"}

@app.get("/api/reserve_scale")
async def list_reserve_scale():
    jobs = config.scheduler.get_jobs()
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
    await config.trigger_github_action("scale-out", {"require_ec2": replicas, "sender": "alertmanager"})
    return {"status": "triggered", "replicas": replicas}

@app.post("/webhook/scale-in")
async def webhook_scale_in(request: Request):
    data = await request.json()
    alerts = data.get("alerts", [])
    firing = [a for a in alerts if a.get("status") == "firing"]
    if not firing:
        return {"status": "skipped"}
    await config.trigger_github_action("scale-in", {"require_ec2": 1, "sender": "alertmanager"})
    return {"status": "triggered", "replicas": 1}

# =============================================
# AIOps Webhook — troubleshoot 엔드포인트
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
    
    # Extract target_ip from instance label
    target_ip = instances.split(",")[0].split(":")[0].strip() if instances else None
    
    if target_ip and target_ip != "unknown":
        raw_logs = await data_handler.get_logs_on_demand(target_ip, container_name="app-app-1")
    else:
        raw_logs = "IP 정보를 찾을 수 없습니다."

    print("② 마스킹 중...")
    masked_logs = analyzer.mask_pii(raw_logs)

    if priority == "critical":
        print("③ Gemini 분석 중... (CRITICAL 알람)")
        result = await analyzer.analyze_with_gemini(masked_logs, alerts_summary)
        print("④ Discord 전송 중...")
        await notifier.send_discord_with_approval(result, alert_names, instances)
        print("⑤ DB 저장 중...")
        await config.run_in_threadpool(data_handler.save_to_db, result, alert_names, instances)

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
        await notifier.send_discord_with_approval(result, alert_names, instances)
        print("⑤ DB 저장 중...")
        await config.run_in_threadpool(data_handler.save_to_db, result, alert_names, instances)

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
        await config.run_in_threadpool(data_handler.save_to_db, result, alert_names, instances)

    print("="*50)
    return {"status": "received", "count": len(alerts), "priority": priority}

    # scale-in은 항상 1대 감소
    await trigger_github_action("scale-in", {
        "require_ec2": 1,
        "sender": "alertmanager"
    })

    return {"status": "triggered", "replicas": 1}
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
