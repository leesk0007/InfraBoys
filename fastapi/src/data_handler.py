from collections import deque
import config
import asyncssh
import asyncio

# =============================================
# DB 저장
# =============================================
def save_to_db(result: dict, alert_name: str, instance: str, raw_log: str = None, log_excerpt: str = None):
    """알람 분석 결과를 저장하고, 새로 생긴 row의 id를 반환한다 (Discord 승인 결과를 연결하기 위함)."""
    if config.db_connection_pool is None:
        print(" DB 연결 풀 없음 - 저장 건너뜀")
        return None

    conn = None
    try:
        conn = config.db_connection_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO aiops_logs (
                    alert_name, instance, cause,
                    severity, recommendation, runbook,
                    raw_log, log_excerpt, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                alert_name,
                instance,
                result.get("cause", ""),
                result.get("severity", ""),
                result.get("recommendation", ""),
                result.get("runbook", ""),
                raw_log,
                log_excerpt
            ))
            new_id = cur.fetchone()[0]
        conn.commit()
        print(f" DB 저장 완료 (id={new_id})")
        return new_id
    except Exception as e:
        if conn:
            conn.rollback()
        print(f" DB 저장 실패: {e}")
        return None
    finally:
        if conn:
            config.db_connection_pool.putconn(conn)

# =============================================
# Discord 승인/거부 결과 기록
# =============================================
def mark_decision(aiops_log_id: int, decision: str, decided_by: str = None):
    if aiops_log_id is None:
        print(" aiops_log_id 없음 - 승인 결과 저장 건너뜀")
        return
    if config.db_connection_pool is None:
        print(" DB 연결 풀 없음 - 승인 결과 저장 건너뜀")
        return

    conn = None
    try:
        conn = config.db_connection_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE aiops_logs
                SET decision = %s, decided_by = %s, decided_at = NOW()
                WHERE id = %s
            """, (decision, decided_by, aiops_log_id))
        conn.commit()
        print(f" 승인 결과 저장 완료 (id={aiops_log_id}, decision={decision})")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f" 승인 결과 저장 실패: {e}")
    finally:
        if conn:
            config.db_connection_pool.putconn(conn)

# =============================================
# DB 조회 (ChatOps 용)
# =============================================
def get_history(limit: int = 5):
    if config.db_connection_pool is None:
        return []
    
    conn = None
    try:
        conn = config.db_connection_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT alert_name, instance, cause, severity, created_at, decision, decided_by
                FROM aiops_logs
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()

            history = []
            for r in rows:
                history.append({
                    "alert_name": r[0],
                    "instance": r[1],
                    "cause": r[2],
                    "severity": r[3],
                    "created_at": r[4].strftime("%Y-%m-%d %H:%M:%S") if r[4] else "",
                    "decision": r[5],
                    "decided_by": r[6]
                })
            return history
    except Exception as e:
        print(f" DB 조회 실패: {e}")
        return []
    finally:
        if conn:
            config.db_connection_pool.putconn(conn)

# =============================================
# On-Demand SSH 로그 수집
# =============================================
async def get_logs_on_demand(target_ip: str, container_name: str = "fastapi") -> str:
    """
    지정된 EC2 인스턴스(target_ip)에 SSH로 접속하여 도커 로그를 수집합니다.
    """
    try:
        print(f"[{target_ip}] SSH 접속 시도...")
        async with asyncssh.connect(
            target_ip, 
            username=config.SSH_USER, 
            client_keys=[config.SSH_KEY_PATH],
            known_hosts=None, # 내부망이므로 known_hosts 무시
            login_timeout=5   # 타임아웃 5초 설정
        ) as conn:
            # 최근 5분, 최대 300줄 추출
            cmd = f"docker logs --since 5m --tail 300 {container_name}"
            result = await conn.run(cmd, check=False)
            
            logs = result.stdout + result.stderr
            if not logs.strip():
                return f"[{target_ip}] 로그가 없거나 컨테이너({container_name})를 찾을 수 없습니다."
            
            # 너무 긴 경우 대비 자르기
            lines = logs.splitlines()[-300:]
            return "\\n".join(lines)
            
    except Exception as e:
        return f"[{target_ip}] SSH 접속 또는 로그 수집 실패: {e}"

# 로컬(기존) 로그 읽기 대비용
def get_local_logs():
    try:
        with open(config.LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            last_100 = deque(f, maxlen=100)
            return "".join(last_100)
    except FileNotFoundError:
        return "로그 파일 없음"
