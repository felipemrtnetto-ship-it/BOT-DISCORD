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
# VIEW COM BOTÃO DE PRESENÇA (BLINDADA CONTRA TIMEOUT)
# ===============================

class ViewPresenca(discord.ui.View):
    def __init__(self, nome_boss, pontos):
        super().__init__(timeout=900)  # Expira em 15 minutos
        self.nome_boss = nome_boss
        self.pontos = pontos
        self.participantes = set()

    @discord.ui.button(label="✅ Registrar Presença", style=discord.ButtonStyle.green, custom_id="registrar_presenca")
    async def registrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # A resposta 'defer' evita instantaneamente o erro de "O aplicativo não respondeu a tempo"
        await interaction.response.defer(ephemeral=True)

        nome_usuario = interaction.user.display_name
        
        if nome_usuario in self.participantes:
            await interaction.followup.send("⚠️ Você já registou presença neste boss!", ephemeral=True)
            return

        self.participantes.add(nome_usuario)

        # Atualiza o ranking global
        ranking = estado.get("ranking", {})
        ranking[nome_usuario] = ranking.get(nome_usuario, 0) + self.pontos
        estado["ranking"] = ranking
        salvar_estado(estado)

        lista_nomes = "\n".join([f"• {p}" for p in self.participantes])
        if not lista_nomes:
            lista_nomes = "Nenhum participante ainda."

        embed = interaction.message.embeds[0]
        embed.set_field_at(
            index=2,
            name=f"👥 Participantes ({len(self.participantes)})",
            value=lista_nomes,
            inline=False
        )
        
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

        nome, horario, dias, mapa, coords, emoji, pontos = boss_encontrado

        embed = discord.Embed(
            title=f"🔥 LISTA ABERTA: {emoji} {nome} 🔥",
            description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} (`{coords}`)\n🏆 **Vale:** {pontos} pontos\n\n*Clique no botão abaixo para registrar a sua presença!*",
            color=0x2ecc71
        )
        embed.add_field(name="⏱️ Status", value="Lista aberta! Fecha em 15 minutos.", inline=False)
        embed.add_field(name=f"👥 Participantes (0)", value="Nenhum participante ainda.", inline=False)

        view = ViewPresenca(nome, pontos)
        msg = await message.channel.send(content="@everyone", embed=embed, view=view, allowed_mentions=discord.AllowedMentions(everyone=True))
        
        # Apaga automaticamente após 15 minutos (900 segundos)
        asyncio.create_task(apagar_mensagem_depois(msg, 900))

async def apagar_mensagem_depois(mensagem, segundos):
    await asyncio.sleep(segundos)
    try:
        await mensagem.delete()
    except Exception:
        pass

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

        # 1. ATUALIZAÇÃO DO PAINEL DE HORÁRIOS
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
                        if m.author == bot.user and m.embeds and m.embeds[0].title and "HORÁRIOS DE BOSSES" in m.embeds[0].title:
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

        # 1.1 ATUALIZAÇÃO DO RANKING GERAL
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
                        if m.author == bot.user and m.embeds and m.embeds[0].title and "RANKING GERAL" in m.embeds[0].title:
                            msg_ranking = m
                            break
                except Exception:
                    pass

            if msg_ranking:
                try:
                    await msg_ranking.edit(embed=embed_ranking)
                except discord.HTTPException:
                    pass
            else:
                nova_msg_rank = await canal_ranking.send(embed=embed_ranking)
                estado["id_mensagem_ranking"] = nova_msg_rank.id
                salvar_estado(estado)

        # 2. CANAL DE ALERTAS (10 MINUTOS ANTES)
        canal_alertas = bot.get_channel(CANAL_ALERTAS_ID)
        if canal_alertas:
            for chave, dados in BOSSES.items():
                nome, horario, dias, mapa, coords, emoji, pontos = dados

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
