import requests
from datetime import datetime
import config

def build_embed_dict(result: dict, alert_names: str, instances: str, ai_log_evidence: str = None):
    color_map = {"높음": 0xFF0000, "중간": 0xFF8C00, "낮음": 0x00FF00}
    color = color_map.get(result.get("severity", ""), 0x5865F2)
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    actions_text = "\n".join(
        [f"{i+1}. {a}" for i, a in enumerate(result.get("actions", []))]
    )

    if not actions_text.strip():
        actions_text = "없음"

    fields = [
        {"name": "서버",      "value": instances,                               "inline": True},
        {"name": "감지 시각", "value": now,                                     "inline": True},
        {"name": "장애 원인", "value": result.get("cause", "알 수 없음"),       "inline": False},
        {"name": "심각도",    "value": result.get("severity", ""),              "inline": True},
        {"name": "추천 대응", "value": result.get("recommendation", ""),        "inline": True},
        {"name": "추천 이유", "value": result.get("recommendation_reason", ""), "inline": False},
        {"name": "즉시 조치", "value": actions_text,                            "inline": False},
        {"name": "추천 런북", "value": result.get("runbook", ""),               "inline": False},
    ]

    if ai_log_evidence:
        fields.append({"name": "핵심 오류 로그 (AI 발췌)", "value": f"```\n{ai_log_evidence}\n```", "inline": False})

    return {
        "title": f"장애 감지 - {alert_names}",
        "color": color,
        "fields": fields,
        "footer": {"text": "Privacy AIOps - 로그는 마스킹 처리 후 AI 분석됨"}
    }

def send_discord(result: dict, alert_names: str, instances: str, ai_log_evidence: str = None):
    embed_dict = build_embed_dict(result, alert_names, instances, ai_log_evidence)
    payload = {
        "username": "AIOps 분석 봇",
        "embeds": [embed_dict]
    }
    try:
        res = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if res.status_code == 204:
            print(" Discord 전송 성공")
        else:
            print(f" Discord 전송 실패: {res.status_code}")
    except requests.RequestException as e:
        print(f" Discord 전송 실패 (무시하고 계속): {e}")

async def send_discord_with_approval(result: dict, alert_names: str, instances: str, ai_log_evidence: str = None, aiops_log_id: int = None):
    """분석 결과를 Discord Bot으로 전송하면서 승인/거부 버튼을 첨부"""
    import discord
    from discord_bot import bot, RunbookApprovalView

    if not config.DISCORD_CHANNEL_ID or config.DISCORD_CHANNEL_ID == "YOUR_DISCORD_CHANNEL_ID":
        print(" [Notifier] Discord 채널 ID가 없습니다. Webhook으로 fallback")
        send_discord(result, alert_names, instances, ai_log_evidence)
        return

    channel = bot.get_channel(int(config.DISCORD_CHANNEL_ID))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(config.DISCORD_CHANNEL_ID))
        except Exception as e:
            print(f" [Notifier] Discord 채널을 찾을 수 없음 ({e}). Webhook으로 fallback")
            send_discord(result, alert_names, instances, ai_log_evidence)
            return

    # Embed 생성
    embed_dict = build_embed_dict(result, alert_names, instances, ai_log_evidence)
    embed = discord.Embed.from_dict(embed_dict)

    runbook = result.get("runbook", "")

    # 런북이 추천된 경우에만 승인 버튼 포함
    if runbook and runbook != "없음" and runbook != "알 수 없음":
        view = RunbookApprovalView(result, alert_names, instances, aiops_log_id)
        msg = await channel.send(
            content=f"🚨 **런북 실행 승인 필요** — `{runbook}`",
            embed=embed,
            view=view
        )
        view.message = msg  # 타임아웃 처리를 위해 메시지 객체 저장
    else:
        # 추천 런북이 없으면 버튼 없이 전송
        await channel.send(embed=embed)
