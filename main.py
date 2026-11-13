import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os
import time

print("🔄 A iniciar o bot com painel de horários limpo (sem carimbo)...")

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
CANAL_CONSULTA_ID = 1570413285214527618 # Canal: 🔍 consultar-pontos

TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "/data/estado.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = discord.Client(intents=intents)

lock = asyncio.Lock()
alertas_10min_memoria = set()
listas_5min_memoria = set()
ultima_mensagem_lista = None
tempo_inicio_bot = time.time()

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
    agora_str = datetime.now(TIMEZONE).strftime('%H:%M:%S')
    embed = discord.Embed(
        title="🏆 RANKING GERAL ATUALIZADO DA GUILDA",
        description=f"Placar geral acumulado de membros.\n\n🕒 **ÚLTIMA ATUALIZAÇÃO:** `{agora_str}`",
        color=0xF1C40F,
    )
    ranking_atual = estado.get("ranking", {})
    if not ranking_atual:
        embed.add_field(name="📊 Placar Vazio", value="Ainda não há pontuações registadas.", inline=False)
    else:
        ranking_ordenado = sorted(ranking_atual.items(), key=lambda item: item[1], reverse=True)
        linhas = []
        for posicao, (membro, pontos) in enumerate(ranking_ordenado, start=1):
            if posicao == 1:
                medalha = "🥇"
            elif posicao == 2:
                medalha = "🥈"
            elif posicao == 3:
                medalha = "🥉"
            else:
                medalha = f"`#{posicao}`"
            
            linhas.append(f"{medalha} **{membro}** — `{pontos} pts`")
        
        bloco_atual = ""
        for linha in linhas:
            if len(bloco_atual) + len(linha) + 1 > 1024:
                embed.add_field(name="🏅 Placar (continuação)", value=bloco_atual, inline=False)
                bloco_atual = ""
            bloco_atual += linha + "\n"
        if bloco_atual:
            embed.add_field(name="🏅 Placar Completo", value=bloco_atual, inline=False)
    
    embed.set_footer(text=f"Total de membros ranqueados: {len(ranking_atual)}")
    return embed

def criar_embed_consulta():
    embed = discord.Embed(
        title="🛡️ BOT-TERROR | CENTRAL DE CONSULTA DE PONTOS",
        description="Clique no botão abaixo para verificar a sua pontuação e posição atual no ranking instantaneamente!\n\n⭐ **Consulta Direta:** A resposta aparece apenas para você e apaga-se automaticamente.",
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
            resposta = f"📊 **Consulta de Pontuação**\n\n👤 **Membro:** {usuario}\n🏆 **Pontos Atuais:** `{pontos_usuario} pts`\n🏅 **Posição no Ranking:** `#{posicao_usuario}`"
        else:
            resposta = f"📊 **Consulta de Pontuação**\n\n👤 **Membro:** {usuario}\n🏆 **Pontos Atuais:** `0 pts`\n🏅 **Posição no Ranking:** `Não ranqueado`"

        msg_enviada = await interaction.followup.send(resposta, ephemeral=True)
        
        async def apagar_depois_de_tempo():
            await asyncio.sleep(60)
            try:
                await msg_enviada.delete()
            except Exception:
                pass

        asyncio.create_task(apagar_depois_de_tempo())


class ViewPresenca(discord.ui.View):
    def __init__(self, nome_boss, pontos):
        super().__init__(timeout=900)
        self.nome_boss = nome_boss
        self.pontos = pontos
        self.participantes = set()

    @discord.ui.button(label="✅ Registrar Presença", style=discord.ButtonStyle.green, custom_id="registrar_presenca")
    async def registrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        usuario = interaction.user.display_name
        if usuario in self.participantes:
            msg = await interaction.followup.send("⚠️ Você já registou presença neste boss!", ephemeral=True)
            asyncio.create_task(apagar_msg_temporaria(msg))
            return

        self.participantes.add(usuario)

        async with lock:
            ranking = estado.get("ranking", {})
            ranking[usuario] = int(ranking.get(usuario, 0)) + self.pontos
            estado["ranking"] = ranking
            salvar_estado()

        nomes = "\n".join(f"• {p}" for p in sorted(self.participantes)) or "Nenhum participante ainda."
        if len(nomes) > 1024:
            nomes = nomes[:1021] + "..."

        try:
            embed = interaction.message.embeds[0]
            embed.clear_fields()
            embed.add_field(name="⏱️ Status", value="Lista aberta! Fecha em 15 minutos.", inline=False)
            embed.add_field(name=f"👥 Participantes ({len(self.participantes)})", value=nomes, inline=False)

            await interaction.message.edit(embed=embed, view=self)
            await atualizar_ranking()

            msg = await interaction.followup.send(f"🎉 Presença registada com sucesso! +{self.pontos} pontos.", ephemeral=True)
            asyncio.create_task(apagar_msg_temporaria(msg))
        except Exception as erro:
            print(f"⚠️ Erro ao atualizar presença: {erro}")
            msg = await interaction.followup.send("Pontuação registada, mas houve uma falha ao atualizar o painel visual.", ephemeral=True)
            asyncio.create_task(apagar_msg_temporaria(msg))

async def apagar_msg_temporaria(msg):
    await asyncio.sleep(15)
    try:
        await msg.delete()
    except Exception:
        pass

# =========================================================
# ATUALIZAÇÃO SEGURA DE CANAIS
# =========================================================

async def atualizar_ranking():
    canal = bot.get_channel(CANAL_RANKING_ID)
    if not canal:
        try:
            canal = await bot.fetch_channel(CANAL_RANKING_ID)
        except Exception:
            return

    embed = criar_embed_ranking()
    mensagem_id = estado.get("id_mensagem_ranking")
    mensagem = None

    if mensagem_id:
        try:
            mensagem = await canal.fetch_message(mensagem_id)
        except Exception:
            mensagem = None

    try:
        if mensagem:
            await mensagem.edit(embed=embed)
        else:
            async for msg in canal.history(limit=15):
                if msg.author == bot.user and msg.embeds and "RANKING GERAL" in (msg.embeds[0].title or ""):
                    mensagem = msg
                    break
            if mensagem:
                await mensagem.edit(embed=embed)
            else:
                mensagem = await canal.send(embed=embed)
            estado["id_mensagem_ranking"] = mensagem.id
            salvar_estado()
    except Exception as erro:
        print(f"⚠️ Erro no ranking: {erro}")

async def garantir_painel_consulta():
    canal = bot.get_channel(CANAL_CONSULTA_ID)
    if not canal:
        try:
            canal = await bot.fetch_channel(CANAL_CONSULTA_ID)
        except Exception:
            return

    embed = criar_embed_consulta()
    view = ViewConsultaPontos()
    mensagem_id = estado.get("id_mensagem_consulta")
    mensagem = None

    if mensagem_id:
        try:
            mensagem = await canal.fetch_message(mensagem_id)
        except Exception:
            mensagem = None

    try:
        if mensagem:
            await mensagem.edit(embed=embed, view=view)
        else:
            async for msg in canal.history(limit=20):
                if msg.author == bot.user and msg.embeds and "CENTRAL DE CONSULTA" in (msg.embeds[0].title or ""):
                    try:
                        await msg.delete()
                    except Exception:
                        pass
            
            mensagem = await canal.send(embed=embed, view=view)
            estado["id_mensagem_consulta"] = mensagem.id
            salvar_estado()
    except Exception as erro:
        print(f"⚠️ Erro no painel de consulta: {erro}")

# =========================================================
# ABERTURA E FECHO DA LISTA DE PRESENÇA
# =========================================================

async def abrir_lista_automatica(dados_boss):
    global ultima_mensagem_lista
    canal = bot.get_channel(CANAL_PRESENCA_ID)
    if not canal:
        return

    nome, horario, dias, mapa, coords, emoji, pontos = dados_boss
    view = ViewPresenca(nome, pontos)

    embed = discord.Embed(
        title=f"🔥 LISTA ABERTA: {emoji} {nome} 🔥",
        description=f"⏰ **Horário:** {horario}\n📍 **Mapa:** {mapa} (`{coords}`)\n🏆 **Vale:** {pontos} pontos\n\n*Clique no botão abaixo para registrar a sua presença!*",
        color=0x2ECC71,
    )
    embed.add_field(name="⏱️ Status", value="Lista aberta! Fecha em 15 minutos.", inline=False)
    embed.add_field(name="👥 Participantes (0)", value="Nenhum participante ainda.", inline=False)

    try:
        mensagem = await canal.send(
            content="@everyone",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        ultima_mensagem_lista = mensagem
        asyncio.create_task(fechar_lista_depois(mensagem, view, nome, pontos, 900))
    except Exception as erro:
        print(f"❌ Erro ao abrir lista automática: {erro}")

async def fechar_lista_depois(mensagem, view_presenca, nome_boss, pontos, segundos):
    global ultima_mensagem_lista
    await asyncio
