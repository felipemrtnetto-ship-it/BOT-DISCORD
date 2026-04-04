import os
import discord
from discord.ui import Button, View
import asyncio
import asyncpg
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# ==============================
# ⚙️ CONFIGURAÇÕES E AMBIENTE
# ==============================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Correção de esquema para o asyncpg
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

TIMEZONE = pytz.timezone("America/Sao_Paulo")

# IDs DOS CANAIS (VERIFIQUE SE ESTÃO CORRETOS NO SEU DISCORD)
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
CANAL_LOGS_ID = 1489805148204040312

# Lista de Eventos: (Nome, Hora do Boss, Dias [None=Todos], Pontos, Emoji)
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

# ==============================
# 🗄️ BANCO DE DADOS (POSTGRES)
# ==============================
async def init_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS ranking (
                user_id BIGINT PRIMARY KEY,
                nick TEXT,
                pontos INTEGER DEFAULT 0
            )
        ''')
        await conn.close()
        print("✅ Banco de Dados conectado e pronto!")
    except Exception as e:
        print(f"❌ Erro Crítico no Banco: {e}")

# ==============================
# 🔘 INTERFACE (BOTÃO)
# ==============================
class PresencaView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Marcar Presença", style=discord.ButtonStyle.green, custom_id="btn_presenca_v2", emoji="✅")
    async def marcar_presenca(self, interaction: discord.Interaction):
        if not self.bot.lista_ativa:
            return await interaction.response.send_message("❌ Nenhuma lista aberta no momento!", ephemeral=True)
        
        user_id = interaction.user.id
        nick = interaction.user.display_name

        if user_id in self.bot.participantes:
            return await interaction.response.send_message("⚠️ Você já está na lista!", ephemeral=True)

        self.bot.participantes[user_id] = nick
        await self.bot.atualizar_lista_msg()
        await interaction.response.send_message(f"✅ Presença confirmada como **{nick}**!", ephemeral=True)

# ==============================
# 🤖 CLASSE DO BOT
# ==============================
class MaratonaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.lista_ativa = None
        self.participantes = {}
        self.mensagem_lista = None

    async def setup_hook(self):
        await init_db()
        self.add_view(PresencaView(self))
        self.loop.create_task(self.scheduler())

    async def log_auditoria(self, titulo, desc, cor=0x3498db):
        canal = self.get_channel(CANAL_LOGS_ID)
        if canal:
            embed = discord.Embed(
