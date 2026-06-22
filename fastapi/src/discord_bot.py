import discord
from discord.ext import commands
import asyncio
import config
import data_handler
import analyzer
from fastapi import HTTPException

# Discord Intents 설정 (메시지 읽기 권한 등)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f" [Discord Bot] 로그인 성공: {bot.user.name} ({bot.user.id})")
    if config.DISCORD_CHANNEL_ID:
        channel = bot.get_channel(int(config.DISCORD_CHANNEL_ID))
        if channel:
            await channel.send("🤖 **AIOps ChatOps 봇이 시작되었습니다!** `!help`로 명령어를 확인하세요.")

@bot.command(name="help")
async def cmd_help(ctx):
    """명령어 도움말 출력"""
    embed = discord.Embed(title="AIOps ChatOps 명령어", color=0x5865F2)
    embed.add_field(name="`!status`", value="현재 EC2 인스턴스 수 및 시스템 상태 조회", inline=False)
    embed.add_field(name="`!scale-out <숫자>`", value="수동으로 인스턴스 Scale-Out 실행", inline=False)
    embed.add_field(name="`!scale-in <숫자>`", value="수동으로 인스턴스 Scale-In 실행", inline=False)
    embed.add_field(name="`!logs <서버IP>`", value="특정 서버의 최근 로그를 On-Demand로 수집", inline=False)
    embed.add_field(name="`!analyze <서버IP>`", value="수동으로 Gemini AI 로그 분석 실행", inline=False)
    embed.add_field(name="`!history [숫자]`", value="최근 저장된 장애 이력 N건 조회 (기본 5건)", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="status")
async def cmd_status(ctx):
    """EC2 상태 및 스케줄러 상태 조회"""
    try:
        from main import get_current_ec2_count
        count = get_current_ec2_count()
        jobs = config.scheduler.get_jobs()
        embed = discord.Embed(title="📊 시스템 상태", color=0x00FF00)
        embed.add_field(name="현재 EC2 수", value=f"{count} / {config.EC2_MAX_COUNT} 대", inline=True)
        embed.add_field(name="스케줄러", value=f"{len(jobs)}개 작업 예약됨", inline=True)
        embed.add_field(name="DB 연결", value="정상" if config.db_connection_pool else "연결 없음", inline=True)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 상태 조회 중 오류 발생: {e}")

@bot.command(name="scale-out")
async def cmd_scale_out(ctx, count: int = 1):
    """Scale-out 실행"""
    await ctx.send(f"⏳ Scale-Out (+{count}대) 트리거 중...")
    try:
        await config.trigger_github_action("scale-out", {"require_ec2": count, "sender": ctx.author.name})
        await ctx.send(f"✅ **Scale-Out (+{count}대)이 트리거되었습니다.** Github Actions에서 실행 중입니다.")
    except Exception as e:
        await ctx.send(f"❌ Scale-Out 실패: {e}")

@bot.command(name="scale-in")
async def cmd_scale_in(ctx, count: int = 1):
    """Scale-in 실행"""
    await ctx.send(f"⏳ Scale-In (-{count}대) 트리거 중...")
    try:
        await config.trigger_github_action("scale-in", {"require_ec2": count, "sender": ctx.author.name})
        await ctx.send(f"✅ **Scale-In (-{count}대)이 트리거되었습니다.** Github Actions에서 실행 중입니다.")
    except Exception as e:
        await ctx.send(f"❌ Scale-In 실패: {e}")

@bot.command(name="logs")
async def cmd_logs(ctx, target_ip: str):
    """지정된 대상에 SSH로 접속하여 로그를 가져옵니다."""
    await ctx.send(f"🔎 `{target_ip}` 서버의 로그를 가져오는 중... (최대 300줄)")
    logs = await data_handler.get_logs_on_demand(target_ip)
    
    # Discord 메시지 제한(2000자) 고려하여 자르기
    if len(logs) > 1900:
        logs = logs[-1900:]
        
    await ctx.send(f"**[{target_ip}] 서버 로그:**\n```\n{logs}\n```")

@bot.command(name="analyze")
async def cmd_analyze(ctx, target_ip: str):
    """수동으로 대상 로그를 수집하고 Gemini로 분석합니다."""
    await ctx.send(f"🔎 `{target_ip}` 서버의 로그를 수집하고 분석을 시작합니다...")
    raw_logs = await data_handler.get_logs_on_demand(target_ip)
    
    masked_logs = analyzer.mask_pii(raw_logs)
    summary = f"- 수동 분석 요청자: {ctx.author.name}"
    
    result = await analyzer.analyze_with_gemini(masked_logs, summary)
    
    # 결과를 Discord로 전송
    embed = discord.Embed(title=f"🧠 수동 AI 분석 결과 - {target_ip}", color=0x9B59B6)
    embed.add_field(name="장애 원인", value=result.get("cause", "알 수 없음"), inline=False)
    embed.add_field(name="심각도", value=result.get("severity", "알 수 없음"), inline=True)
    embed.add_field(name="추천 대응", value=result.get("recommendation", "알 수 없음"), inline=True)
    
    actions_text = "\n".join([f"- {a}" for a in result.get("actions", [])])
    if actions_text:
        embed.add_field(name="즉시 조치", value=actions_text, inline=False)
        
    embed.add_field(name="추천 런북", value=result.get("runbook", "없음"), inline=False)
    
    await ctx.send(embed=embed)
    
    # DB 저장
    import main
    await config.run_in_threadpool(data_handler.save_to_db, result, "ManualAnalysis", target_ip)

@bot.command(name="history")
async def cmd_history(ctx, count: int = 5):
    """DB에서 장애 이력을 가져옵니다."""
    history = await config.run_in_threadpool(data_handler.get_history, count)
    
    if not history:
        await ctx.send("📭 기록된 장애 이력이 없습니다.")
        return
        
    decision_map = {
        "approved": f"✅ 승인 ({h.get('decided_by') or '알 수 없음'})",
        "denied": f"❌ 거부 ({h.get('decided_by') or '알 수 없음'})",
        "timeout": "⏰ 타임아웃 (무응답 자동거부)",
    }

    embed = discord.Embed(title=f"📜 최근 장애 이력 (최대 {count}건)", color=0x3498DB)
    for h in history:
        decision_text = decision_map.get(h.get("decision"), "⏳ 대기중 / 해당없음")
        embed.add_field(
            name=f"[{h['created_at']}] {h['alert_name']}",
            value=f"서버: {h['instance']} | 심각도: {h['severity']}\n원인: {h['cause'][:100]}...\n처리: {decision_text}",
            inline=False
        )
    await ctx.send(embed=embed)

class RunbookApprovalView(discord.ui.View):
    """런북 실행 승인/거부 버튼이 포함된 View"""
    
    def __init__(self, result: dict, alert_names: str, instances: str, aiops_log_id: int = None):
        super().__init__(timeout=300) # 5분 타임아웃
        self.result = result
        self.alert_names = alert_names
        self.instances = instances
        self.aiops_log_id = aiops_log_id
        self.responded = False
        self.message = None

    @discord.ui.button(label="✅ 런북 실행 승인", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True

        runbook = self.result.get("runbook", "알 수 없는 런북")
        mapping = config.RUNBOOK_ACTION_MAP.get(runbook)

        if not mapping:
            await interaction.response.edit_message(
                content=f"❌ **지원하지 않는 런북입니다:** `{runbook}`",
                view=None
            )
            return

        # 버튼 비활성화 + 실행 중 표시
        await interaction.response.edit_message(
            content=f"⏳ **GitHub Actions 실행 요청 중...**\n- 액션: {mapping['description']}\n- 승인자: {interaction.user.name}",
            view=None
        )

        # 실제 GitHub Actions API 호출
        try:
            target_ip = self.instances.split(",")[0].split(":")[0].strip() if self.instances else ""
            payload = {**mapping["payload"], "target_ip": target_ip}

            await config.trigger_github_action(mapping["event_type"], payload)
            await config.run_in_threadpool(data_handler.mark_decision, self.aiops_log_id, "approved", interaction.user.name)

            await interaction.followup.send(
                f"✅ **런북 실행 요청 성공!**\n"
                f"- GitHub Actions에서 `{mapping['event_type']}` 이벤트가 트리거되었습니다.\n"
                f"- 대상 런북: `{runbook}`"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ **런북 실행 요청 실패:** {e}")

    @discord.ui.button(label="❌ 거부", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True

        await config.run_in_threadpool(data_handler.mark_decision, self.aiops_log_id, "denied", interaction.user.name)

        await interaction.response.edit_message(
            content=f"❌ **런북 실행이 거부되었습니다.** (거부자: {interaction.user.name})",
            view=None
        )

    async def on_timeout(self):
        """5분 동안 응답 없으면 자동 만료"""
        if not self.responded and self.message:
            try:
                await config.run_in_threadpool(data_handler.mark_decision, self.aiops_log_id, "timeout", None)
                await self.message.edit(
                    content="⏰ **승인 시간 초과 (5분)** — 런북 실행이 자동 거부되었습니다.",
                    view=None
                )
            except Exception as e:
                print(f" 타임아웃 메시지 업데이트 실패: {e}")

async def start_discord_bot():
    """FastAPI lifespan에서 호출되어 백그라운드에서 동작할 봇 구동기"""
    if config.DISCORD_BOT_TOKEN and config.DISCORD_BOT_TOKEN != "YOUR_DISCORD_BOT_TOKEN":
        print(" [Discord Bot] 봇 구동 시작...")
        try:
            await bot.start(config.DISCORD_BOT_TOKEN)
        except Exception as e:
            print(f" [Discord Bot] 봇 구동 실패: {e}")
    else:
        print(" [Discord Bot] 토큰이 설정되지 않아 봇을 시작하지 않습니다.")
