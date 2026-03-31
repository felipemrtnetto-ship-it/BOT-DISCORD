import os
from dotenv import load_dotenv
import discord
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz

# ==============================
# 🔍 CONFIGURAÇÃO DE AMBIENTE
# ==============================
load_dotenv()
TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or "").strip().replace('"', '').replace("'", "")

if not TOKEN:
    raise Exception("Token não encontrado no Railway.")

# ==============================
# ⚙️ CONFIGURAÇÕES
# ==============================
TIMEZONE = pytz.timezone("America/Sao_Paulo")
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
DB_PATH = "ranking.db"

eventos = [
    ("Galia Black", "10:45", None, 2, "🗡️"),
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
    ("Castle Siege", "21:10", [6], 50, "🛡️"),
]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

lista_ativa = None
participantes = {}
usuarios_registrados = set()
mensagem_lista = None
alerta_enviado = False

# ==============================
# 🗄️ BANCO DE DADOS
# ==============================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS ranking (nick TEXT PRIMARY KEY, pontos INTEGER DEFAULT 0)")
        await db.commit()

# ==============================
# 🏆 LÓGICA DE PONTOS (RANKING COMPLETO)
# ==============================
async def gerar_ranking_embed():
    async with aiosqlite.connect(DB_PATH) as db:
        # REMOVIDO O LIMIT 10 - Agora pega todos
        cur = await db.execute("SELECT nick, pontos FROM ranking ORDER BY pontos DESC")
        ranking = await cur.fetchall()
    
    embed = discord.Embed(title="🏆 RANKING GERAL DA MARATONA", color=0xFFD700)
    
    if not ranking:
        embed.description = "Nenhum ponto registrado ainda."
    else:
        txt = ""
        for i, (n, p) in enumerate(ranking, 1):
            medalha = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"**{i}º**"
            linha = f"{medalha} {n} — {p} pts\n"
            
            # Evita que o embed quebre o limite de caracteres do Discord
            if len(txt) + len(linha) > 3900:
                txt += "... e outros jogadores."
                break
            txt += linha
            
        embed.description = txt
    return embed

async def distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji):
    global participantes, lista_ativa, mensagem_lista, usuarios_registrados, alerta_enviado
    nicks = list(participantes.values())
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for nick in nicks:
                await db.execute("INSERT INTO ranking (nick, pontos) VALUES (?, ?) ON CONFLICT(nick) DO UPDATE SET pontos = pontos + excluded.pontos", (nick, pontos))
            await db.commit()

        if mensagem_lista:
            try: await mensagem_lista.delete()
            except: pass

        embed_fim = discord.Embed(title=f"🔒 {nome} ENCERRADO", color=0xFF0000)
        embed_fim.add_field(name="✅ Pontos", value=f"+{pontos}", inline=True)
        embed_fim.add_field(name="👥 Players", value=len(nicks), inline=True)
        await canal_presenca.send(embed=embed_fim)

        if canal_pontos:
            await canal_pontos.send(embed=await gerar_ranking_embed())
    finally:
        participantes = {}; usuarios_registrados = set(); lista_ativa = None; alerta_enviado = False

# ==============================
# ⏰ SCHEDULER
# ==============================
async def scheduler():
    global mensagem_lista, participantes, usuarios_registrados, lista_ativa, alerta_enviado
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = datetime.now(TIMEZONE)
            canal_presenca = client.get_channel(CANAL_PRESENCA_ID)
            canal_pontos = client.get_channel(CANAL_PONTOS_ID)

            if canal_presenca:
                for nome, hora, dias, pontos, emoji in eventos:
                    h, m = map(int, hora.split(":"))
                    ev_hoje = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if ev_hoje < now - timedelta(hours=1): ev_hoje += timedelta(days=1)
                    if dias and now.weekday() not in dias: continue

                    abrir_em = ev_hoje - timedelta(minutes=5)
                    alerta_em = ev_hoje + timedelta(minutes=5)
                    fechar_em = ev_hoje + timedelta(minutes=10)

                    if abrir_em <= now <= abrir_em + timedelta(seconds=40) and not lista_ativa:
                        lista_ativa = nome; participantes = {}; usuarios_registrados = set()
                        embed = discord.Embed(title=f"{emoji} LISTA ABERTA: {nome}", description="👉 Digite seu **NICK** abaixo!\n⏰ Fecha em 15 minutos.", color=0x00FF00)
                        mensagem_lista = await canal_presenca.send(content="@everyone", embed=embed)

                    if alerta_em <= now <= alerta_em + timedelta(seconds=40) and lista_ativa == nome and not alerta_enviado:
                        alerta_enviado = True
                        await canal_presenca.send(f"⚠️ **ATENÇÃO @everyone**\nA lista de **{nome}** fecha em 5 minutos!")

                    if fechar_em <= now <= fechar_em + timedelta(seconds=40) and lista_ativa == nome:
                        await distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji)
        except Exception as e: print(f"Erro no scheduler: {e}")
        await asyncio.sleep(30)

# ==============================
# 🤖 EVENTOS E COMANDOS
# ==============================
@client.event
async def on_ready():
    await init_db()
    print(f"🚀 {client.user} ONLINE!")
    client.loop.create_task(scheduler())

@client.event
async def on_message(message):
    global participantes, mensagem_lista, usuarios_registrados, lista_ativa
    if message.author.bot: return

    # --- COMANDOS ADM ---
    if message.content.startswith("!add") and message.author.guild_permissions.administrator:
        try:
            _, nick, pts = message.content.split()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT INTO ranking (nick, pontos) VALUES (?, ?) ON CONFLICT(nick) DO UPDATE SET pontos = pontos + excluded.pontos", (nick, int(pts)))
                await db.commit()
            await message.channel.send(f"✅ {pts} pontos adicionados a **{nick}**.")
        except: await message.channel.send("Uso: `!add Nick Pontos`")

    if message.content.startswith("!remove") and message.author.guild_permissions.administrator:
        try:
            _, nick, pts = message.content.split()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE ranking SET pontos = MAX(0, pontos - ?) WHERE nick = ?", (int(pts), nick))
                await db.commit()
            await message.channel.send(f"⚠️ {pts} pontos removidos de **{nick}**.")
        except: await message.channel.send("Uso: `!remove Nick Pontos`")

    if message.content == "!fechar" and message.author.guild_permissions.administrator:
        if lista_ativa:
            c_pres = client.get_channel(CANAL_PRESENCA_ID)
            c_pont = client.get_channel(CANAL_PONTOS_ID)
            pts_evento = next((e[3] for e in eventos if e[0] == lista_ativa), 0)
            emoji_evento = next((e[4] for e in eventos if e[0] == lista_ativa), "📝")
            await distribuir_pontos(c_pres, c_pont, lista_ativa, pts_evento, emoji_evento)

    if message.content == "!zerar_ranking" and message.author.guild_permissions.administrator:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DROP TABLE IF EXISTS ranking"); await db.commit()
        await init_db(); await message.channel.send("⚠️ Ranking Zerado!")

    # --- COMANDOS PLAYER ---
    if message.content == "!ranking":
        await message.channel.send(embed=await gerar_ranking_embed())

    if message.content.startswith("!meus_pontos"):
        try:
            nick = message.content.split()[1]
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute("SELECT pontos FROM ranking WHERE nick = ?", (nick,))
                res = await cur.fetchone()
            await message.channel.send(f"👤 **{nick}** tem **{res[0] if res else 0}** pontos.")
        except: await message.channel.send("Uso: `!meus_pontos Nick`")

    # --- LÓGICA DA LISTA ---
    if message.channel.id == CANAL_PRESENCA_ID:
        if not lista_ativa or message.author.id in usuarios_registrados:
            if not message.content.startswith("!"):
                try: await message.delete()
                except: pass
            return
        nick = message.content.strip()
        if 2 <= len(nick) <= 20:
            usuarios_registrados.add(message.author.id)
            participantes[message.author.id] = nick
            try:
                await message.delete()
                if mensagem_lista:
                    txt = "\n".join([f"• {n}" for n in participantes.values()])
                    embed = discord.Embed(title=f"📋 LISTA ATIVA: {lista_ativa}", description=f"👥 Players: {len(participantes)}\n\n{txt}", color=0x00FF00)
                    await mensagem_lista.edit(embed=embed)
            except: pass

client.run(TOKEN)
