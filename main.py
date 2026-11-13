import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os

print("🔄 A iniciar o script unificado do bot com volume em /data...")

# =========================================================
# CONFIGURAÇÕES DE CANAIS EXATOS
# =========================================================

TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN ou DISCORD_TOKEN não configurado nas variáveis de ambiente do Railway.")

CANAL_ALERTAS_ID = 1570454121922822265  # Canal: ⚠️-alerta-dos-boss
CANAL_PAINEL_ID = 1570446068490043442   # Canal: ⏰ horários-boss
CANAL_PRESENCA_ID = 1561134289595142235 # Canal: 🧙‍♂️ presença-boss
CANAL_RANKING_ID = 1570234809719070842  # Canal: 💯 ranking-boss
CANAL_CONSULTA_ID = 1570446068490043442 # Canal: 🔍 consultar-pontos

TIMEZONE = pytz.timezone("America/Sao_Paulo")

# Garante que o estado.json é lido/gravado na pasta persistente do volume em /data
ARQUIVO_ESTADO = "/data/estado.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = discord.Client(intents=intents)

lock = asyncio.Lock()
alertas_10min_memoria = set()
listas_5min_memoria = set()
ultima_mensagem_lista = None

BOSSES = {
    "blood wizard": ("Blood Wizard", "18:10", None, "Devias (/pvp2)", "159, 32", "🧙‍♂️", 10),
    "crusher skeleton": ("Crusher Skeleton", "19:05", None, "Lorencia", "Spawn aleatório", "💀", 15),
    "necromancer": ("Necromancer", "19:40", None, "Elbeland 2 (/devias4)", "29, 39", "🔮", 15),
    "selupan": ("Selupan", "20:10", None, "Raklion (após a ponte, /pvp4)", "174, 2027", "🕷️", 15),
    "galia black": ("Galia Black", "20:30", None, "Lost Tower 1 (à esquerda do /move)", "166, 77", "🦇", 15),
    "skull reaper": ("Skull Reaper", "20:50", None, "Dungeon 1 (à esquerda do /move)", "92, 237", "⚔️", 15),
    "gwyn": ("Gwyn, o Senhor das Cinzas", "22:10", None, "Dungeon 3", "25, 72", "🔥", 20),
    "hellmaine": ("Hellmaine", "22:30", None, "Aida (/hellmaine)", "115, 100", "🐺", 25),
    "balgass": ("Balgass", "23:00", [2, 5], "Crywolf Fortress", "112, 80 (Somente quartas e sábados)", "👑", 50),
    "yhorm": ("Yhorm", "23:40", None, "/lorencia1", "22, 46", "🛡️", 20),
    "zorlak": ("Zorlak", "01:10", None, "Lorencia", "Spawn aleatório", "⚡", 15),
}

# =========================================================
# ESTADO E PERSISTÊNCIA SEGURA
# =========================================================

def estado_padrao():
    return {
        "ranking": {},
        "id_mensagem_painel": None,
        "id_mensagem_ranking": None,
        "id_mensagem_consulta": None,
    }

def carregar_estado():
    # Cria a pasta /data caso não exista
    os.makedirs(os.path.dirname(ARQUIVO_ESTADO), exist_ok=True)
    if not os.path.exists(ARQUIVO_ESTADO):
        return estado_padrao()
    try:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        if not isinstance(dados, dict):
            return estado_padrao()
        dados.setdefault("ranking", {})
        dados.setdefault("id_mensagem_painel", None)
        dados.setdefault("id_mensagem_ranking", None)
        dados.setdefault("id_mensagem_consulta", None)
        return dados
    except Exception:
        return estado_padrao()

def salvar_estado(dados=None):
    dados = dados if dados is not None else estado
    try:
        os.makedirs(os.path.dirname(ARQUIVO_ESTADO), exist_ok=True)
        arquivo_temporario = ARQUIVO_ESTADO + ".tmp"
        with open(arquivo_temporario, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=4)
        os.replace(arquivo_temporario, ARQUIVO_ESTADO)
    except OSError as erro:
        print(f"❌ Erro ao salvar estado: {erro}")

estado = carregar_estado()

# =========================================================
# DATAS E TEMPO
# =========================================================

def formatar_tempo(segundos_totais):
    if segundos_totais <= 0:
        return "🔴 Nascendo agora!"
    horas = int(segundos_totais // 3600)
    minutos = int((segundos_totais % 3600) // 60)
    segundos = int(segundos_totais % 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

def proxima_data_boss(dados_boss, agora):
    nome, horario, dias, mapa, coords, emoji, pontos = dados_boss
    hora, minuto = map(int, horario.split(":"))
    for deslocamento in range(8):
        data = agora.date() + timedelta(days=deslocamento)
        if dias is not None and data.weekday() not in dias:
            continue
        horario_boss = TIMEZONE.localize(datetime(data.year, data.month, data.day, hora, minuto))
        if horario_boss >= agora:
            return horario_boss
    return None

# =========================================================
# EMBEDS
# =========================================================

def criar_embed_agenda_detalhada(agora):
    weekday_atual = agora.weekday()
    embed = discord.Embed(
        title="🛡️ HORÁRIOS DE BOSSES E PONTUAÇÃO",
        description="━━━━━━━━━━━━━━━━━━━━",
        color=0x9B59B6,
    )
    encontrou_algum = False
    for chave, dados_boss in BOSSES.items():
        nome, horario, dias, mapa, coords, emoji, pontos = dados_boss
        if dias is not None and weekday_atual not in dias:
            continue

        proxima_ocorrencia = proxima_data_boss(dados_boss, agora)
        if proxima_ocorrencia is None:
            continue
        diferenca = (proxima_ocorrencia - agora).total_seconds()
        tempo_formatado = formatar_tempo(diferenca)
        
        if diferenca <= 600:
            status_icone = "🔥"
        elif diferenca <= 1800:
            status_icone = "⚠️"
        else:
            status_icone = "⏳"

        dia_texto = f"📅 **Data:** {proxima_ocorrencia.strftime('%d/%m/%Y')}\n" if proxima_ocorrencia.date() != agora.date() else ""
        
        texto_campo = (
            f"📍 **Mapa:** {mapa}\n"
            f"⏰ **Horário:** {horario}\n"
            f"{dia_texto}"
            f"📌 **Coords:** `{coords}`\n"
            f"🏆 **Vale:** `{pontos} pontos`\n"
            f"{status_icone} **Faltam:** `{tempo_formatado}`\n"
            f"────────────────────────"
        )
        embed.add_field(name=f"{emoji} {nome}", value=texto_campo, inline=False)
        encontrou_algum = True

    if not encontrou_algum:
        embed.description = "Nenhum boss programado para hoje."
    embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━\n*Fique atento aos horários e prepare-se para disputar os bosses!*", inline=False)
    return embed

def criar_embed_ranking():
    embed = discord.Embed(
        title="🏆 RANKING GERAL ATUALIZADO DA GUILDA",
        description="Placar geral somando todos os pontos acumulados por cada membro.",
        color=0xF1C40F,
    )
    ranking_atual = estado.get("ranking", {})
    if not ranking_atual:
        embed.add_field(name="📊 Placar Vazio", value="Ainda não há pontuações registadas.", inline=False)
    else:
        ranking_ordenado = sorted(ranking_atual.items(), key=lambda item: item[1], reverse=True)
        linhas = []
        for posicao, (membro, pontos) in enumerate(ranking_ordenado, start=1):
            medalha = "🥇" if posicao == 1 else "🥈" if posicao == 2 else "🥉" if posicao == 3 else f"`#{posicao}`"
            linhas.append(f"{medalha} **{membro}** — `{pontos} pts`")
        
        bloco_atual = ""
        for linha in linhas:
            if len(bloco_atual) + len(linha) + 1 > 1024:
                embed.add_field(name="🏅 Placar (continuação)", value=bloco_atual, inline=False)
                bloco_atual = ""
            bloco_atual += linha + "\n"
        if bloco_atual:
            embed.add_field(name="🏅 Placar Completo", value=bloco_atual, inline=False)
    embed.set_footer(text=f"Atualizado automaticamente • Total de membros: {len(ranking_atual)}")
    return embed

def criar_embed_consulta():
    embed = discord.Embed(
        title="🛡️ BOT-TERROR | CENTRAL DE CONSULTA DE PONTOS",
        description="Clique no botão abaixo para verificar a sua pontuação e posição atual no ranking instantaneamente!\n\n⭐ **Consulta Direta:** A resposta aparece apenas para você.",
        color=0x2E8B57
    )
    return embed

# =========================================================
# VIEWS INTERATIVAS
# =========================================================

class ViewConsultaPontos(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⭐ Meus Pontos", style=discord.ButtonStyle.blurple, custom_id="btn_meus_pontos")
    async def meus_pontos(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        usuario = interaction.user.display_name
        ranking = estado.get("ranking", {})
        ranking_ordenado = sorted(ranking.items(), key=lambda item: item[1], reverse=True)
        
        pontos_usuario = ranking.get(usuario, 0)
        posicao_usuario = None
        
        for idx, (membro, pts) in enumerate(ranking_ordenado, start=1):
            if membro == usuario:
                posicao_usuario = idx
                break

        if posicao_usuario:
            resposta = f"📊 **Consulta de Pontuação**\n\n👤 **Membro:** {usuario}\
