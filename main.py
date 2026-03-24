import os
import discord
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz

# ==============================
# TOKEN (Railway + fallback)
# ==============================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("❌ TOKEN não encontrado!")
    exit()

# ==============================
# CONFIG
# ==============================
PONTOS = 10
TIMEZONE = pytz.timezone("America/Sao_Paulo")

CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076

eventos = [
    ("Galia Black", "21:35", None),
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

DB_PATH = "ranking.db"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

lista_ativa = None
participantes = {}
mensagem_lista = None
evento_atual = None
ultimo_evento = None

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
# FINALIZAR EVENTO
# ==============================
async def distribuir_pontos(canal_presenca, canal_pontos, nome):
    global participantes, lista_ativa, mensagem_lista, ultimo_evento

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

    if mensagem_lista:
        try:
            await mensagem_lista.delete()
        except:
            pass

    lista_txt = "\n".join([f"{i+1}. {n}" for i, n in enumerate(lista_final)])

    await canal_presenca.send(
        f"🔒 **LISTA FECHADA — {nome}**\n\n"
        f"👥 Participantes:\n"
        f"{lista_txt if lista_txt else 'Nenhum participante.'}"
    )

    msg = "🏆 **RANKING GERAL – BOSSES**\n\n"
    for i, (nick, pontos) in enumerate(ranking_geral, 1):
        msg += f"{i}. {nick} — {pontos} pts\n"

    await canal_pontos.send(msg)

    participantes = {}
    lista_ativa = None
    mensagem_lista = None
    ultimo_evento = nome

# ==============================
# SCHEDULER CORRIGIDO
# ==============================
async def scheduler():
    global lista_ativa, participantes, mensagem_lista, evento_atual

    await client.wait_until_ready()

    while True:

        canal_presenca = client.get_channel(CANAL_PRESENCA_ID)
        canal_pontos = client.get_channel(CANAL_PONTOS_ID)

        if not canal_presenca or not canal_pontos:
            print("❌ Canal não encontrado")
            await asyncio.sleep(10)
            continue

        now = datetime.now(TIMEZONE)

        for nome, hora, dias in eventos:

            h, m = map(int, hora.split(":"))
            evento = now.replace(hour=h, minute=m, second=0, microsecond=0)

            if evento < now:
                evento += timedelta(days=1)

            if dias and now.weekday() not in dias:
                continue

            abrir = evento - timedelta(minutes=5)
            fechar = evento + timedelta(minutes=10)

            # 🔥 ABRIR SOMENTE NO MOMENTO CERTO
            if abrir <= now <= abrir + timedelta(seconds=20):
                if lista_ativa is None:
                    lista_ativa = nome
                    evento_atual = nome
                    participantes = {}

                    mensagem_lista = await canal_presenca.send(
                        f"📋 **LISTA ABERTA — {nome}**\n\n"
                        f"👥 Participantes: 0\n\n"
                        f"✍️ Envie seu nick!"
                    )

            # 🔥 FECHAR CORRETAMENTE
            if fechar <= now <= fechar + timedelta(seconds=20):
                if lista_ativa == nome:
                    await distribuir_pontos(canal_presenca, canal_pontos, nome)

        await asyncio.sleep(20)

# ==============================
# CAPTURA DE NICK
# ==============================
@client.event
async def on_message(message):
    global participantes, mensagem_lista

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

    nick = message.content.strip()

    if not nick:
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
    print(f"✅ Bot online como {client.user}")

# ==============================
# START
# ==============================
client.run(TOKEN)
