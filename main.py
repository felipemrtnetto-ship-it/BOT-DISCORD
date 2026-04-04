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

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

TIMEZONE = pytz.timezone("America/Sao_Paulo")

CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
CANAL_LOGS_ID = 1489805148204040312

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
# 🗄️ BANCO DE DADOS
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
        print("✅ Banco de Dados conectado!")
    except Exception as e:
        print(f"❌ Erro no Banco: {e}")

# ==============================
# 🔘 INTERFACE (SISTEMA DE BOTÃO)
# ==============================
class PresencaView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    # Adicionado o parâmetro 'button' para evitar o TypeError
    @discord.ui.button(label="Marcar Presença", style=discord.ButtonStyle.green, custom_id="btn_pres_v2", emoji="✅")
    async def marcar_presenca(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.bot.lista_ativa:
            return await interaction.response.send_message("❌ Nenhuma lista aberta!", ephemeral=True)
        
        user_id = interaction.user.id
        nick = interaction.user.display_name

        if user_id in self.bot.participantes:
            return await interaction.response.send_message("⚠️ Você já está na lista!", ephemeral=True)

        self.bot.participantes[user_id] = nick
        await self.bot.atualizar_lista_msg()
        await interaction.response.send_message(f"✅ Confirmado: **{nick}**", ephemeral=True)

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
            embed = discord.Embed(title=titulo, description=desc, color=cor, timestamp=datetime.now(TIMEZONE))
            await canal.send(embed=embed)

    async def atualizar_lista_msg(self):
        if self.mensagem_lista:
            txt = "\n".join([f"• {n}" for n in self.participantes.values()])
            embed = discord.Embed(
                title=f"📋 LISTA: {self.lista_ativa}",
                description=f"Clique no botão abaixo!\n\n**Participantes ({len(self.participantes)}):**\n{txt}",
                color=0x2ecc71
            )
            try:
                await self.mensagem_lista.edit(embed=embed, view=PresencaView(self))
            except:
                pass

    async def distribuir_pontos(self, nome, pts):
        if not self.participantes:
            await self.log_auditoria("⚠️ Lista Vazia", f"Evento **{nome}** sem ninguém.", 0xe67e22)
            self.lista_ativa = None
            return

        try:
            conn = await asyncpg.connect(DATABASE_URL)
            for uid, nick in self.participantes.items():
                await conn.execute('''
                    INSERT INTO ranking (user_id, nick, pontos) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET pontos = ranking.pontos + $3, nick = $2
                ''', uid, nick, pts)
            await conn.close()
            
            await self.log_auditoria("💰 Pontos Pagos", f"Evento: {nome}\nPlayers: {len(self.participantes)}", 0x27ae60)
            
            canal_pts = self.get_channel(CANAL_PONTOS_ID)
            if canal_pts:
                await canal_pts.send(f"✅ **{nome}** finalizado! **{len(self.participantes)}** players ganharam **{pts}** pts.")
        except Exception as e:
            print(f"Erro ao pagar: {e}")
        finally:
            self.participantes = {}
            self.lista_ativa = None

    async def scheduler(self):
        await self.wait_until_ready()
        print(f"⏰ Scheduler iniciado.")
        while not self.is_closed():
            try:
                now = datetime.now(TIMEZONE)
                hora_atual = now.strftime("%H:%M")
                canal_pres = self.get_channel(CANAL_PRESENCA_ID)

                for nome, h_boss, dias, pts, emoji in eventos:
                    if dias and now.weekday() not in dias: continue
                    
                    h, m = map(int, h_boss.split(":"))
                    dt_boss = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    t_abrir = (dt_boss - timedelta(minutes=5)).strftime("%H:%M")
                    t_fechar = (dt_boss + timedelta(minutes=10)).strftime("%H:%M")

                    if hora_atual == t_abrir and self.lista_ativa != nome:
                        self.lista_ativa = nome
                        self.participantes = {}
                        emb = discord.Embed(title=f"{emoji} LISTA ABERTA: {nome}", description="Clique no botão abaixo!", color=0x00FF00)
                        self.mensagem_lista = await canal_pres.send(content="@everyone", embed=emb, view=PresencaView(self))

                    if hora_atual == t_fechar and self.lista_ativa == nome:
                        await self.distribuir_pontos(nome, pts)
            except Exception as e:
                print(f"Erro loop: {e}")
            await asyncio.sleep(30)

# ==============================
# 🎮 COMANDOS
# ==============================
client = MaratonaBot()

@client.event
async def on_ready():
    print(f"🚀 {client.user} ONLINE!")

@client.event
async def on_message(message):
    if message.author.bot: return

    if message.content == "!testar" and message.author.guild_permissions.administrator:
        canal = client.get_channel(CANAL_PRESENCA_ID)
        if canal:
            client.lista_ativa = "Teste Manual"
            client.participantes = {}
            emb = discord.Embed(title="🧪 TESTE", description="Clique no botão abaixo!", color=0x00FFFF)
            client.mensagem_lista = await canal.send(embed=emb, view=PresencaView(client))
        else:
            await message.channel.send("❌ Canal de presença não encontrado.")

    if message.content == "!ranking":
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            rows = await conn.fetch("SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 20")
            await conn.close()
            emb = discord.Embed(title="🏆 RANKING", color=0xFFD700)
            txt = "\n".join([f"**{i+1}º** {r['nick']} — `{r['pontos']} pts`" for i, r in enumerate(rows)]) if rows else "Ranking ainda vazio."
            emb.description = txt
            await message.channel.send(embed=emb)
        except Exception as e:
            await message.channel.send(f"Erro ao ler ranking: {e}")

client.run(TOKEN)
