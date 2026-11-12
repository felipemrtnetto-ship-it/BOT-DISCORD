import discord
from discord.ext import tasks
import asyncio
import pytz
from datetime import datetime, timedelta
import json
import os

print("🔄 A iniciar o script do bot...")

# =========================================================
# CONFIGURAÇÕES
# =========================================================

TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError(
        "TOKEN ou DISCORD_TOKEN não configurado nas variáveis de ambiente do Railway."
    )

CANAL_PAINEL_ID = 1570446068490043442
CANAL_ALERTAS_ID = 1570454121922822265
CANAL_RANKING_ID = 1570446068490043442

TIMEZONE = pytz.timezone("America/Sao_Paulo")
ARQUIVO_ESTADO = "estado.json"

# O bot precisa da intenção Message Content ativada também
# no Discord Developer Portal.
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = discord.Client(intents=intents)

lock = asyncio.Lock()
alertas_enviados_memoria = set()
ultima_mensagem_lista = None


# =========================================================
# BOSSES E PONTUAÇÕES
# dias=None significa todos os dias.
# weekday(): segunda=0, terça=1, quarta=2, quinta=3,
# sexta=4, sábado=5, domingo=6.
# =========================================================

BOSSES = {
    "blood wizard": (
        "Blood Wizard", "18:10", None,
        "Devias (/pvp2)", "159, 32", "🧙‍♂️", 10
    ),
    "crusher skeleton": (
        "Crusher Skeleton", "19:05", None,
        "Lorencia", "Spawn aleatório", "💀", 15
    ),
    "selupan": (
        "Selupan", "20:10", None,
        "Raklion (após a ponte, /pvp4)", "174, 2027", "🕷️", 15
    ),
    "galia black": (
        "Galia Black", "20:30", None,
        "Lost Tower 1 (à esquerda do /move)", "166, 77", "🦇", 15
    ),
    "gwyn": (
        "Gwyn, o Senhor das Cinzas", "22:10", None,
        "Dungeon 3", "25, 72", "🔥", 20
    ),
    "hellmaine": (
        "Hellmaine", "22:30", None,
        "Aida (/hellmaine)", "115, 100", "🐺", 25
    ),
    "balgass": (
        "Balgass", "23:00", [2, 5],
        "Crywolf Fortress", "112, 80 (Somente quartas e sábados)", "👑", 50
    ),
    "yhorm": (
        "Yhorm", "23:40", None,
        "/lorencia1", "22, 46", "🛡️", 20
    ),
    "zorlak": (
        "Zorlak", "01:10", None,
        "Lorencia", "Spawn aleatório", "⚡", 15
    ),
}


# =========================================================
# ESTADO E PERSISTÊNCIA
# =========================================================

def estado_padrao():
    return {
        "ranking": {},
        "id_mensagem_painel": None,
        "id_mensagem_ranking": None,
    }


def carregar_estado():
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

        if not isinstance(dados["ranking"], dict):
            dados["ranking"] = {}

        return dados

    except (json.JSONDecodeError, OSError) as erro:
        print(f"⚠️ Não foi possível carregar {ARQUIVO_ESTADO}: {erro}")
        return estado_padrao()


def salvar_estado(dados=None):
    dados = dados if dados is not None else estado

    try:
        arquivo_temporario = ARQUIVO_ESTADO + ".tmp"

        with open(arquivo_temporario, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=4)

        os.replace(arquivo_temporario, ARQUIVO_ESTADO)

    except OSError as erro:
        print(f"❌ Erro ao salvar estado: {erro}")


estado = carregar_estado()


# =========================================================
# FUNÇÕES DE DATA E TEMPO
# =========================================================

def formatar_tempo(segundos_totais):
    if segundos_totais <= 0:
        return "🔴 Nascendo agora!"

    horas = int(segundos_totais // 3600)
    minutos = int((segundos_totais % 3600) // 60)
    segundos = int(segundos_totais % 60)

    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def proxima_data_boss(dados_boss, agora):
    """Retorna a próxima ocorrência válida do boss, considerando os dias."""
    nome, horario, dias, mapa, coords, emoji, pontos = dados_boss
    hora, minuto = map(int, horario.split(":"))

    for deslocamento in range(8):
        data = agora.date() + timedelta(days=deslocamento)

        if dias is not None and data.weekday() not in dias:
            continue

        horario_boss = TIMEZONE.localize(
            datetime(data.year, data.month, data.day, hora, minuto)
        )

        if horario_boss >= agora:
            return horario_boss

    return None


# =========================================================
# EMBED DO PAINEL DE HORÁRIOS
# =========================================================

def criar_embed_agenda_detalhada(agora):
    embed = discord.Embed(
        title="🛡️ HORÁRIOS DE BOSSES E PONTUAÇÃO",
        description="━━━━━━━━━━━━━━━━━━━━",
        color=0x9B59B6,
    )

    encontrou_algum = False

    for chave, dados_boss in BOSSES.items():
        nome, horario, dias, mapa, coords, emoji, pontos = dados_boss

        proxima_ocorrencia = proxima_data_boss(dados_boss, agora)
        if proxima_ocorrencia is None:
            continue

        diferenca = (proxima_ocorrencia - agora).total_seconds()
        tempo_formatado = formatar_tempo(diferenca)
        status_icone = "🔥" if diferenca <= 600 else "⏳"

        dia_texto = ""
        if proxima_ocorrencia.date() != agora.date():
            dia_texto = (
                f"📅 **Data:** {proxima_ocorrencia.strftime('%d/%m/%Y')}\n"
            )

        texto_campo = (
            f"📍 **Mapa:** {mapa}\n"
            f"⏰ **Horário:** {horario}\n"
            f"{dia_texto}"
            f"📌 **Coords:** `{coords}`\n"
            f"🏆 **Vale:** `{pontos} pontos`\n"
            f"{status_icone} **Faltam:** `{tempo_formatado}`\n"
            f"────────────────────────"
        )

        embed.add_field(
            name=f"{emoji} {nome}",
            value=texto_campo,
            inline=False,
        )
        encontrou_algum = True

    if not encontrou_algum:
        embed.description = "Nenhum boss programado."

    embed.add_field(
        name="\u200b",
        value=(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*Fique atento aos horários e prepare-se para disputar os bosses!*"
        ),
        inline=False,
    )

    embed.set_footer(text="Painel atualizado automaticamente")
    return embed


# =========================================================
# EMBED DO RANKING
# =========================================================

def criar_embed_ranking():
    embed = discord.Embed(
        title="🏆 RANKING GERAL ATUALIZADO DA GUILDA",
        description=(
            "Placar geral somando todos os pontos acumulados por cada membro."
        ),
        color=0xF1C40F,
    )

    ranking_atual = estado.get("ranking", {})

    if not ranking_atual:
        embed.add_field(
            name="📊 Placar Vazio",
            value="Ainda não há pontuações registadas.",
            inline=False,
        )
    else:
        ranking_ordenado = sorted(
            ranking_atual.items(),
            key=lambda item: item[1],
            reverse=True,
        )

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

        # O Discord limita o valor de cada campo a 1024 caracteres.
        blocos = []
        bloco_atual = ""

        for linha in linhas:
            linha_com_quebra = linha + "\n"

            if len(bloco_atual) + len(linha_com_quebra) > 1024:
                blocos.append(bloco_atual)
                bloco_atual = ""

            bloco_atual += linha_com_quebra

        if bloco_atual:
            blocos.append(bloco_atual)

        for indice, bloco in enumerate(blocos):
            nome_campo = (
                "🏅 Placar Completo"
                if indice == 0
                else f"🏅 Placar (continuação {indice + 1})"
            )
            embed.add_field(name=nome_campo, value=bloco, inline=False)

    embed.set_footer(
        text=(
            "Atualizado automaticamente • Total de membros pontuados: "
            + str(len(ranking_atual))
        )
    )
    return embed


async def atualizar_ranking():
    canal = bot.get_channel(CANAL_RANKING_ID)
    if canal is None:
        try:
            canal = await bot.fetch_channel(CANAL_RANKING_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            print("⚠️ Não foi possível acessar o canal do ranking.")
            return

    embed = criar_embed_ranking()
    mensagem = None
    mensagem_id = estado.get("id_mensagem_ranking")

    if mensagem_id:
        try:
            mensagem = await canal.fetch_message(mensagem_id)
        except discord.NotFound:
            mensagem = None
        except discord.HTTPException as erro:
            print(f"⚠️ Erro ao buscar mensagem do ranking: {erro}")

    if mensagem:
        try:
            await mensagem.edit(embed=embed)
        except discord.HTTPException as erro:
            print(f"⚠️ Erro ao atualizar ranking: {erro}")
        return

    try:
        async for msg in canal.history(limit=20):
            if (
                msg.author == bot.user
                and msg.embeds
                and msg.embeds[0].title
                and "RANKING GERAL ATUALIZADO" in msg.embeds[0].title
            ):
                mensagem = msg
                break

        if mensagem:
            await mensagem.edit(embed=embed)
        else:
            mensagem = await canal.send(embed=embed)

        estado["id_mensagem_ranking"] = mensagem.id
        salvar_estado()

        if not mensagem.pinned:
            try:
                await mensagem.pin()
            except (discord.Forbidden, discord.HTTPException):
                pass

    except discord.HTTPException as erro:
        print(f"❌ Não foi possível publicar o ranking: {erro}")


# =========================================================
# VIEW COM BOTÃO DE PRESENÇA
# =========================================================

class ViewPresenca(discord.ui.View):
    def __init__(self, nome_boss, pontos):
        super().__init__(timeout=900)
        self.nome_boss = nome_boss
        self.pontos = pontos
        self.participantes = set()

    @discord.ui.button(
        label="✅ Registrar Presença",
        style=discord.ButtonStyle.green,
        custom_id="registrar_presenca",
    )
    async def registrar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.defer(ephemeral=True)

        usuario = interaction.user.display_name
        chave_usuario = str(interaction.user.id)

        if usuario in self.participantes:
            await interaction.followup.send(
                "⚠️ Você já registou presença neste boss!",
                ephemeral=True,
            )
            return

        self.participantes.add(usuario)

        async with lock:
            ranking = estado.get("ranking", {})
            ranking[usuario] = int(ranking.get(usuario, 0)) + self.pontos
            estado["ranking"] = ranking
            salvar_estado()

        nomes = "\n".join(
            f"• {participante}" for participante in sorted(self.participantes)
        )

        # Evita ultrapassar o limite de caracteres de um campo do Discord.
        if len(nomes) > 1024:
            nomes = nomes[:1021] + "..."

        try:
            embed = interaction.message.embeds[0]
            embed.clear_fields()
            embed.add_field(
                name="⏱️ Status",
                value="Lista aberta! Fecha em 15 minutos.",
                inline=False,
            )
            embed.add_field(
                name=f"👥 Participantes ({len(self.participantes)})",
                value=nomes or "Nenhum participante ainda.",
                inline=False,
            )

            await interaction.message.edit(embed=embed, view=self)
            await atualizar_ranking()

            await interaction.followup.send(
                f"🎉 Presença registada com sucesso! +{self.pontos} pontos.",
                ephemeral=True,
            )

        except discord.HTTPException as erro:
            print(f"⚠️ Erro ao atualizar a lista de presença: {erro}")
            await interaction.followup.send(
                "A pontuação foi registada, mas não consegui atualizar a mensagem.",
                ephemeral=True,
            )


# =========================================================
# APAGAR LISTA DEPOIS DE 15 MINUTOS
# =========================================================

async def apagar_mensagem_depois(mensagem, segundos):
    global ultima_mensagem_lista

    await asyncio.sleep(segundos)

    try:
        await mensagem.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

    if ultima_mensagem_lista and ultima_mensagem_lista.id == mensagem.id:
        ultima_mensagem_lista = None


# =========================================================
# COMANDOS DE TEXTO: !abrirlista e !fechar
# =========================================================

@bot.event
async def on_message(message):
    global ultima_mensagem_lista

    if message.author.bot:
        return

    conteudo = message.content.lower().strip()

    if conteudo == "!fechar":
        if ultima_mensagem_lista:
            try:
                await ultima_mensagem_lista.delete()
                ultima_mensagem_lista = None
                await message.channel.send("🔒 Lista encerrada com sucesso!")
            except discord.NotFound:
                ultima_mensagem_lista = None
                await message.channel.send("⚠️ A lista já havia sido encerrada.")
            except (discord.Forbidden, discord.HTTPException):
                await message.channel.send(
                    "⚠️ Não foi possível apagar a lista ativa."
                )
        else:
            await message.channel.send(
                "⚠️ Nenhuma lista ativa registada recentemente para fechar."
            )
        return

    if conteudo.startswith("!abrirlista"):
        partes = message.content.split(maxsplit=1)

        if len(partes) < 2:
            await message.channel.send(
                "⚠️ Uso correto: `!abrirlista crusher`"
            )
            return

        termo_busca = partes[1].strip().lower()
        boss_encontrado = None

        for chave, dados_boss in BOSSES.items():
            if termo_busca == chave or termo_busca in chave:
                boss_encontrado = dados_boss
                break

        if not boss_encontrado:
            # Busca também por palavras individuais do nome digitado.
            palavras = termo_busca.split()
            for chave, dados_boss in BOSSES.items():
                if any(palavra in chave for palavra in palavras):
                    boss_encontrado = dados_boss
                    break

        if not boss_encontrado:
            await message.channel.send(
                "❌ Boss não encontrado! Verifique o nome."
            )
            return

        nome, horario, dias, mapa, coords, emoji, pontos = boss_encontrado

        embed = discord.Embed(
            title=f"🔥 LISTA ABERTA: {emoji} {nome} 🔥",
            description=(
                f"⏰ **Horário:** {horario}\n"
                f"📍 **Mapa:** {mapa} (`{coords}`)\n"
                f"🏆 **Vale:** {pontos} pontos\n\n"
                "*Clique no botão abaixo para registrar a sua presença!*"
            ),
            color=0x2ECC71,
        )

        embed.add_field(
            name="⏱️ Status",
            value="Lista aberta! Fecha em 15 minutos.",
            inline=False,
        )
        embed.add_field(
            name="👥 Participantes (0)",
            value="Nenhum participante ainda.",
            inline=False,
        )

        view = ViewPresenca(nome, pontos)

        try:
            mensagem = await message.channel.send(
                content="@everyone",
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )

            ultima_mensagem_lista = mensagem
            asyncio.create_task(apagar_mensagem_depois(mensagem, 900))

        except discord.Forbidden:
            await message.channel.send(
                "❌ Não tenho permissão para enviar a lista ou mencionar @everyone."
            )
        except discord.HTTPException as erro:
            print(f"❌ Erro ao abrir lista: {erro}")
            await message.channel.send(
                "❌ Não foi possível abrir a lista neste momento."
            )


# =========================================================
# VERIFICAÇÃO ANTI-DUPLICIDADE DOS ALERTAS
# =========================================================

async def alerta_ja_postado_recentemente(canal, nome_boss):
    try:
        limite_tempo = datetime.now(pytz.utc) - timedelta(minutes=15)

        async for mensagem in canal.history(
            limit=30,
            after=limite_tempo,
        ):
            if mensagem.author == bot.user and mensagem.embeds:
                titulo = mensagem.embeds[0].title or ""
                if nome_boss.lower() in titulo.lower():
                    return True

    except (discord.Forbidden, discord.HTTPException) as erro:
        print(f"⚠️ Não foi possível verificar alertas anteriores: {erro}")

    return False


async def enviar_alerta_boss(dados_boss, horario_boss):
    nome, horario, dias, mapa, coords, emoji, pontos = dados_boss

    canal = bot.get_channel(CANAL_ALERTAS_ID)
    if canal is None:
        try:
            canal = await bot.fetch_channel(CANAL_ALERTAS_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            print("⚠️ Não foi possível acessar o canal de alertas.")
            return

    chave_alerta = f"{nome}:{horario_boss.strftime('%Y%m%d%H%M')}"

    if chave_alerta in alertas_enviados_memoria:
        return

    if await alerta_ja_postado_recentemente(canal, nome):
        alertas_enviados_memoria.add(chave_alerta)
        return

    embed = discord.Embed(
        title=f"🚨 BOSS EM 10 MINUTOS: {emoji} {nome}",
        description=(
            f"⏰ **Horário:** {horario}\n"
            f"📍 **Mapa:** {mapa}\n"
            f"📌 **Coordenadas:** `{coords}`\n"
            f"🏆 **Pontuação:** `{pontos} pontos`\n\n"
            "**Preparem-se! O boss está chegando.**"
        ),
        color=0xE74C3C,
    )

    try:
        await canal.send(
            content="@everyone",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        alertas_enviados_memoria.add(chave_alerta)
        print(f"📢 Alerta enviado: {nome}")

    except discord.Forbidden:
        print(f"❌ Sem permissão para enviar alerta de {nome}.")
    except discord.HTTPException as erro:
        print(f"❌ Erro ao enviar alerta de {nome}: {erro}")


# =========================================================
# LOOP PRINCIPAL
# =========================================================

@tasks.loop(seconds=5)
async def verificar_boss():
    async with lock:
        agora = datetime.now(TIMEZONE)

        # -------------------------------------------------
        # ATUALIZAR PAINEL DE HORÁRIOS
        # -------------------------------------------------
        canal_painel = bot.get_channel(CANAL_PAINEL_ID)

        if canal_painel is None:
            try:
                canal_painel = await bot.fetch_channel(CANAL_PAINEL_ID)
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                canal_painel = None

        if canal_painel:
            embed_painel = criar_embed_agenda_detalhada(agora)
            mensagem_id = estado.get("id_mensagem_painel")
            mensagem_painel = None

            if mensagem_id:
                try:
                    mensagem_painel = await canal_painel.fetch_message(
                        mensagem_id
                    )
                except discord.NotFound:
                    mensagem_painel = None
                except discord.HTTPException as erro:
                    print(f"⚠️ Erro ao buscar painel: {erro}")

            if not mensagem_painel:
                try:
                    async for mensagem in canal_painel.history(limit=20):
                        if (
                            mensagem.author == bot.user
                            and mensagem.embeds
                            and mensagem.embeds[0].title
                            and "HORÁRIOS DE BOSSES"
                            in mensagem.embeds[0].title
                        ):
                            mensagem_painel = mensagem
                            break
                except (discord.Forbidden, discord.HTTPException):
                    pass

            try:
                if mensagem_painel:
                    await mensagem_painel.edit(embed=embed_painel)
                else:
                    nova_mensagem = await canal_painel.send(
                        embed=embed_painel
                    )
                    estado["id_mensagem_painel"] = nova_mensagem.id
                    salvar_estado()

            except discord.HTTPException as erro:
                print(f"⚠️ Erro ao atualizar painel: {erro}")

        # -------------------------------------------------
        # ATUALIZAR / CRIAR RANKING
        # -------------------------------------------------
        # A atualização periódica também recupera o ranking
        # caso a mensagem tenha sido apagada manualmente.
        await atualizar_ranking()

        # -------------------------------------------------
        # VERIFICAR HORÁRIOS E ENVIAR ALERTAS
        # O alerta é enviado quando faltam até 10 minutos.
        # -------------------------------------------------
        for chave, dados_boss in BOSSES.items():
            proxima_ocorrencia = proxima_data_boss(dados_boss, agora)

            if proxima_ocorrencia is None:
                continue

            segundos_restantes = (
                proxima_ocorrencia - agora
            ).total_seconds()

            if 0 <= segundos_restantes <= 600:
                await enviar_alerta_boss(
                    dados_boss,
                    proxima_ocorrencia,
                )


@verificar_boss.before_loop
async def antes_de_verificar_boss():
    await bot.wait_until_ready()


# =========================================================
# EVENTOS DO BOT
# =========================================================

@bot.event
async def on_ready():
    print("---------------------------------------")
    print(f"✅ Bot conectado como: {bot.user}")
    print(f"🕒 Fuso horário: {TIMEZONE}")
    print("---------------------------------------")

    if not verificar_boss.is_running():
        verificar_boss.start()


@bot.event
async def on_disconnect():
    print("⚠️ Bot desconectado. O Discord tentará reconectar.")


@bot.event
async def on_resumed():
    print("🔄 Sessão do Discord retomada.")


# =========================================================
# INICIAR BOT
# =========================================================

bot.run(TOKEN)