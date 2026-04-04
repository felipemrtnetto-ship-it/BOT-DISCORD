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

TIMEZONE = pytz.timezone("America/Sao_Paulo")
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
CANAL_LOGS_ID = 1489805148204040312 

# Lista de Eventos (Configuração Original)
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
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS ranking (
            user_id BIGINT PRIMARY KEY,
            nick TEXT,
            pontos INTEGER DEFAULT 0
        )
    ''')
    await conn.close()

# ==============================
# 🔘 INTERFACE (SISTEMA DE BOTÃO)
# ==============================
class PresencaView(View):
    def __init__(self, bot):
        super().__init__(timeout=None) # Botão nunca expira (persistente)
        self.bot = bot

    @discord.ui.button(label="Marcar Presença", style=discord.ButtonStyle.green, custom_id="btn_presenca_v2", emoji="✅")
    async def marcar_presenca(self, interaction: discord.Interaction):
        if not self.bot.lista_ativa:
            return await interaction.response.send_message("❌ A lista para este evento já foi fechada!", ephemeral=True)
        
        user_id = interaction.user.id
        nick = interaction.user.display_name # Pega o nome do Discord automaticamente

        if user_id in self.bot.participantes:
            return await interaction.response.send_message("⚠️ Você já está nesta lista!", ephemeral=True)

        # Adiciona na memória temporária da lista
        self.bot.participantes[user_id] = nick
        
        # Atualiza a mensagem principal com o novo nome
        await self.bot.atualizar_lista_msg()
        
        await interaction.response.send_message(f"✅ Presença confirmada: **{nick}**", ephemeral=True)

# ==============================
# 🤖 BOT CLIENT PRINCIPAL
# ==============================
class MaratonaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.lista_ativa = None
        self.participantes = {} # {user_id: nick}
        self.mensagem_lista = None
        self.alerta_enviado = False

    async def setup_hook(self):
        # Inicializa DB e recupera o listener do botão
        await init_db()
        self.add_view(PresencaView(self))
        self.loop.create_task(self.scheduler())

    async def log_auditoria(self, titulo, descricao, cor=0x3498db):
        canal = self.get_channel(CANAL_LOGS_ID)
        if canal:
            embed = discord.Embed(title=titulo, description=descricao, color=cor, timestamp=datetime.now(TIMEZONE))
            await canal.send(embed=embed)

    async def atualizar_lista_msg(self):
        if self.mensagem_lista:
            txt = "\n".join([f"• {n}" for n in self.participantes.values()])
            embed = discord.Embed(
                title=f"📋 LISTA: {self.lista_ativa}",
                description=f"Clique no botão abaixo para garantir seus pontos!\n\n**Participantes ({len(self.participantes)}):**\n{txt}",
                color=0x2ecc71
            )
            try:
                await self.mensagem_lista.edit(embed=embed, view=PresencaView(self))
            except: pass

    async def distribuir_pontos(self, nome_evento, pontos_valor):
        if not self.participantes:
            await self.log_auditoria("⚠️ Evento Vazio", f"O evento **{nome_evento}** encerrou sem ninguém na lista.")
            self.lista_ativa = None; return

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            for uid, nick in self.participantes.items():
                # SQL compatível com Postgres (usa $1, $2...)
                await conn.execute('''
                    INSERT INTO ranking (user_id, nick, pontos) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET pontos = ranking.pontos + $3, nick = $2
                ''', uid, nick, pontos_valor)
            
            await self.log_auditoria("💰 Pontos Distribuídos", f"Evento: **{nome_evento}**\nTotal: {len(self.participantes)} players\nPontos: +{pontos_valor}", 0x27ae60)
            
            # Envia confirmação no canal de pontos
            canal_pontos = self.get_channel(CANAL_PONTOS_ID)
            if canal_pontos:
                await canal_pontos.send(f"✅ **{nome_evento}** finalizado! **{len(self.participantes)}** jogadores receberam **{pontos_valor}** pontos.")
        
        finally:
            await conn.close()
            if self.mensagem_lista:
                try: await self.mensagem_lista.delete()
                except: pass
            self.participantes = {}; self.lista_ativa = None; self.alerta_enviado = False

    async def scheduler(self):
        await self.wait_until_ready()
        print(f"⏰ Scheduler iniciado em {TIMEZONE}")
        
        while not self.is_closed():
            try:
                now = datetime.now(TIMEZONE)
                canal_presenca = self.get_channel(CANAL_PRESENCA_ID)
                
                if not canal_presenca:
                    await asyncio.sleep(60); continue

                for nome, hora, dias, pts, emoji in eventos:
                    h, m = map(int, hora.split(":"))
                    ev_hoje = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    
                    if ev_hoje < now - timedelta(hours=1): ev_hoje += timedelta(days=1)
                    if dias and now.weekday() not in dias: continue

                    abrir = ev_hoje - timedelta(minutes=5)
                    alerta = ev_hoje + timedelta(minutes=5)
                    fechar = ev_hoje + timedelta(minutes=10)

                    # 🟢 ABRIR LISTA
                    if abrir <= now <= abrir + timedelta(seconds=45) and not self.lista_ativa:
                        self.lista_ativa = nome
                        self.participantes = {}
                        embed = discord.Embed(
                            title=f"{emoji} LISTA ABERTA: {nome}", 
                            description="Clique no botão abaixo para registrar sua presença!", 
                            color=0x00FF00
                        )
                        self.mensagem_lista = await canal_presenca.send(content="@everyone", embed=embed, view=PresencaView(self))

                    # 🟡 ALERTA 5 MINUTOS
                    if alerta <= now <= alerta + timedelta(seconds=45) and self.lista_ativa == nome and not self.alerta_enviado:
                        self.alerta_enviado = True
                        await canal_presenca.send(f"⚠️ **ATENÇÃO** - A lista de **{nome}** fecha em 5 minutos! Corra!")

                    # 🔴 FECHAR E DISTRIBUIR
                    if fechar <= now <= fechar + timedelta(seconds=45) and self.lista_ativa == nome:
                        await self.distribuir_pontos(nome, pts)

            except Exception as e:
                print(f"Erro no scheduler: {e}")
            
            await asyncio.sleep(40)

# ==============================
# 🎮 COMANDOS
# ==============================
client = MaratonaBot()

@client.event
async def on_ready():
    print(f"🚀 {client.user} ONLINE!")
    print(f"🔗 Conectado ao Postgres do Railway")

@client.event
async def on_message(message):
    if message.author.bot: return

    # --- RANKING PÚBLICO ---
    if message.content == "!ranking":
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch("SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 25")
        await conn.close()

        if not rows:
            return await message.channel.send("Nenhum ponto registrado ainda.")

        embed = discord.Embed(title="🏆 RANKING DA MARATONA", color=0xFFD700)
        txt = ""
        for i, row in enumerate(rows, 1):
            medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"**{i}º**"
            txt += f"{medal} {row['nick']} — `{row['pontos']} pts`\n"
        
        embed.description = txt
        await message.channel.send(embed=embed)

    # --- COMANDO DE TESTE (ADM) ---
    if message.content == "!testar_lista" and message.author.guild_permissions.administrator:
        client.lista_ativa = "Teste Manual"
        client.participantes = {}
        embed = discord.Embed(title="🧪 TESTE DE BOTÃO", description="Clique abaixo para testar o sistema!", color=0x00FFFF)
        client.mensagem_lista = await message.channel.send(embed=embed, view=PresencaView(client))

    # --- LIMPAR RANKING (ADM) ---
    if message.content == "!zerar_tudo" and message.author.guild_permissions.administrator:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("DELETE FROM ranking")
        await conn.close()
        await message.channel.send("⚠️ Ranking completamente zerado!")
        await client.log_auditoria("🚨 RESET GERAL", f"O administrador {message.author.mention} zerou o ranking.")

client.run(TOKEN)
