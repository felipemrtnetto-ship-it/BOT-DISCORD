import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os

print("🔄 A iniciar o script do bot...")

# ===============================
# CONFIGURAÇÕES
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
intents.message_content = True  # Necessário para ler o comando !abrirlista
intents.guilds = True
bot = discord.Client(intents=intents)

lock = asyncio.Lock()
alertas_enviados_memoria = set()

# ===============================
# BOSSES E PONTUAÇÕES
# ===============================

BOSSES = {
    "blood wizard": ("Blood Wizard", "18:10", None, "Devias (/pvp2)", "159, 32", "🧙‍♂️", 10),
    "crusher skeleton": ("Crusher Skeleton", "19:05", None, "Lorencia", "Spawn aleatório", "💀", 15),
    "selupan": ("Selupan", "20:10", None, "Raklion (após a ponte, /pvp4)", "174, 2027", "🕷️", 15),
    "galia black": ("Galia Black", "20:30", None, "Lost Tower 1 (à esquerda do /move)", "166, 77", "🦇", 15),
    "gwyn": ("Gwyn, o Senhor das Cinzas", "22:10", None, "Dungeon 3", "25, 72", "🔥", 20),
    "hellmaine": ("Hellmaine", "22:30", None, "Aida (/hellmaine)", "115, 100", "🐺", 25),
    "balgass": ("Balgass", "23:00", [2, 5], "Crywolf Fortress", "112, 80 (Somente quartas e sábados)", "👑", 50),
    "yhorm": ("Yhorm", "23:40", None, "/lorencia1", "22, 46", "🛡️", 20),
    "zorlak": ("Zorlak", "01:10", None, "Lorencia", "Spawn aleatório", "⚡", 15),
}

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

    for chave, dados in BOSSES.items():
        nome, horario, dias, mapa, coords, emoji, pontos = dados
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

        embed.add_field(name=f"{emoji} {nome}", value=texto_campo, inline=False)
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

        if len(texto_ranking) > 1024:
            texto_ranking = texto_ranking[:1021] + "..."

        embed.add_field(name="🏅 Placar Completo", value=texto_ranking, inline=False)

    embed.set_footer(text="Atualizado em tempo real • Total de membros pontuados: " + str(len(ranking_atual)))
    return embed

# ===============================
# VIEW COM BOTÃO DE PRESENÇA
# ===============================

class ViewPresenca(discord.ui.View):
    def __init__(self, nome_boss, pontos):
        super().__init__(timeout=900)  # Expira em 15 minutos
        self.nome_boss = nome_boss
        self.pontos = pontos
        self.participantes = set()

    @discord.ui.button(label="✅ Registrar Presença", style=discord.ButtonStyle.green, custom_id="registrar_presenca")
    async def registrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Evita o erro de timeout do Discord instantaneamente
        await interaction.response.defer(ephemeral=True)

        nome_usuario = interaction.user.display_name
        
        if nome_usuario in self.participantes:
            await interaction.followup.send("⚠️ Você já registou presença neste boss!", ephemeral=True)
            return

        self.participantes.add(nome_usuario)

        # Atualiza os pontos no ranking global
        ranking = estado.get("ranking", {})
        ranking[nome_usuario] = ranking.get(nome_usuario, 0) + self.pontos
        estado["ranking"] = ranking
        salvar_estado(estado)

        lista_nomes = "\n".join([f"• {p}" for p in self.participantes])
        if not lista_nomes:
            lista_nomes = "Nenhum participante ainda."

        # Atualiza o embed de forma segura sem erros de índice
        embed = interaction.message.embeds[0]
        embed.clear_fields()
        embed.add_field(name="⏱️ Status", value="Lista aberta! Fecha em 15 minutos.", inline=False)
        embed.add_field(name=f"👥 Participantes ({len(self.participantes)})", value=lista_nomes, inline=False)
        
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(f"🎉 Presença registada com sucesso! +{self.pontos} pontos.", ephemeral=True)

# ===============================
# COMANDO MANUAL PARA ABRIR LISTA
# ===============================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    conteudo = message.content.lower().strip()

    if conteudo.startswith("!abrirlista"):
        partes = message.content.split(maxsplit=1)
        if len(partes) < 2:
            await message.channel.send("⚠️ Uso correto: `!abrirlista crusher`")
            return

        termo_busca = partes[1].strip().lower()
        boss_encontrado = None

        for chave, dados in BOSSES.items():
            if termo_busca in chave or any(termo in chave for termo in termo_busca.split()):
                boss_encontrado = dados
                break

        if not boss_encontrado:
            await message.channel.send("❌ Boss não encontrado! Verifique o nome.")
            return

        nome, horario
