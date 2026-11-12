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

CANAL_PAINEL_ID = 1570446068490043442   # Canal do painel fixo de horários
CANAL_ALERTAS_ID = 1570454121922822265  # Canal de alertas (@everyone)
CANAL_RANKING_ID = 1570446068490043442   # Canal onde o ranking será fixado e atualizado

TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = discord.Client(intents=intents)

lock = asyncio.Lock()
alertas_enviados_memoria = set()

# ===============================
# BOSSES E PONTUAÇÕES
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
# ESTADO E PERSISTÊNCIA
# ===============================

def carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO):
        return {"ranking": {}, "id_mensagem_painel": None, "id_mensagem_ranking": None}
    try:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            dados = json.load(f)
            if "ranking" not in dados:
                dados["ranking"] = {}
            return dados
    except Exception:
        return {"ranking": {}, "id_mensagem_painel": None, "id_mensagem_ranking": None}

def salvar_estado(estado):
    try:
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=4)
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
# EMBED DO PAINEL DE HORÁRIOS
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

        status_icone = "🔥" if diferenca <= 600 else "⏳"

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
# EMBED DO RANKING GERAL COMPLETO
# ===============================

def criar_embed_ranking():
    embed = discord.Embed(
        title="🏆 RANKING GERAL ATUALIZADO DA GUILDA",
        description="Placar geral somando todos os pontos acumulados por cada membro.",
        color=0xf1c40f
    )

    ranking_atual = estado.get("ranking", {})

    if not ranking_atual:
        embed.add_field(
            name="📊 Placar Vazio",
            value="Ainda não há pontuações registadas.",
            inline=False
        )
    else:
        # Ordena todos os membros por pontos (do maior para o menor)
        ranking_ordenado = sorted(ranking_atual.items(), key=lambda item: item[1], reverse=True)
        
        texto_ranking = ""
        for i, (membro, pontos) in enumerate(ranking_ordenado, start=1):
            if i == 1:
                medalha = "🥇"
            elif i == 2:
                medalha = "🥈"
            elif i == 3:
                medalha = "🥉"
            else:
                medalha = f"`#{i}`"
            
            texto_ranking += f"{medalha} **{membro}** — `{pontos} pts`\n"

        # Como o Discord tem limite de caracteres por campo (1024), dividimos se passar de muitas pessoas
        if len(texto_ranking) > 1024:
            # Caso a lista seja gigante, o embed divide de forma segura
            embed.add_field(name="🏅 Placar Completo", value=texto_ranking[:1024], inline=False)
        else:
            embed.add_field(name="🏅 Placar Completo", value=texto_ranking, inline=False)

    embed.set_footer(text="Atualizado em tempo real • Total de membros pontuados: " + str(len(ranking_atual)))
    return embed

# ===============================
# FUNÇÃO PARA ADICIONAR PONTOS
# ===============================

def adicionar_pontos(nome_membro, quantidade):
    ranking = estado.get("ranking", {})
    ranking[nome_membro] = ranking.get(nome_membro, 0) + quantidade
    estado["ranking"] = ranking
    salvar_estado(estado)

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
# LOOP PRINCIPAL (PAINEL + RANKING GERAL + ALERTAS)
# ===============================

@tasks.loop(seconds=5)
async def verificar_boss():
    async with lock:
        agora = datetime.now(TIMEZONE)

        # 1. ATUALIZAÇÃO DO PAINEL DE HORÁRIOS (EDITA A MESMA MENSAGEM)
        canal_painel = bot.get_channel(CANAL_PAINEL_ID)
        if canal_painel:
            embed_painel = criar_embed_agenda_detalhada(agora)
            msg_id_painel = estado.get("id_mensagem_painel")
            msg_painel = None

            if msg_id_painel:
                try:
                    msg_painel = await canal_painel.fetch_message(msg_id_painel)
                except discord.NotFound:
                    msg_painel = None

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
                nova_msg = await canal_painel.send(embed=embed_painel)
                estado["id_mensagem_painel"] = nova_msg.id
                salvar_estado(estado)

        # 1.1 ATUALIZAÇÃO DO RANKING GERAL (EDITA A MESMA MENSAGEM SEM APAGAR)
        canal_ranking = bot.get_channel(CANAL_RANKING_ID)
        if canal_ranking:
            embed_ranking = criar_embed_ranking()
            msg_id_ranking = estado.get("id_mensagem_ranking")
            msg_ranking = None

            if msg_id_ranking:
                try:
                    msg_ranking = await canal_ranking.fetch_message(msg_id_ranking)
                except discord.NotFound:
                    msg_ranking = None

            if not msg_ranking:
                try:
                    async for m in canal_ranking.history(limit=10):
                        if m.author == bot.user and m.embeds and "RANKING GERAL" in (m.embeds
