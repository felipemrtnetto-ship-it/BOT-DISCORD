import os
import discord
from discord import app_commands
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz

# ==============================
# CONFIG
# ==============================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN não configurado nas variáveis do Railway")

PONTOS = 10
TIMEZONE = pytz.timezone("America/Sao_Paulo")

CANAL_PRESENCA = "🧙🏻‍♂️presença-boss"
CANAL_PONTOS = "💯pontos-boss"

eventos = [
    ("Galia Black", "23:20", None),
    ("Kundun", "13:10", None),
    ("Kundun", "15:10", None),
    ("Galia Black", "16:45", None),
    ("Blood Wizard", "18:10", None),
    ("Crusher Skeleton", "19:05", None),
    ("Necromancer", "19:40", None),
    ("Selupan", "20:10", None),
    ("Skull Reaper", "20:50", None),
    ("Gywen", "22:10", None),
    ("HellMaine", "22:30", None),
    ("Balgass", "23:00", [2, 5]),
    ("Yorm", "23:40", None),
    ("Zorlak", "01:10", None),
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ranking.db")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

lista_ativa = None
participantes = {}
mensagem_lista = None


# ==============================
# BANCO
# ==============================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ranking (
            nick TEXT PRIMARY KEY,
            pontos INTEGER DEFAULT 0
        )
        """)
        await db.commit()


# ==============================
# DISTRIBUIR PONTOS
# ==============================
async def distribuir_pontos(canal_presenca, canal_pontos, nome):
    global participantes, lista_ativa, mensagem_lista

    lista_final = list(participantes.values())

    async with aiosqlite.connect(DB_PATH) as db:
        for nick in lista_final:
            cur = await db.execute("SELECT pontos FROM ranking WHERE nick=?", (nick,))
            row = await cur.fetchone()

            if row:
                await db.execute(
                    "UPDATE ranking SET pontos = pontos + ? WHERE nick=?",
                    (PONTOS, nick),
                )
            else:
                await db.execute(
                    "INSERT INTO ranking (nick, pontos) VALUES (?,?)",
                    (nick, PONTOS),
                )

        await db.commit()

        cur = await db.execute(
            "SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 10"
        )
        ranking_geral = await cur.fetchall()

    # Apagar mensagem da lista aberta
    if mensagem_lista:
        try:
            await mensagem_lista.delete()
        except:
            pass

    participantes_formatado = "\n".join(
        [f"{i+1}. {n}" for i, n in enumerate(lista_final)]
    )

    await canal_presenca.send(
        f"📋 **LISTA FINALIZADA — {nome}**\n\n"
        f"👥 Participantes:\n"
        f"{participantes_formatado if participantes_formatado else 'Nenhum participante.'}"
    )

    msg_ranking = "🏆 **RANKING GERAL – BOSSES**\n\n"
    for i, (nick, pontos) in enumerate(ranking_geral, 1):
        msg_ranking += f"{i}. {nick} — {pontos} pts\n"

    await canal_pontos.send(msg_ranking)

    print(f"Lista fechada: {nome}")

    participantes = {}
    lista_ativa = None
    mensagem_lista = None


# ==============================
# SCHEDULER
# ==============================
async def scheduler():
    await client.wait_until_ready()

    while not client.is_closed():

        canal_presenca = discord.utils.get(
            client.get_all_channels(), name=CANAL_PRESENCA
        )
        canal_pontos = discord.utils.get(
            client.get_all_channels(), name=CANAL_PONTOS
        )

        if not canal_presenca or not canal_pontos:
            await asyncio.sleep(30)
            continue

        now = datetime.now(TIMEZONE)
        print(f"[{now.strftime('%H:%M:%S')}] Verificando eventos...")

        for nome, hora, dias in eventos:
            h, m = map(int, hora.split(":"))
            evento = now.replace(hour=h, minute=m, second=0, microsecond=0)

            # Corrigir evento após meia-noite
            if evento < now - timedelta(minutes=15):
                evento += timedelta(days=1)

            if dias and now.weekday() not in dias:
                continue

            abrir = evento - timedelta(minutes=5)
            fechar = evento + timedelta(minutes=10)

            global lista_ativa, participantes, mensagem_lista

            # ABRIR LISTA
            if abrir <= now <= abrir + timedelta(seconds=30):
                if lista_ativa is None:
                    lista_ativa = nome
                    participantes = {}

                    mensagem_lista = await canal_presenca.send(
                        f"📋 **LISTA ABERTA — {nome}**\n\n"
                        f"👥 Participantes: 0\n\n"
                        f"✍️ Envie seu nick no chat!"
                    )

                    print(f"Lista aberta: {nome}")

            # FECHAR LISTA
            if fechar <= now <= fechar + timedelta(seconds=30):
                if lista_ativa == nome:
                    await distribuir_pontos(canal_presenca, canal_pontos, nome)

        await asyncio.sleep(30)


# ==============================
# BLOQUEAR MENSAGENS + DUPLICADOS
# ==============================
@client.event
async def on_message(message):
    global participantes, mensagem_lista

    if message.author.bot:
        return

    if message.channel.name != CANAL_PRESENCA:
        return

    if not lista_ativa:
        try:
            await message.delete()
        except:
            pass
        return

    nick = message.content.strip().lower()

    # validações
    if not nick or len(nick) > 15:
        try:
            await message.delete()
        except:
            pass
        return

    if nick in participantes.values():
        try:
            await message.delete()
        except:
            pass
        return

    participantes[message.author.id] = nick

    try:
        await message.delete()
    except:
        pass

    if mensagem_lista:
        lista_formatada = "\n".join([f"• {n}" for n in participantes.values()])

        try:
            await mensagem_lista.edit(
                content=(
                    f"📋 **LISTA ABERTA — {lista_ativa}**\n\n"
                    f"👥 Participantes: {len(participantes)}\n\n"
                    f"{lista_formatada}\n\n"
                    f"✍️ Envie seu nick no chat!"
                )
            )
        except:
            mensagem_lista = None


# ==============================
# READY
# ==============================
@client.event
async def on_ready():
    await init_db()
    asyncio.create_task(scheduler())
    print("✅ Bot online!")


client.run(TOKEN)
