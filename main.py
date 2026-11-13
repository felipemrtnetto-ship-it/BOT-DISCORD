import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os
import time

print("🔄 A iniciar o bot definitivo (ID do Discord + Anti-Rate Limit)...")

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
intents.members = True

class MeuBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = asyncio.Lock()

    async def setup_hook(self):
        self.add_view(ViewConsultaPontos())
        if not verificar_boss.is_running():
            verificar_boss.start()
        print("⚙️ setup_hook executado: Views e loops iniciados com sucesso.")

    async def on_ready(self):
        print(f"---------------------------------------")
        print(f"✅ Bot conectado com sucesso como: {self.user}")
        print(f"🕒 Fuso horário: {TIMEZONE}")
        print(f"---------------------------------------")
        await migrar_ranking_para_ids(self)

bot = MeuBot(intents=intents)

alertas_10min_memoria = set()
listas_5min_memoria = set()
ultima_mensagem_lista = None
tempo_inicio_bot = time.time()
ultimo_hash_ranking = ""

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

async def migrar_ranking_para_ids(client):
    ranking = estado.get("ranking", {})
    novo_ranking = {}
    alterado = False

    for chave, pontos in ranking.items():
        if chave.isdigit():
            novo_ranking[chave] = pontos
            continue

        encontrou = False
        for guild in client.guilds:
            membro = discord.utils.find(lambda m: m.display_name.lower() == chave.lower() or m.name.lower() == chave.lower(), guild.members)
            if membro:
                novo_ranking[str(membro.id)] = pontos
                encontrou = True
                alterado = True
                print(f"🔄 Migrado com sucesso: '{chave}' -> ID {membro.id} ({membro.display_name})")
                break
        
        if not encontrou:
            novo_ranking[chave] = pontos

    if alterado:
        estado["ranking"] = novo_ranking
        salvar_estado()
        print("✅ Migração de ranking concluída e salva com sucesso!")

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

async def obter_nome_membro_async(client, user_id_str):
    if user_id_str.isdigit():
        for guild in client.guilds:
            membro = guild.get_member(int(user_id_str))
            if membro:
                return membro.display_name
            try:
                membro = await guild.fetch_member(int(user_id_str))
                if membro:
                    return membro.display_name
            except Exception:
                continue
    return user_id_str

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

async def criar_embed_ranking_async(client):
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
        for posicao, (user_id_str, pontos) in enumerate(ranking_ordenado, start=1):
            nome_exibicao = await obter_nome_membro_async(client, user_id_str)

            if posicao == 1:
                medalha = "🥇"
            elif posicao == 2:
                medalha = "🥈"
            elif posicao == 3:
                medalha = "🥉"
            else:
                medalha = f"`#{posicao}`"
            
            linhas.append(f"{medalha} **{nome_exibicao}** — `{pontos} pts`")
        
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

        user_id_str = str(interaction.user.id)
        usuario = interaction.user.display_name
        ranking = estado.get("ranking", {})
        
        pontos_usuario = ranking.get(user_id_str, ranking.get(usuario, 0))
        ranking_ordenado = sorted(ranking.items(), key=lambda item: item[1], reverse=True)
        posicao_usuario = None
        
        for idx, (uid_ou_nome, pts) in enumerate(ranking_ordenado, start=1):
            if uid_ou_nome == user_id_str or uid_ou_nome.lower() == usuario.lower():
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
        self.participantes_ids = set()

    @discord.ui.button(label="✅ Registrar Presença", style=discord.ButtonStyle.green, custom_id="registrar_presenca")
    async def registrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        user_id_str = str(interaction.user.id)
        if user_id_str in self.participantes_ids:
            msg = await interaction.followup.send("⚠️ Você já registou presença neste boss!", ephemeral=True)
            asyncio.create_task(apagar_msg_temporaria(msg))
            return

        self.participantes_ids.add(user_id_str)

        async with bot.lock:
            ranking = estado.get("ranking", {})
            ranking[user_id_str] = int(ranking.get(user_id_str, 0)) + self.pontos
            estado["ranking"] = ranking
            salvar_estado()

        nomes_participantes = []
        for uid in sorted(self.participantes_ids):
            nome = await obter_nome_membro_async(interaction.client, uid)
            nomes_participantes.append(f"• {nome}")
        
        nomes = "\n".join(nomes_participantes) or "Nenhum participante ainda."
        if len(nomes) > 1024:
            nomes = nomes[:1021] + "..."

        try:
            embed = interaction.message.embeds[0]
            embed.clear_fields()
            embed.add_field(name="⏱️ Status", value="Lista aberta! Fecha em 15 minutos.", inline=False)
            embed.add_field(name=f"👥 Participantes ({len(self.participantes_ids)})", value=nomes, inline=False)

            await interaction.message.edit(embed=embed, view=self)
            await atualizar_ranking(forcar=True)

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
# ATUALIZAÇÃO SEGURA DE CANAIS (COM ANTI-RATE LIMIT)
# =========================================================

async def atualizar_ranking(forcar=False):
    global ultimo_hash_ranking
    canal = bot.get_channel(CANAL_RANKING_ID)
    if not canal:
        try:
            canal = await bot.fetch_channel(CANAL_RANKING_ID)
        except Exception:
            return

    ranking_atual = estado.get("ranking", {})
    hash_atual = json.dumps(ranking_atual, sort_keys=True)

    if not forcar and hash_atual == ultimo_hash_ranking:
        return

    ultimo_hash_ranking = hash_atual
    embed = await criar_embed_ranking_async(bot)
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
    await asyncio.sleep(segundos)
    
    try:
        await mensagem.delete()
    except Exception:
        pass

    if ultima_mensagem_lista and ultima_mensagem_lista.id == mensagem.id:
        ultima_mensagem_lista = None

    canal = bot.get_channel(CANAL_PRESENCA_ID)
    if not canal:
        return

    nomes_participantes = []
    for uid in sorted(view_presenca.participantes_ids):
        nome = await obter_nome_membro_async(bot, uid)
        nomes_participantes.append(f"• {nome}")

    lista_nomes = "\n".join(nomes_participantes) if nomes_participantes else "Nenhum participante registado."
    if len(lista_nomes) > 1024:
        lista_nomes = lista_nomes[:1021] + "..."

    embed_final = discord.Embed(
        title=f"📋 LISTA DE PARTICIPANTES: {nome_boss}",
        description=f"🔒 **Lista encerrada.** Registo de presenças concluído.\n🏆 **Pontos atribuídos:** `{pontos} pts` por participante.",
        color=0xE74C3C
    )
    embed_final.add_field(name=f"👥 Participantes Confirmados ({len(view_presenca.participantes_ids)})", value=lista_nomes, inline=False)
    embed_final.set_footer(text="Pontuações aplicadas e atualizadas no ranking geral.")

    try:
        await canal.send(embed=embed_final)
    except Exception as e:
        print(f"⚠️ Erro ao enviar painel final de participantes: {e}")

# =========================================================
# COMANDOS DE TEXTO E PAINEL DE CONTROLO
# =========================================================

@bot.event
async def on_message(message):
    global ultima_mensagem_lista
    if message.author.bot:
        return

    conteudo = message.content.strip()
    conteudo_lower = conteudo.lower()

    if conteudo_lower == "!status":
        uptime_segundos = int(time.time() - tempo_inicio_bot)
        horas = uptime_segundos // 3600
        minutos = (uptime_segundos % 3600) // 60
        
        embed_status = discord.Embed(
            title="🛡️ PAINEL DE CONTROLO | BOT-TERROR",
            description="Estado atual dos sistemas do bot na nuvem (Railway):",
            color=0x3498DB
        )
        embed_status.add_field(name="🟢 Estado", value="Online e Operacional", inline=True)
        embed_status.add_field(name="⏱️ Uptime", value=f"{horas}h {minutos}m", inline=True)
        embed_status.add_field(name="🏆 Total Ranqueados", value=f"{len(estado.get('ranking', {}))} membros", inline=True)
        embed_status.add_field(name="📂 Volume Persistente", value="Ativo (`/data/estado.json`)", inline=False)
        embed_status.set_footer(text="Use !comandos para ver a lista de ações disponíveis.")
        await message.channel.send(embed=embed_status)
        return

    if conteudo_lower == "!comandos":
        embed_cmd = discord.Embed(
            title="📜 PAINEL DE GESTÃO - LISTA DE COMANDOS",
            description="Aqui estão todos os comandos administrativos disponíveis:",
            color=0xE67E22
        )
        embed_cmd.add_field(name="⚙️ Controlo & Testes", value=(
            "`!status` - Mostra o painel de controlo e tempo ligado\n"
            "`!forcaratualizar` - Força a atualização imediata de todos os painéis\n"
            "`!ping` - Testa a latência de resposta do bot\n"
            "`!testeboss [nome]` - Força um teste abrindo a lista de um boss"
        ), inline=False)
        embed_cmd.add_field(name="🏆 Gestão de Pontos", value=(
            "`!addpontos [Membro] [Qtde]` - Adiciona pontos a um membro\n"
            "`!tirarpontos [Membro] [Qtde]` - Remove pontos de um membro"
        ), inline=False)
        embed_cmd.add_field(name="⏰ Gestão de Listas", value=(
            "`!abrirlista [boss]` - Abre manualmente a lista de um boss\n"
            "`!fechar` - Fecha a lista de presença ativa"
        ), inline=False)
        await message.channel.send(embed=embed_cmd)
        return

    if conteudo_lower == "!forcaratualizar":
        await atualizar_ranking(forcar=True)
        await garantir_painel_consulta()
        await message.channel.send("🔄 Painéis, ranking e central de consulta atualizados manualmente com sucesso!")
        return

    if conteudo_lower == "!ping":
        latencia = round(bot.latency * 1000)
        await message.channel.send(f"🏓 Pong! Latência de resposta com o Discord: `{latencia}ms`.")
        return

    if conteudo_lower.startswith("!testeboss"):
        partes = conteudo.split(maxsplit=1)
        if len(partes) < 2:
            await message.channel.send("⚠️ Uso correto: `!testeboss crusher`")
            return
        termo = partes[1].strip().lower()
        boss_encontrado = None
        for chave, dados_boss in BOSSES.items():
            if termo in chave:
                boss_encontrado = dados_boss
                break
        if not boss_encontrado:
            await message.channel.send("❌ Boss de teste não encontrado.")
            return
        await abrir_lista_automatica(boss_encontrado)
        await message.channel.send(f"🧪 **[TESTE]** Lista de presença aberta com sucesso para o boss: **{boss_encontrado[0]}**!")
        return

    if conteudo_lower == "!fechar":
        if ultima_mensagem_lista:
            try:
                await ultima_mensagem_lista.delete()
                ultima_mensagem_lista = None
                await message.channel.send("🔒 Lista encerrada manualmente com sucesso!")
            except Exception:
                await message.channel.send("⚠️ Não foi possível apagar a lista ativa.")
        else:
            await message.channel.send("⚠️ Nenhuma lista ativa registada recentemente para fechar.")
        return

    if conteudo_lower.startswith("!abrirlista"):
        partes = conteudo.split(maxsplit=1)
        if len(partes) < 2:
            await message.channel.send("⚠️ Uso correto: `!abrirlista crusher`")
            return

        termo_busca = partes[1].strip().lower()
        boss_encontrado = None

        for chave, dados_boss in BOSSES.items():
            if termo_busca in chave:
                boss_encontrado = dados_boss
                break
        
        if not boss_encontrado:
            for chave, dados_boss in BOSSES.items():
                if any(p in chave for p in termo_busca.split()):
                    boss_encontrado = dados_boss
                    break

        if not boss_encontrado:
            await message.channel.send("❌ Boss não encontrado! Verifique o nome.")
            return

        await abrir_lista_automatica(boss_encontrado)
        return

    if conteudo_lower.startswith("!addpontos"):
        partes = conteudo.split(maxsplit=2)
        if len(partes) < 3:
            await message.channel.send("⚠️ Uso correto: `!addpontos NomeDoMembro 10`")
            return

        membro_alvo_str = partes[1].strip()
        try:
            pontos_a_adicionar = int(partes[2])
        except ValueError:
            await message.channel.send("❌ A quantidade de pontos deve ser um número inteiro.")
            return

        alvo_chave = None
        if message.mentions:
            alvo_chave = str(message.mentions[0].id)
        else:
            encontrado = discord.utils.find(lambda m: m.display_name.lower() == membro_alvo_str.lower() or m.name.lower() == membro_alvo_str.lower(), message.guild.members)
            if encontrado:
                alvo_chave = str(encontrado.id)
            else:
                alvo_chave = membro_alvo_str

        async with bot.lock:
            ranking = estado.get("ranking", {})
            atual = int(ranking.get(alvo_chave, 0))
            ranking[alvo_chave] = atual + pontos_a_adicionar
            estado["ranking"] = ranking
            salvar_estado()

        await atualizar_ranking(forcar=True)
        await message.channel.send(f"✅ Adicionados **{pontos_a_adicionar} pts** para **{membro_alvo_str}**! Total atual: `{ranking[alvo_chave]} pts`.")
        return

    if conteudo_lower.startswith("!tirarpontos"):
        partes = conteudo.split(maxsplit=2)
        if len(partes) < 3:
            await message.channel.send("⚠️ Uso correto: `!tirarpontos NomeDoMembro 10`")
            return

        membro_alvo_str = partes[1].strip()
        try:
            pontos_a_remover = int(partes[2])
        except ValueError:
            await message.channel.send("❌ A quantidade de pontos deve ser um número inteiro.")
            return

        alvo_chave = None
        if message.mentions:
            alvo_chave = str(message.mentions[0].id)
        else:
            encontrado = discord.utils.find(lambda m: m.display_name.lower() == membro_alvo_str.lower() or m.name.lower() == membro_alvo_str.lower(), message.guild.members)
            if encontrado:
                alvo_chave = str(encontrado.id)
            else:
                alvo_chave = membro_alvo_str

        async with bot.lock:
            ranking = estado.get("ranking", {})
            atual = int(ranking.get(alvo_chave, 0))
            novo_total = max(0, atual - pontos_a_remover)
            ranking[alvo_chave] = novo_total
            estado["ranking"] = ranking
            salvar_estado()

        await atualizar_ranking(forcar=True)
        await message.channel.send(f"🗑️ Removidos **{pontos_a_remover} pts** de **{membro_alvo_str}**! Total atual: `{novo_total} pts`.")
        return

# =========================================================
# LOOP PRINCIPAL UNIFICADO (30 SEG)
# =========================================================

@tasks.loop(seconds=30)
async def verificar_boss():
    async with bot.lock:
        agora = datetime.now(TIMEZONE)
        weekday_atual = agora.weekday()

        canal_painel = bot.get_channel(CANAL_PAINEL_ID)
        if canal_painel:
            embed_painel = criar_embed_agenda_detalhada(agora)
            msg_id = estado.get("id_mensagem_painel")
            msg_painel = None
            
            if msg_id:
                try:
                    msg_painel = await canal_painel.fetch_message(msg_id)
                except Exception:
                    msg_painel = None

            try:
                if msg_painel:
                    await msg_painel.edit(embed=embed_painel)
                else:
                    async for m in canal_painel.history(limit=15):
                        if m.author == bot.user and m.embeds and "HORÁRIOS DE BOSSES" in (m.embeds[0].title or ""):
                            msg_painel = m
                            break
                    
                    if msg_painel:
                        await msg_painel.edit(embed=embed_painel)
                        estado["id_mensagem_painel"] = msg_painel.id
                        salvar_estado()
                    else:
                        nova_msg = await canal_painel.send(embed=embed_painel)
                        estado["id_mensagem_painel"] = nova_msg.id
                        salvar_estado()
            except Exception as e:
                print(f"⚠️ Erro no painel: {e}")

        await atualizar_ranking(forcar=False)
        await garantir_painel_consulta()

        canal_alertas = bot.get_channel(CANAL_ALERTAS_ID)
        
        for chave, dados_boss in BOSSES.items():
            nome, horario, dias, mapa, coords, emoji, pontos = dados_boss
            if dias is not None and weekday_atual not in dias:
                continue

            proxima_ocorrencia = proxima_data_boss(dados_boss, agora)
            if proxima_ocorrencia is None:
                continue

            diferenca = (proxima_ocorrencia - agora).total_seconds()
            data_hoje = agora.strftime('%Y-%m-%d')
            
            chave_alerta_10m = f"{nome}_{horario}_{data_hoje}_10min"
            chave_lista_5m = f"{nome}_{horario}_{data_hoje}_5min_lista"

            if 570 <= diferenca <= 600:
                if chave_alerta_10m not in alertas_10min_memoria:
                    alertas_10min_memoria.add(chave_alerta_10m)
                    if canal_alertas:
                        embed_alerta = discord.Embed(
                            title=f"🔥 BOSS {emoji} {nome} NASCENDO EM BREVE! 🔥",
                            description=(
                                f"⏰ **Horário:** {horario}\n"
                                f"📍 **Mapa:** {mapa}\n"
                                f"📌 **Coordenadas:** `{coords}`\n"
                                f"🏆 **Pontuação:** `{pontos} pontos`\n\n"
                                "*Corram para o local!*"
                            ),
                            color=0xFFA500,
                        )
                        try:
                            await canal_alertas.send(
                                content="@everyone",
                                embed=embed_alerta,
                                allowed_mentions=discord.AllowedMentions(everyone=True),
                            )
                        except Exception as erro:
                            print(f"⚠️ Erro no alerta de 10 min: {erro}")

            if 270 <= diferenca <= 300:
                if chave_lista_5m not in listas_5min_memoria:
                    listas_5min_memoria.add(chave_lista_5m)
                    await abrir_lista_automatica(dados_boss)

if __name__ == "__main__":
    bot.run(TOKEN)
