import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os

print("🔄 A iniciar o script do bot...")

# ===============================
# CONFIG
# ===============================

TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN ou DISCORD_TOKEN não configurado na variável de ambiente.")

CANAL_PAINEL_ID = 1570446068490043442   # Canal do painel fixo
CANAL_ALERTAS_ID = 1570454121922822265  # Canal de alertas (@everyone)

TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = discord.Client(intents=intents)

lock = asyncio.Lock()
alertas_enviados_memoria = set()

# ===============================
# BOSSES (APENAS OS QUE VALEM PONTOS / ATIVOS)
# ===============================

BOSSES = [
    ("Blood Wizard", "18:10", None, "Devias (/pvp2)", "159, 32", "🧙‍♂️", 10),
    ("Crusher Skeleton", "19:05", None, "Lorencia", "Spawn aleatório", "💀", 15),
    ("Selupan", "20:10", None, "Raklion (após a ponte, /pvp4)", "174, 2027", "🕷️", 15),
    ("Galia Black", "20:30", None, "Lost Tower 1 (à esquerda do /move)", "166, 77", "🦇", 15),
    ("Gwyn, o Senhor das Cinzas", "22:10", None, "Dungeon 3", "25, 72", "🔥", 20),
    ("Hellmaine", "22:30", None, "Aida (/hellmaine)", "115, 100", "🐺", 25),
    ("Balgass", "23:00", [2, 5], "Crywolf Fortress", "112, 80 (Somente quartas e sábados)", "👑", 50),
    ("Yhorm", "23:40", None, "/lorencia1", "22, 46", "🛡️", 20),
    ("Zorlak", "01:10", None, "Lorencia", "Spawn aleatório", "⚡", 15),
]

# ===============================
# ESTADO
# ===============================

def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {}
    try:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def salvar_estado(estado):
    try:
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f)
    except Exception:
        pass

estado = carregar_estado()

# ===============================
# FORMATAR TEMPO (HH:MM:SS)
# ===============================

def formatar_tempo(segundos_totais):
    if segundos_totais <= 0:
        return "🔴 Nascendo agora!"
    
    horas = int(segundos_totais // 3600)
    minutos = int((segundos_totais % 3600) // 60)
    segundos = int(segundos_totais % 60)
    
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

# ===============================
# GERAR EMBED COM PONTOS E EMOJIS
# ===============================

def criar_embed_agenda_detalhada(agora):
    weekday_atual = agora.weekday()
    
    embed = discord.Embed(
        title="🛡️ HORÁRIOS DE BOSSES E PONTUAÇÃO",
        description="━━━━━━━━━━━━━━━━━━━━",
        color=0x9b59b6
    )

    encontrou_algum = False

    for nome, horario, dias, mapa, coords, emoji, pontos in BOSSES:
        if dias is not None and weekday_atual not in dias:
            continue

        hora, minuto = map(int, horario.split(":"))
        dt_boss = TIMEZONE.localize(
            datetime(agora.year, agora.month, agora.day, hora, minuto)
        )

        if dt_boss < agora:
            dt_boss += timedelta(days=1)

        diferenca = (dt_boss - agora).total_seconds()
        tempo_formatado = formatar_tempo(diferenca)

        if diferenca <= 600:
            status_icone = "🔥"
        else:
            status_icone = "⏳"

        texto_campo = (
            f"📍 **Mapa:** {mapa}\n"
            f"⏰ **Horário:** {horario}  |  📌 **Coords:** `{coords}`\n"
            f"🏆 **Vale:** `{pontos} pontos`\n"
            f"{status_icone} **Faltam:** `{tempo_formatado}`\n"
            f"────────────────────────"
        )

        embed.add_field(
            name=f"{emoji} {nome}",
            value=texto_campo,
            inline=False
        )
        encontrou_algum = True

    if not encontrou_algum:
        embed.description = "Nenhum boss programado para hoje."

    embed.add_field(
        name="\u200b",
        value="━━━━━━━━━━━━━━━━━━━━\n*Fique atento aos horários e prepare-se para disputar os bosses!*",
        inline=False
    )
    
    return embed

# ===============================
# VERIFICAÇÃO ANTI-DUPLICIDADE NO CHAT
# ===============================

async def alerta_ja_postado_recentemente(canal, nome_boss):
    try:
        limite_tempo = datetime.now(pytz.utc) - timedelta(minutes=15)
        async for msg in canal.history(limit=15, after=limite_tempo):
            if msg.author == bot.user and msg.embeds:
                titulo = msg.embeds[0].title or ""
                if nome_boss in titulo:
                    return True
    except Exception:
        pass
    return False

# ===============================
# LOOP PRINCIPAL (EDITA A MESMA MENSAGEM DO PAINEL)
# ===============================

@tasks.loop(seconds=5)
async def verificar_boss():
    async with lock:
        agora = datetime.now(TIMEZONE)

        # 1. ATUALIZAÇÃO DO PAINEL DE HORÁRIOS (EDITANDO A MENSAGEM EXISTENTE)
        canal_painel = bot.get_channel(CANAL_PAINEL_ID)
        if not canal_painel:
            try:
                canal_painel = await bot.fetch_channel(CANAL_PAINEL_ID)
            except discord.DiscordException:
                canal_painel = None

        if canal_painel:
            embed_painel = criar_embed_agenda_detalhada(agora)
            msg_id = estado.get("id_mensagem_painel")
            msg_painel = None

            if msg_id:
                try:
                    msg_painel = await canal_painel.fetch_message(msg_id)
                except (discord.NotFound, discord.HTTPException):
                    msg_painel = None

            # Se não encontrou a mensagem anterior guardada, procura nas últimas do bot no canal
            if not msg_painel:
                try:
                    async for m in canal_painel.history(limit=10):
                        if m.author == bot.user and m.embeds and "HORÁRIOS DE BOSSES" in (m.embeds[0].title or ""):
                            msg_painel = m
                            break
                except Exception:
                    pass

            if msg_painel:
                try:
                    await msg_painel.edit(embed=embed_painel)
                except discord.HTTPException:
                    pass
            else:
                # Se realmente não existir nenhuma, cria a primeira
                nova_msg = await canal_painel.send(embed=embed_painel)
                estado["id_mensagem_painel"] = nova_msg.id
                salvar_estado(estado)

        # 2. CANAL DE ALERTAS (SOMENTE 10 MINUTOS ANTES)
        canal_alertas = bot.get_channel(CANAL_ALERTAS_ID)
        if not canal_alertas:
            try:
                canal_alertas = await bot.fetch_channel(CANAL_ALERTAS_ID)
            except discord.DiscordException:
                canal_alertas = None

        if canal_alertas:
            for evento in BOSSES:
                nome, horario, dias, mapa, coords, emoji, pontos = evento

                if dias is not None and agora.weekday() not in dias:
                    continue

                hora_boss = datetime.strptime(horario, "%H:%M")
                hora_boss = TIMEZONE.localize(
                    datetime(agora.year, agora.month, agora.day, hora_boss.hour, hora_boss.minute)
                )

                if hora_boss < agora:
                    hora_boss += timedelta(days=1)

                diferenca = (hora_boss - agora).total_seconds()
                data_hoje = agora.strftime('%Y-%m-%d')
                chave_10 = f"{nome}_{horario}_{data_hoje}_10min"

                if 590 <= diferenca <= 600:
                    if chave_10 in alertas_enviados_memoria or estado.get(chave_10):
                        continue

                    if await alerta_ja_postado_recentemente(canal_alertas, nome):
                        alertas_enviados_memoria.add(chave_10)
                        estado[chave_10] = True
                        salvar_estado(estado)
                        continue

                    alertas_enviados_memoria.add(chave_10)
                    estado[chave_10] = True
                    salvar_estado(estado)

                    embed_10 = discord.Embed(
                        title=f"🔥 BOSS {emoji} {nome} NASCENDO EM 10 MINUTOS! 🔥",
                        description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} (`{coords}`)\n🏆 **Vale:** {pontos} pontos\n\n*Corram para o local!*",
                        color=0xffa500
                    )
                    msg_alerta = await canal_alertas.send(
                        content="@everyone",
                        embed=embed_10,
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )
                    
                    asyncio.create_task(apagar_mensagem_depois(msg_alerta, 900))

async def apagar_mensagem_depois(mensagem, segundos):
    await asyncio.sleep(segundos)
    try:
        await mensagem.delete()
    except discord.NotFound:
        pass
    except discord.DiscordException:
        pass

# ===============================
# READY
# ===============================

@bot.event
async def on_ready():
    print(f"🛡️ Bot conectado com sucesso como {bot.user}")
    if not verificar_boss.is_running():
        verificar_boss.start()
        print("🚀 Loop de verificação iniciado com sucesso!")

# ===============================
# EXECUÇÃO
# ===============================

if __name__ == "__main__":
    bot.run(TOKEN)
