import os
from dotenv import load_dotenv
import discord
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz

# ==============================
# 🔍 DEBUG DE AMBIENTE (RAILWAY FIX)
# ==============================
load_dotenv()

# Tenta carregar de todas as formas possíveis
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")

print("\n--- 🕵️ RELATÓRIO DE INICIALIZAÇÃO ---")
# Lista as chaves para sabermos se o Railway injetou algo
chaves_encontradas = list(os.environ.keys())
print(f"DEBUG: Chaves de sistema detectadas: {', '.join([k for k in chaves_encontradas if 'TOKEN' in k.upper()])}")

if not TOKEN:
    print("❌ ERRO FATAL: Nenhuma variável de Token foi encontrada!")
    print("Acesse 'Variables' no Railway e crie: DISCORD_TOKEN")
    print("---------------------------------------\n")
    raise Exception("Token não configurado no painel do Railway.")
else:
    print(f"✅ SUCESSO: Token detectado (Início: {TOKEN[:5]}...)")
    print("---------------------------------------\n")

# ==============================
# CONFIGURAÇÕES DO BOT
# ==============================
TIMEZONE = pytz.timezone("America/Sao_Paulo")
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
DB_PATH = "ranking.db"

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

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Estados globais
lista_ativa = None
participantes = {}
usuarios_registrados = set()
mensagem_lista = None
evento_aberto_id = None
evento_fechado_id = None

# ==============================
# BANCO DE DADOS
# ==============================
async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ranking (
                nick TEXT PRIMARY KEY,
                pontos INTEGER DEFAULT 0
            )
            """)
            await db.commit()
        print("🗄️ Banco de dados pronto.")
    except Exception as e:
        print(f"❌ Erro ao iniciar DB: {e}")

# ==============================
# LÓGICA DE PONTUAÇÃO
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

        lista_str = "\n".join([f"• {n}" for n in nicks_para_premiar])
        await canal_presenca.send(
            f"🔒 **{nome} ENCERRADO**\n"
            f"✅ Pontos atribuídos: +{pontos}\n"
            f"👥 Participantes: {len(nicks_para_premiar)}\n\n"
            f"Lista final:\n{lista_str if lista_str else 'Vazia'}"
        )

        rank_msg = "🏆 **TOP 10 RANKING GERAL**\n\n"
        for i, (n, p) in enumerate(ranking_geral, 1):
            rank_msg += f"{i}º {n} — {p} pts\n"
        await canal_pontos.send(rank_msg)

    except Exception as e:
        print(f"Erro ao processar ranking: {e}")
    finally:
        participantes = {}
        usuarios_registrados = set()
        lista_ativa = None

# ==============================
# AGENDADOR (SCHEDULER)
# ==============================
async def scheduler():
    global lista_ativa, participantes, mensagem_lista
    global evento_aberto_id, evento_fechado_id, usuarios_registrados

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

                ev_id = f"{nome}-{evento_hoje.strftime('%Y-%m-%d-%H-%M')}"
                abrir_em = evento_hoje - timedelta(minutes=5)
                fechar_em = evento_hoje + timedelta(minutes=10)

                # Abertura
                if abrir_em <= now <= abrir_em + timedelta(seconds=45):
                    if lista_ativa is None and evento_aberto_id != ev_id:
                        lista_ativa = nome
                        participantes = {}
                        usuarios_registrados = set()
                        evento_aberto_id = ev_id
                        mensagem_lista = await canal_presenca.send(
                            f"{emoji} **LISTA ABERTA: {nome}**\n"
                            f"⏰ Fecha em: 15 min\n"
                            f"👉 Digite seu **NICK** abaixo!"
                        )

                # Fechamento
                if fechar_em <= now <= fechar_em + timedelta(seconds=45):
                    if lista_ativa == nome and evento_fechado_id != ev_id:
                        evento_fechado_id = ev_id
                        await distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji)

        except Exception as e:
            print(f"Erro no loop: {e}")
        
        await asyncio.sleep(30)

# ==============================
# EVENTOS DO DISCORD
# ==============================
@client.event
async def on_ready():
    await init_db()
    print(f"🚀 {client.user} está online e monitorando bosses!")
    if not hasattr(client, 'task_started'):
        client.task_started = True
        client.loop.create_task(scheduler())

@client.event
async def on_message(message):
    global participantes, mensagem_lista, usuarios_registrados

    if message.author.bot or message.channel.id != CANAL_PRESENCA_ID:
        return

    # Se não há lista, apaga a mensagem
    if not lista_ativa:
        try: await message.delete()
        except: pass
        return

    # Se já registrou, apaga
    if message.author.id in usuarios_registrados:
        try: await message.delete()
        except: pass
        return

    nick = message.content.strip()
    if nick and len(nick) <= 25:
        usuarios_registrados.add(message.author.id)
        participantes[message.author.id] = nick
        
        try: await message.delete()
        except: pass

        if mensagem_lista:
            try:
                lista_txt = "\n".join([f"• {n}" for n in participantes.values()])
                await mensagem_lista.edit(content=(
                    f"📋 **LISTA ATIVA: {lista_ativa}**\n"
                    f"👥 Participantes: {len(participantes)}\n\n"
                    f"{lista_txt}"
                ))
            except: pass

# ==============================
# EXECUÇÃO
# ==============================
try:
    client.run(TOKEN)
except Exception as e:
    print(f"FATAL: O bot não conseguiu iniciar. Detalhes: {e}")
