import os
import asyncio
import logging
from datetime import datetime, timedelta

import discord
import asyncpg
import pytz
from discord.ext import tasks
from discord.ui import View
from dotenv import load_dotenv

# =====================================================
# BOT-TERROR - CONFIGURAÇÕES
# =====================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

TIMEZONE = pytz.timezone("America/Sao_Paulo")

BOT_NAME = "BOT-TERROR"

# IDs DOS CANAIS
CANAL_PRESENCA_ID = 1561134289595142235
CANAL_PONTOS_ID = 1570234809719070842
CANAL_LOGS_ID = 1570235263853133854

# =====================================================
# HORÁRIOS DOS EVENTOS (ATUALIZADOS)
# =====================================================
eventos = [
    ("Blood Wizard", "18:10", None, 5, "🧙‍♂️"),
    ("Crusher Skeleton", "19:05", None, 5, "💀"),
    ("Necromancer", "19:40", None, 5, "☠️"),
    ("Selupan", "20:10", None, 5, "🦂"),
    ("Galia Black", "20:30", None, 2, "🗡️"),
    ("Skull Reaper", "20:50", None, 5, "👻"),
    ("Gwyn, o Senhor das Cinzas", "22:10", None, 5, "🔥"),
    ("Hellmaine", "22:30", None, 20, "👿"),
    ("Balgass", "23:00", [2, 5], 30, "🧌"), # Quarta (2) e Sábado (5)
    ("Yhorm", "23:40", None, 15, "🐗"),
    ("Zorlak", "01:10", None, 15, "🐉"),
]

# =====================================================
# LOGS
# =====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(BOT_NAME)

# =====================================================
# BANCO DE DADOS
# =====================================================

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ranking (
                user_id BIGINT PRIMARY KEY,
                nick TEXT NOT NULL,
                pontos INTEGER DEFAULT 0
            )
        """)

    logger.info("Banco de dados conectado!")


# =====================================================
# BOTÃO DE PRESENÇA NOS EVENTOS
# =====================================================

class PresencaView(View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Marcar Presença",
        style=discord.ButtonStyle.green,
        custom_id="btn_pres_v3",
        emoji="✅"
    )
    async def marcar_presenca(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not self.bot.lista_ativa:
            await interaction.response.send_message(
                "❌ Nenhuma lista aberta!",
                ephemeral=True
            )
            return

        if interaction.user.id in self.bot.participantes:
            await interaction.response.send_message(
                "⚠️ Você já está na lista!",
                ephemeral=True
            )
            return

        self.bot.participantes[interaction.user.id] = (
            interaction.user.display_name
        )

        await self.bot.atualizar_lista_msg()

        await interaction.response.send_message(
            "✅ Presença confirmada!",
            ephemeral=True
        )


# =====================================================
# BOTÃO DE CONSULTAR PONTOS
# =====================================================

class MeuPerfilView(View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Meus Pontos",
        style=discord.ButtonStyle.blurple,
        custom_id="btn_meus_pontos_v1",
        emoji="⭐"
    )
    async def meus_pontos(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        user_id = interaction.user.id

        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT nick, pontos FROM ranking WHERE user_id = $1",
                    user_id
                )

                if not row:
                    await interaction.response.send_message(
                        "📭 Você ainda não possui pontos registrados no ranking.",
                        ephemeral=True
                    )
                    return

                posicao = await conn.fetchval(
                    """
                    SELECT COUNT(*) + 1 
                    FROM ranking 
                    WHERE pontos > (SELECT pontos FROM ranking WHERE user_id = $1)
                    """,
                    user_id
                )

            pontos = row["pontos"]
            nick = row["nick"]

            embed = discord.Embed(
                title=f"📊 Status Atualizado de {nick}",
                description=(
                    f"🏆 **Posição no Ranking:** `{posicao}º lugar`\n"
                    f"⭐ **Pontos Acumulados:** `{pontos} pts`"
                ),
                color=0x3498db,
                timestamp=datetime.now(TIMEZONE)
            )
            embed.set_footer(text=BOT_NAME)

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        except Exception:
            logger.exception("Erro ao consultar pontos pelo botão.")
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao buscar seus pontos. Tente novamente mais tarde.",
                ephemeral=True
            )


# =====================================================
# BOTÃO PARA CRIAR ABA PRIVADA DO JOGADOR
# =====================================================

class AbrirAbaView(View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Abrir Minha Aba Privada",
        style=discord.ButtonStyle.blurple,
        custom_id="btn_aba_privada_v1",
        emoji="🔒"
    )
    async def abrir_aba(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        canal = interaction.channel
        usuario = interaction.user
        nome_aba = f"pontos-{usuario.name}".lower()

        try:
            aba_existente = discord.utils.get(canal.threads, name=nome_aba)

            if not aba_existente:
                async for thread in canal.archived_threads(private=True):
                    if thread.name == nome_aba:
                        aba_existente = thread
                        await aba_existente.edit(archived=False)
                        break

            if aba_existente:
                await aba_existente.add_user(usuario)
                await interaction.followup.send(
                    f"🔒 Sua aba privada já está aberta! Acesse aqui: {aba_existente.mention}",
                    ephemeral=True
                )
                return

            nova_aba = await canal.create_thread(
                name=nome_aba,
                type=discord.ChannelType.private_thread,
                invitable=False
            )

            await nova_aba.add_user(usuario)

            embed = discord.Embed(
                title=f"🔒 Espaço Privado de {usuario.display_name}",
                description=(
                    "Bem-vindo à sua aba exclusiva!\n"
                    "Somente você e os administradores têm acesso a este espaço.\n\n"
                    "Clique no botão abaixo sempre que quiser puxar seus pontos atualizados:"
                ),
                color=0x3498db
            )

            await nova_aba.send(
                content=usuario.mention,
                embed=embed,
                view=MeuPerfilView(self.bot)
            )

            await interaction.followup.send(
                f"✅ Sua aba privada foi criada! Clique para entrar: {nova_aba.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ O bot não tem permissão para criar tópicos privados neste canal. Verifique as permissões do cargo do bot.",
                ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao criar aba privada.")
            await interaction.followup.send(
                "❌ Ocorreu um erro ao abrir sua aba. Tente novamente.",
                ephemeral=True
            )


# =====================================================
# CLIENTE BOT-TERROR
# =====================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True


class MaratonaBot(discord.Client):

    def __init__(self):
        super().__init__(intents=intents)

        self.pool = None
        self.lista_ativa = None
        self.participantes = {}
        self.mensagem_lista = None

        self.eventos_abertos = set()
        self.eventos_fechados = set()
        self.data_controle = None

    async def setup_hook(self):

        if not TOKEN:
            raise RuntimeError("DISCORD_TOKEN não configurado!")

        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL não configurado!")

        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5
        )

        await init_db(self.pool)

        self.add_view(PresencaView(self))
        self.add_view(MeuPerfilView(self))
        self.add_view(AbrirAbaView(self))

        self.scheduler_loop.start()

        logger.info("BOT-TERROR inicializado!")

    async def close(self):

        if self.pool:
            await self.pool.close()

        await super().close()

    async def obter_canal(self, canal_id):

        canal = self.get_channel(canal_id)

        if canal is None:
            try:
                canal = await self.fetch_channel(canal_id)
            except discord.DiscordException:
                logger.exception(
                    "Não foi possível acessar o canal %s",
                    canal_id
                )

        return canal

    async def log_auditoria(
        self,
        titulo,
        descricao,
        cor=0x3498db
    ):

        canal = await self.obter_canal(CANAL_LOGS_ID)

        if canal is None:
            return

        try:
            embed = discord.Embed(
                title=f"🤖 {BOT_NAME} | {titulo}",
                description=descricao,
                color=cor,
                timestamp=datetime.now(TIMEZONE)
            )

            await canal.send(embed=embed)

        except discord.DiscordException:
            logger.exception("Erro ao enviar log.")

    async def atualizar_lista_msg(self):

        if self.mensagem_lista is None:
            return

        participantes = "\n".join(
            f"• {discord.utils.escape_markdown(nick)}"
            for nick in self.participantes.values()
        )

        if not participantes:
            participantes = "Aguardando participantes..."

        embed = discord.Embed(
            title=f"📋 LISTA: {self.lista_ativa}",
            description=(
                f"**Participantes ({len(self.participantes)}):**\n"
                f"{participantes}"
            ),
            color=0x2ecc71
        )

        try:
            await self.mensagem_lista.edit(
                embed=embed,
                view=PresencaView(self)
            )

        except discord.DiscordException:
            logger.exception("Erro ao atualizar lista.")

    async def abrir_lista(self, nome, horario, emoji):

        canal = await self.obter_canal(CANAL_PRESENCA_ID)

        if canal is None:
            logger.error("Canal de presença indisponível.")
            return False

        self.lista_ativa = nome
        self.participantes = {}

        embed = discord.Embed(
            title=f"{emoji} LISTA ABERTA: {nome}",
            description=(
                f"Evento previsto para **{horario}**.\n"
                "Clique no botão abaixo para participar!"
            ),
            color=0x00ff00
        )

        try:
            self.mensagem_lista = await canal.send(
                content="@everyone",
                embed=embed,
                view=PresencaView(self),
                allowed_mentions=discord.AllowedMentions(
                    everyone=True
                )
            )

            await self.log_auditoria(
                "Lista Aberta",
                f"Evento: **{nome}**",
                0x00ff00
            )

            logger.info("Lista aberta: %s", nome)

            return True

        except discord.DiscordException:
            logger.exception("Erro ao abrir lista.")
            self.limpar_lista()
            return False

    async def distribuir_pontos(self, nome, pts):

        if self.mensagem_lista:

            try:
                embed = self.mensagem_lista.embeds[0]

                embed.title = f"❌ LISTA ENCERRADA: {nome}"
                embed.color = 0xe74c3c

                await self.mensagem_lista.edit(
                    embed=embed,
                    view=None
                )

            except (discord.DiscordException, IndexError):
                logger.exception("Erro ao encerrar lista.")

        if not self.participantes:

            await self.log_auditoria(
                "Lista Vazia",
                f"Evento **{nome}** sem participantes.",
                0xe67e22
            )

            self.limpar_lista()
            return

        quantidade = len(self.participantes)

        try:

            async with self.pool.acquire() as conn:

                async with conn.transaction():

                    for uid, nick in self.participantes.items():

                        await conn.execute(
                            """
                            INSERT INTO ranking
                                (user_id, nick, pontos)
                            VALUES ($1, $2, $3)

                            ON CONFLICT (user_id)
                            DO UPDATE SET
                                pontos = ranking.pontos + EXCLUDED.pontos,
                                nick = EXCLUDED.nick
                            """,
                            uid,
                            nick,
                            pts
                        )

            await self.log_auditoria(
                "Pontos Pagos",
                f"Evento: {nome}\n"
                f"Participantes: {quantidade}\n"
                f"Pontos: {pts}",
                0x27ae60
            )

            canal = await self.obter_canal(CANAL_PONTOS_ID)

            if canal:
                await canal.send(
                    f"✅ **{nome}** finalizado! "
                    f"**{quantidade}** jogadores ganharam "
                    f"**{pts}** pts."
                )

        except Exception:
            logger.exception("Erro ao distribuir pontos.")

        finally:
            self.limpar_lista()

    def limpar_lista(self):

        self.participantes = {}
        self.lista_ativa = None
        self.mensagem_lista = None

    @tasks.loop(seconds=15)
    async def scheduler_loop(self):

        agora = datetime.now(TIMEZONE)
        hoje = agora.date()

        if self.data_controle != hoje:

            self.data_controle = hoje
            self.eventos_abertos.clear()
            self.eventos_fechados.clear()

        for indice, evento in enumerate(eventos):

            nome, hora_boss, dias, pts, emoji = evento

            if dias is not None and agora.weekday() not in dias:
                continue

            hora, minuto = map(int, hora_boss.split(":"))

            dt_boss = agora.replace(
                hour=hora,
                minute=minuto,
                second=0,
                microsecond=0
            )

            dt_abrir = dt_boss - timedelta(minutes=5)
            dt_fechar = dt_boss + timedelta(minutes=10)

            chave = f"{hoje}-{indice}"

            if (
                dt_abrir <= agora < dt_boss
                and chave not in self.eventos_abertos
            ):

                if self.lista_ativa is None:

                    sucesso = await self.abrir_lista(
                        nome,
                        hora_boss,
                        emoji
                    )

                    if sucesso:
                        self.eventos_abertos.add(chave)

                else:
                    logger.warning(
                        "Já existe lista ativa: %s",
                        self.lista_ativa
                    )

            if (
                dt_fechar <= agora < dt_fechar + timedelta(minutes=1)
                and chave not in self.eventos_fechados
            ):

                if self.lista_ativa == nome:
                    await self.distribuir_pontos(nome, pts)

                self.eventos_fechados.add(chave)

    @scheduler_loop.before_loop
    async def antes_scheduler(self):
        await self.wait_until_ready()


client = MaratonaBot()


@client.event
async def on_ready():

    logger.info(
        "🚀 BOT-TERROR ONLINE! Conectado como %s",
        client.user
    )


@client.event
async def on_message(message):

    if message.author.bot or message.guild is None:
        return

    conteudo = message.content.strip()

    if message.author.guild_permissions.administrator:

        if conteudo == "!painel":
            embed = discord.Embed(
                title=f"🛡️ {BOT_NAME} | CENTRAL DO JOGADOR",
                description=(
                    "Clique no botão abaixo para abrir a sua **aba privada**.\n"
                    "Dentro dela, somente você e a administração podem visualizar suas informações e consultar seus pontos atualizados em tempo real!"
                ),
                color=0x2ecc71
            )
            await message.channel.send(embed=embed, view=AbrirAbaView(client))
            try:
                await message.delete()
            except discord.DiscordException:
                pass

        elif conteudo.startswith("!addpontos"):

            try:

                if not message.mentions:
                    raise ValueError()

                partes = conteudo.split()

                if len(partes) < 3:
                    raise ValueError()

                usuario = message.mentions[0]
                qtd = int(partes[2])

                async with client.pool.acquire() as conn:

                    await conn.execute(
                        """
                        INSERT INTO ranking
                            (user_id, nick, pontos)
                        VALUES ($1, $2, $3)

                        ON CONFLICT (user_id)
                        DO UPDATE SET
                            pontos = ranking.pontos + EXCLUDED.pontos,
                            nick = EXCLUDED.nick
                        """,
                        usuario.id,
                        usuario.display_name,
                        qtd
                    )

                await message.channel.send(
                    f"✅ Adicionado **{qtd}** pts para "
                    f"{usuario.mention}!"
                )

                await client.log_auditoria(
                    "Ponto Manual",
                    f"ADM: {message.author}\n"
                    f"Jogador: {usuario.display_name}\n"
                    f"Pontos: {qtd}"
                )

            except ValueError:

                await message.channel.send(
                    "Use: `!addpontos @usuario 10`"
                )

            except Exception:

                logger.exception("Erro em !addpontos.")

                await message.channel.send(
                    "❌ Erro ao adicionar pontos."
                )

        elif conteudo == "!zerar_ranking":

            try:

                async with client.pool.acquire() as conn:
                    await conn.execute("DELETE FROM ranking")

                await message.channel.send(
                    "⚠️ **RANKING RESETADO!**"
                )

                await client.log_auditoria(
                    "Ranking Resetado",
                    f"Ranking zerado por {message.author}.",
                    0xff0000
                )

            except Exception:

                logger.exception("Erro ao zerar ranking.")

                await message.channel.send(
                    "❌ Erro ao zerar ranking."
                )

        elif conteudo == "!testar":

            if client.lista_ativa is not None:

                await message.channel.send(
                    f"⚠️ Já existe uma lista ativa: "
                    f"**{client.lista_ativa}**."
                )

                return

            sucesso = await client.abrir_lista(
                "Teste Manual",
                "Manual",
                "🧪"
            )

            if sucesso:

                await message.channel.send(
                    "✅ Lista de teste criada!"
                )

            else:

                await message.channel.send(
                    "❌ Não foi possível criar a lista."
                )

    if conteudo == "!ranking":

        try:

            async with client.pool.acquire() as conn:

                rows = await conn.fetch(
                    """
                    SELECT nick, pontos
                    FROM ranking
                    ORDER BY pontos DESC, nick ASC
                    """
                )

            if not rows:

                await message.channel.send(
                    "📭 O ranking está vazio."
                )

                return

            linhas = [
                f"**{i + 1}º** "
                f"{discord.utils.escape_markdown(row['nick'])} "
                f"— `{row['pontos']} pts`"
                for i, row in enumerate(rows)
            ]

            blocos = [
                linhas[i:i + 25]
                for i in range(0, len(linhas), 25)
            ]

            for indice, bloco in enumerate(blocos):

                titulo = (
                    f"🏆 {BOT_NAME} | RANKING COMPLETO"
                    if indice == 0
                    else f"🏆 RANKING (CONT. {indice + 1})"
                )

                embed = discord.Embed(
                    title=titulo,
                    description="\n".join(bloco),
                    color=0xffd700
                )

                await message.channel.send(embed=embed)

        except Exception:

            logger.exception("Erro ao consultar ranking.")

            await message.channel.send(
                "❌ Erro ao processar ranking."
            )


if __name__ == "__main__":

    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN não configurado!")

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurado!")

    client.run(TOKEN, log_handler=None)
