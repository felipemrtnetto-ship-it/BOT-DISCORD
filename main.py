import os
from dotenv import load_dotenv
import discord
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz

# ==============================
# LOAD ENV
# ==============================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise Exception("❌ TOKEN não encontrado!")

# ==============================
# CONFIG
# ==============================
TIMEZONE = pytz.timezone("America/Sao_Paulo")

CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076

# ==============================
# EVENTOS (AGORA COM PONTOS + EMOJI)
# ==============================
eventos = [
    ("Galia Black", "21:35", None, 2, "🗡️"),
    ("Kundun", "13:10", None, 2, "🐲"),
    ("Kundun", "15:10", None, 2, "🐲"),
    ("Galia Black", "16:45", None, 2, "🗡️"),
    ("Blood Wizard", "18:10", None, 5, "🧙‍♂️"),
    ("Crusher Skeleton", "19:05", None, 5, "💀"),
    ("Necromancer", "19:40", None, 5, "☠️"),
    ("Selupan", "20:10", None, 5, "🦂"),
    ("Skull Reaper", "20:50", None, 5, "👻"),
    ("Gywen", "22:10", None, 5, "🐺"),
    ("HellMaine", "22:30", None, 20, "👿"),
    ("Balgass", "23:00", [2, 5], 30, "🧌"),
    ("Yorm", "23:40", None, 15, "🐗"),
    ("Zorlak", "01:10", None, 15, "🐉"),

    # 🛡️ CASTLE SIEGE (DOMINGO = 6)
    ("Castle Siege", "21:00", [6], 50, "🛡️"),
]

DB_PATH = "ranking.db"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

lista_ativa = None
participantes = {}
usuarios_registrados = set()
mensagem_lista = None

evento_aberto_id = None
evento_fechado_id = None

# ==============================
# DATABASE
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
# FINALIZAR EVENTO
# ==============================
async def distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji):
    global participantes, lista_ativa, mensagem_lista

    lista_final = list(participantes.values())

    async with aiosqlite.connect(DB_PATH) as db:
        for nick in lista_final:
            cur = await db.execute("SELECT pontos FROM ranking WHERE nick=?", (nick,))
            row = await cur.fetchone()

            if row:
                await db.execute(
                    "UPDATE ranking SET pontos = pontos + ? WHERE nick=?",
                    (pontos, nick),
                )
            else:
                await db.execute(
                    "INSERT INTO ranking (nick, pontos) VALUES (?,?)",
                    (nick, pontos),
                )

        await db.commit()

        cur = await db.execute(
            "SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 10"
        )
        ranking_geral = await cur.fetchall()

    if mensagem_lista:
        try:
            await mensagem_lista.delete()
        except:
            pass

    lista_txt = "\n".join([f"{i+1}. {n}" for i, n in enumerate(lista_final)])

    await canal_presenca.send(
        f"🔒 **Lista fechada!**\n\n"
        f"{emoji} **{nome} FINALIZADO**\n\n"
        f"👥 Participantes:\n"
        f"{lista_txt if lista_txt else 'Nenhum participante.'}"
    )

    msg = "🏆 **RANKING GERAL – BOSSES**\n\n"
    for i, (nick, pts) in enumerate(ranking_geral, 1):
        msg += f"{i}. {nick} — {pts} pts\n"

    await canal_pontos.send(msg)

    participantes = {}
    lista_ativa = None
    mensagem_lista = None

# ==============================
# SCHEDULER
# ==============================
async def scheduler():
    global lista_ativa, participantes, mensagem_lista
    global evento_aberto_id, evento_fechado_id, usuarios_registrados

    await client.wait_until_ready()

    while True:
        canal_presenca = client.get_channel(CANAL_PRESENCA_ID)
        canal_pontos = client.get_channel(CANAL_PONTOS_ID)

        now = datetime.now(TIMEZONE)

        for nome, hora, dias, pontos, emoji in eventos:

            h, m = map(int, hora.split(":"))
            evento = now.replace(hour=h, minute=m, second=0, microsecond=0)

            if evento < now:
                evento += timedelta(days=1)

            if dias and now.weekday() not in dias:
                continue

            evento_id = f"{nome}-{evento.date()}"

            abrir = evento - timedelta(minutes=5)
            fechar = evento + timedelta(minutes=10)

            # ABRIR
            if abrir <= now <= abrir + timedelta(seconds=20):
                if lista_ativa is None and evento_aberto_id != evento_id:

                    print(f"🟢 Abrindo: {nome}")

                    lista_ativa = nome
                    participantes = {}
                    usuarios_registrados = set()
                    evento_aberto_id = evento_id

                    mensagem_lista = await canal_presenca.send(
                        f"{emoji} **LISTA ABERTA — {nome}**\n\n"
                        f"👥 Participantes: 0\n\n"
                        f"✍️ Envie seu nick!"
                    )

            # FECHAR
            if fechar <= now <= fechar + timedelta(seconds=20):
                if lista_ativa == nome and evento_fechado_id != evento_id:

                    print(f"🔴 Fechando: {nome}")

                    evento_fechado_id = evento_id
                    await distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji)

        await asyncio.sleep(20)

# ==============================
# CAPTURA NICK
# ==============================
@client.event
async def on_message(message):
    global participantes, mensagem_lista, usuarios_registrados

    if message.author.bot:
        return

    if message.channel.id != CANAL_PRESENCA_ID:
        return

    if not lista_ativa:
        try:
            await message.delete()
        except:
            pass
        return

    if message.author.id in usuarios_registrados:
        try:
            await message.delete()
        except:
            pass
        return

    nick = message.content.strip()
    if not nick:
        return

    usuarios_registrados.add(message.author.id)
    participantes[message.author.id] = nick

    try:
        await message.delete()
    except:
        pass

    if mensagem_lista:
        lista_txt = "\n".join([f"• {n}" for n in participantes.values()])

        await mensagem_lista.edit(
            content=(
                f"📋 **LISTA ABERTA — {lista_ativa}**\n\n"
                f"👥 Participantes: {len(participantes)}\n\n"
                f"{lista_txt}"
            )
        )

# ==============================
# READY
# ==============================
@client.event
async def on_ready():
    await init_db()
    asyncio.create_task(scheduler())
    print(f"🚀 Bot online como {client.user}")

# ==============================
# START
# ==============================
client.run(TOKEN)
