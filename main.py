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
# Limpa aspas que o Railway costuma inserir automaticamente no plano Hobby
TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or "").strip().replace('"', '').replace("'", "")

if not TOKEN:
    print("\n--- 🕵️ RELATÓRIO DE ERRO ---")
    print("ERRO: DISCORD_TOKEN não encontrado nas variáveis do Railway.")
    raise Exception("Token não configurado.")

# ==============================
# ⚙️ CONFIGURAÇÕES DO BOT
# ==============================
TIMEZONE = pytz.timezone("America/Sao_Paulo")
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
DB_PATH = "ranking.db"

# Lista de eventos: (Nome, Hora, Dias[None=Todos], Pontos, Emoji)
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
    ("Castle Siege", "21:10", [6], 50, "🛡️"),
]

# Configuração de Intents (Permissões)
intents = discord.Intents.default()
intents.message_content = True #
client = discord.Client(intents=intents)

# Variáveis de controle de estado
lista_ativa = None
participantes = {}
usuarios_registrados = set()
mensagem_lista = None

# ==============================
# 🗄️ BANCO DE DADOS
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
    print("🗄️ Banco de dados pronto.")

# ==============================
# 🏆 LÓGICA DE PONTUAÇÃO
# ==============================
async def distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji):
    global participantes, lista_ativa, mensagem_lista, usuarios_registrados
    
    nicks_para_premiar = list(participantes.values())
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for nick in nicks_para_premiar:
                await db.execute("""
                    INSERT INTO ranking (nick, pontos) VALUES (?, ?)
                    ON CONFLICT(nick) DO UPDATE SET pontos = pontos + excluded.pontos
                """, (nick, pontos))
            await db.commit()

            cur = await db.execute("SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 10")
            ranking_geral = await cur.fetchall()

        if mensagem_lista:
            try: await mensagem_lista.delete()
            except: pass

        await canal_presenca.send(
            f"🔒 **{nome} ENCERRADO**\n"
            f"✅ Pontos atribuídos: +{pontos}\n"
            f"👥 Participantes registrados: {len(nicks_para_premiar)}"
        )

        rank_msg = "🏆 **TOP 10 RANKING GERAL**\n\n"
        for i, (n, p) in enumerate(ranking_geral, 1):
            rank_msg += f"{i}º {n} — {p} pts\n"
        await canal_pontos.send(rank_msg)

    except Exception as e:
        print(f"Erro ao processar ranking: {e}")
    finally:
        # Reseta a lista para o próximo evento
        participantes = {}
        usuarios_registrados = set()
        lista_ativa = None
        mensagem_lista = None

# ==============================
# ⏰ AGENDADOR (SCHEDULER)
# ==============================
async def scheduler():
    # Definição das globais no topo para evitar SyntaxError
    global mensagem_lista, participantes, usuarios_registrados, lista_ativa

    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = datetime.now(TIMEZONE)
            canal_presenca = client.get_channel(CANAL_PRESENCA_ID)
            canal_pontos = client.get_channel(CANAL_PONTOS_ID)

            if not canal_presenca:
                await asyncio.sleep(10)
                continue

            for nome, hora, dias, pontos, emoji in eventos:
                h, m = map(int, hora.split(":"))
                evento_hoje = now.replace(hour=h, minute=m, second=0, microsecond=0)

                if evento_hoje < now:
                    evento_hoje += timedelta(days=1)

                if dias and now.weekday() not in dias:
                    continue

                abrir_em = evento_hoje - timedelta(minutes=5)
                fechar_em = evento_hoje + timedelta(minutes=10)

                # Abertura da Lista
                if abrir_em <= now <= abrir_em + timedelta(seconds=50) and not lista_ativa:
                    lista_ativa = nome
                    participantes = {}
                    usuarios_registrados = set()
                    mensagem_lista = await canal_presenca.send(
                        f"{emoji} **LISTA ABERTA: {nome}**\n"
                        f"⏰ Fecha em: 15 min\n"
                        f"👉 Digite seu **NICK** abaixo!"
                    )

                # Fechamento da Lista
                if fechar_em <= now <= fechar_em + timedelta(seconds=50) and lista_ativa == nome:
                    await distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji)

        except Exception as e:
            print(f"Erro no loop do agendador: {e}")
        
        await asyncio.sleep(40)

# ==============================
# 🤖 EVENTOS DO DISCORD
# ==============================
@client.event
async def on_ready():
    await init_db()
    print(f"🚀 {client.user} está online e monitorando!")
    client.loop.create_task(scheduler())

@client.event
async def on_message(message):
    global participantes, mensagem_lista, usuarios_registrados, lista_ativa

    if message.author.bot:
        return

    # Comando para zerar ranking (Apenas Administradores)
    if message.content == "!zerar_ranking":
        if message.author.guild_permissions.administrator:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DROP TABLE IF EXISTS ranking")
                await db.commit()
            await init_db()
            await message.channel.send("⚠️ **O ranking foi zerado com sucesso!**")
        else:
            await message.channel.send("❌ Você não tem permissão para usar este comando.")
        return

    # Lógica de captação de nicks no canal de presença
    if message.channel.id == CANAL_PRESENCA_ID:
        # Se não houver lista aberta ou o usuário já registrou, apaga a mensagem
        if not lista_ativa or message.author.id in usuarios_registrados:
            try: await message.delete()
            except: pass
            return

        nick = message.content.strip()
        if 2 <= len(nick) <= 25:
            usuarios_registrados.add(message.author.id)
            participantes[message.author.id] = nick
            
            try: 
                await message.delete() # Apaga o nick enviado para limpar o chat
                if mensagem_lista:
                    lista_txt = "\n".join([f"• {n}" for n in participantes.values()])
                    await mensagem_lista.edit(content=(
                        f"📋 **LISTA ATIVA: {lista_ativa}**\n"
                        f"👥 Participantes: {len(participantes)}\n\n"
                        f"{lista_txt}"
                    ))
            except: 
                pass

# ==============================
# 🏁 INICIALIZAÇÃO
# ==============================
try:
    client.run(TOKEN)
except Exception as e:
    print(f"ERRO CRÍTICO: {e}")
