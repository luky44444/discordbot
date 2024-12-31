import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
import sqlite3
import asyncio
import time
from datetime import datetime
import pytz

intents = discord.Intents.default()
intents.messages = True
client = commands.Bot(command_prefix="!", intents=intents)

url_template = "https://api.gtacnr.net/cnr/players?serverId="
servers = ["EU1", "EU2", "US1", "US2", "SEA"]


def convert_timestamp(iso_timestamp):
    try:
        # Odstraníme nadbytečné milisekundy (ponecháme max. 6 číslic)
        if "." in iso_timestamp:
            main, fraction = iso_timestamp.split(".")
            fraction = fraction[:6]  # Ponechat max. 6 číslic
            iso_timestamp = f"{main}.{fraction}"

        # Převeď timestamp na UTC datetime objekt
        utc_dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))

        # Nastav lokální časovou zónu
        local_tz = pytz.timezone("Europe/Prague")  # Změň na svou časovou zónu, pokud je jiná
        local_dt = utc_dt.astimezone(local_tz)

        # Převeď datetime objekt do čitelného formátu
        return local_dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception as e:
        return f"Neplatný časový formát: {e}"


def get_db_connection():
    try:
        conn = sqlite3.connect(r"C:\Users\lukyn\PycharmProjects\pythonProject1\fivem\+1\withdatabase\players.db")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Chyba při připojování k databázi: {e}")
        return None


def get_unique_db_connection():
    try:
        conn = sqlite3.connect(r"C:\Users\lukyn\PycharmProjects\pythonProject1\fivem\+1\withdatabase\unique_players.db")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Chyba při připojování k databázi: {e}")
        return None


def create_unique_players_table():
    conn = get_unique_db_connection()
    if conn is None:
        return
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS unique_players (
        username TEXT PRIMARY KEY,
        uid TEXT,
        last_server TEXT,
        last_seen TEXT
    )
    """)
    conn.commit()
    conn.close()


def add_or_update_unique_player(username, uid, server):
    conn = get_unique_db_connection()
    if conn is None:
        print("Nepodařilo se připojit k databázi.")
        return
    cursor = conn.cursor()

    # Získání aktuálního času z počítače ve formátu 'YYYY-MM-DD HH:MM:SS'
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Kontrola existence hráče podle UID
        cursor.execute("SELECT * FROM unique_players WHERE uid = ?", (uid,))
        existing_player = cursor.fetchone()

        if existing_player:
            # Pokud existuje, zkontrolujeme změnu jména
            existing_username = existing_player["username"]
            if username != existing_username:
                # Pokud už jsou uložena dvě jména, přidáme nové jméno
                names = existing_username.split(" / ")  # Očekáváme oddělení jmen pomocí " / "
                if username not in names:
                    if len(names) >= 2:
                        # Nahraďme starší jméno novým
                        names[0] = names[1]  # Posuňme druhé jméno na místo prvního
                        names[1] = username  # Nahraďme druhé jméno novým
                    else:
                        # Přidej nové jméno
                        names.append(username)

                    # Aktualizace uložených jmen
                    updated_usernames = " / ".join(names)
                    cursor.execute(""" 
                        UPDATE unique_players 
                        SET username = ?, last_server = ?, last_seen = ? 
                        WHERE uid = ? 
                    """, (updated_usernames, server, current_time, uid))
                else:
                    # Jméno se nezměnilo, aktualizujeme jen server a čas
                    cursor.execute(""" 
                        UPDATE unique_players 
                        SET last_server = ?, last_seen = ? 
                        WHERE uid = ? 
                    """, (server, current_time, uid))
            else:
                # Pokud jméno odpovídá, aktualizujeme jen server a čas
                cursor.execute(""" 
                    UPDATE unique_players 
                    SET last_server = ?, last_seen = ? 
                    WHERE uid = ? 
                """, (server, current_time, uid))
        else:
            # Pokud hráč neexistuje, přidáme nový záznam
            print(f"Přidávám nového hráče: {username}, server: {server}, čas: {current_time}")
            cursor.execute(""" 
                INSERT INTO unique_players (username, uid, last_server, last_seen) 
                VALUES (?, ?, ?, ?) 
            """, (username, uid, server, current_time))

        conn.commit()
    except Exception as e:
        print(f"Chyba při práci s databází: {e}. Jméno: {username}")
    finally:
        conn.close()


def update_unique_players_table():
    conn = get_unique_db_connection()
    if conn is None:
        return
    cursor = conn.cursor()

    # Přidání sloupce last_server, pokud neexistuje
    try:
        cursor.execute("ALTER TABLE unique_players ADD COLUMN last_server TEXT")
        print("Sloupec 'last_server' byl přidán.")
    except sqlite3.OperationalError:
        print("Sloupec 'last_server' již existuje.")

    # Přidání sloupce last_seen, pokud neexistuje
    try:
        cursor.execute("ALTER TABLE unique_players ADD COLUMN last_seen TEXT")
        print("Sloupec 'last_seen' byl přidán.")
    except sqlite3.OperationalError:
        print("Sloupec 'last_seen' již existuje.")

    conn.commit()
    conn.close()


def create_tables_if_not_exist():
    conn = get_db_connection()
    if conn is None:
        return
    cursor = conn.cursor()

    for server in servers:
        # Zkontroluj, zda tabulka již existuje, a přidej sloupec 'uid', pokud neexistuje
        cursor.execute(f"PRAGMA table_info({server})")
        columns = cursor.fetchall()
        if not any(column[1] == "uid" for column in columns):
            cursor.execute(f"ALTER TABLE {server} ADD COLUMN uid TEXT")
            conn.commit()
            print(f"Sloupec 'uid' přidán do tabulky {server}.")

        # Vytvoření tabulky, pokud neexistuje, s přidáním 'uid'
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {server} (username TEXT, uid TEXT, last_updated INTEGER)")
        conn.commit()
        print(f"Tabulka {server} byla vytvořena (pokud neexistovala).")

    conn.close()


def add_last_updated_column():
    conn = get_db_connection()
    if conn is None:
        return
    cursor = conn.cursor()

    for server in servers:
        cursor.execute(f"PRAGMA table_info({server})")
        columns = cursor.fetchall()

        if not any(column[1] == "last_updated" for column in columns):
            cursor.execute(f"ALTER TABLE {server} ADD COLUMN last_updated INTEGER")
            conn.commit()
            print(f"Sloupec 'last_updated' přidán do tabulky {server}.")

    conn.close()


async def save_data():
    conn = get_db_connection()
    if conn is None:
        return
    cursor = conn.cursor()

    update_unique_players_table()

    create_tables_if_not_exist()
    add_last_updated_column()

    for server in servers:
        url = f"{url_template}{server}"
        response = requests.get(url)
        await asyncio.sleep(2)
        cursor.execute(f"DELETE FROM {server}")
        print(f"Tabulka {server} byla vymazána")
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                print(f"Chyba při dekódování JSON z {url}: {response.text}")
                continue
        else:
            print(f"Chyba: Server na {url} vrátil stavový kód {response.status_code}")
            continue

        for item in data:
            username = item["Username"]["Username"]
            uid = item["Uid"]
            timestamp = item["Username"]["Timestamp"]  # ISO8601 formát
            cursor.execute(f"INSERT INTO {server} (username, uid, last_updated) VALUES (?, ?, ?)",
                           (username, uid, int(time.time())))

            # Přidání nebo aktualizace unikátního hráče
            add_or_update_unique_player(username, uid, server)

        conn.commit()
        print(f"Data pro server {server} byla uložena.")
        await asyncio.sleep(2)

    conn.close()


def get_last_updated(server):
    conn = get_db_connection()
    if conn is None:
        return "Chyba připojení k databázi"
    cursor = conn.cursor()
    cursor.execute(f"SELECT last_updated FROM {server} ORDER BY last_updated DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    if result:
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result['last_updated']))
    return "Není k dispozici"


def search_player(name, server):
    conn = get_db_connection()
    if conn is None:
        return []
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {server} WHERE username LIKE ?", (f"%{name}%",))
    results = cursor.fetchall()
    conn.close()
    return results


# Pravidelný update dat každou minutu
@tasks.loop(minutes=0.5)
async def update_data():
    print("Aktualizuji data...")
    await save_data()


@client.event
async def on_ready():
    print(f"Bot {client.user} byl spuštěn")
    create_unique_players_table()
    await client.tree.sync()
    update_data.start()


@client.tree.command(name="players", description="Shows list of all players on the server")
@app_commands.describe(server="Vyberte server: EU1, EU2, US1, US2, SEA")
async def players(interaction: discord.Interaction, server: str):
    if server.upper() not in servers:
        await interaction.response.send_message("Zadali jste neplatný server", ephemeral=True)
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT username FROM {server}")
        data = cursor.fetchall()
        conn.close()

        if not data:
            await interaction.response.send_message(f"Na serveru {server} není nikdo", ephemeral=True)
            return

        last_updated = get_last_updated(server)
        embeds = []
        for i in range(0, len(data), 25):
            chunk = data[i:i + 25]
            embed = discord.Embed(
                title=f"Seznam všech hráčů na serveru {server} (strana {i // 25 + 1})",
                description=f"Celkový počet hráčů na serveru {server} je {len(data)}\nPoslední aktualizace: {last_updated}",
                color=discord.Color.green()
            )
            for item in chunk:
                username = item["username"]
                embed.add_field(name=username, value="", inline=False)
            embeds.append(embed)

        await interaction.response.send_message(embed=embeds[0])

        for embed in embeds[1:]:
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba: {e}", ephemeral=True)


@client.tree.command(name="search", description="Vyhledává hráče podle uživatelského jména na všech serverech")
@app_commands.describe(name="Uživatelské jméno hráče, které chcete vyhledat")
async def search(interaction: discord.Interaction, name: str):
    try:
        found_players = []

        # Hledání hráčů na všech serverech
        for server in servers:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {server} WHERE username LIKE ?", (f"%{name}%",))
            results = cursor.fetchall()
            conn.close()

            if results:
                for row in results:
                    username = row["username"]
                    uid = row["uid"]
                    found_players.append((server, username, uid))

        # Pokud jsou hráči nalezeni
        if found_players:
            embeds = []
            for i in range(0, len(found_players), 25):
                chunk = found_players[i:i + 25]  # Rozdělení do skupin po 25 hráčích
                embed = discord.Embed(
                    title=f"Výsledky vyhledávání pro '{name}'",
                    description=f"Počet nalezených hráčů: {len(found_players)}",
                    color=discord.Color.blue()
                )

                for server, username, uid in chunk:
                    embed.add_field(
                        name=f"Server: {server}",
                        value=f"**{username}** (UID: {uid})",
                        inline=False
                    )

                embeds.append(embed)

            # Odeslání prvního embedu
            await interaction.response.send_message(embed=embeds[0])

            # Následné odeslání dalších embedů
            for embed in embeds[1:]:
                await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(f"Žádní hráči neobsahují jméno '{name}'", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba: {e}", ephemeral=True)


@client.tree.command(name="clear", description="Smaže všechny zprávy na kanálu")
async def clear(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        await interaction.channel.purge()
        await interaction.response.send_message("Všechny zprávy byly smazány.", delete_after=5)
    else:
        await interaction.response.send_message("Nemáte dostatečná oprávnění pro tento příkaz.", delete_after=5)


@client.tree.command(name="search_unique", description="Vyhledává unikátní hráče podle uživatelského jména")
@app_commands.describe(name="Uživatelské jméno hráče, které chcete vyhledat")
async def search_unique(interaction: discord.Interaction, name: str):
    try:
        conn = get_unique_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM unique_players WHERE username LIKE ?", (f"%{name}%",))
        results = cursor.fetchall()
        conn.close()

        # Zjisti celkový počet hráčů v databázi
        conn = get_unique_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM unique_players")
        total_players = cursor.fetchone()[0]
        conn.close()

        if results:
            embeds = []
            total_results = len(results)
            max_fields = 25  # Maximální počet polí na jeden embed
            for i in range(0, total_results, max_fields):
                embed = discord.Embed(
                    title=f"Výsledky vyhledávání pro '{name}'",
                    description=f"Počet nalezených unikátních hráčů: {total_results}\nCelkový počet hráčů v databázi: {total_players}",
                    color=discord.Color.green()
                )

                for row in results[i:i + max_fields]:
                    last_seen = convert_timestamp(row["last_seen"])  # Převeď timestamp na čitelný formát
                    embed.add_field(
                        name=f"UID: {row['uid']}",
                        value=f"**{row['username']}**\nPoslední server: {row['last_server']}\nPoslední připojení: {last_seen}",
                        inline=False
                    )

                embeds.append(embed)

            # Poslat všechny embedy
            for embed in embeds:
                await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"Žádní unikátní hráči neobsahují jméno '{name}'", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba: {e}", ephemeral=True)


@client.tree.command(name="search_uid", description="Vyhledává unikátní hráče podle UID")
@app_commands.describe(uid="UID hráče, které chcete vyhledat")
async def search_uid(interaction: discord.Interaction, uid: str):
    try:
        conn = get_unique_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM unique_players WHERE uid LIKE ?", (f"%{uid}%",))
        results = cursor.fetchall()
        conn.close()

        if results:
            # Vytvoření embedu
            embed = discord.Embed(
                title=f"Výsledky vyhledávání pro UID '{uid}'",
                description=f"Počet nalezených hráčů: {len(results)}",
                color=discord.Color.blue()
            )

            # Přidání každého hráče do embed message
            for row in results:
                embed.add_field(
                    name=f"UID: {row['uid']}",
                    value=f"**{row['username']}**",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"Žádní hráči neobsahují UID '{uid}'", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba: {e}", ephemeral=True)


@client.tree.command(name="delete_user", description="Smaže unikátního hráče podle jména")
@app_commands.describe(name="Přesné nebo částečné jméno hráče, který chcete smazat")
async def delete_user(interaction: discord.Interaction, name: str):
    try:
        conn = get_unique_db_connection()
        if conn is None:
            await interaction.response.send_message("Chyba při připojení k databázi.", ephemeral=True)
            return

        cursor = conn.cursor()
        # Použijeme LIKE pro částečnou shodu s jménem
        cursor.execute("SELECT * FROM unique_players WHERE username LIKE ?", (f"%{name}%",))
        result = cursor.fetchone()

        if result:
            # Pokud hráč existuje, smažeme ho
            cursor.execute("DELETE FROM unique_players WHERE username LIKE ?", (f"%{name}%",))
            conn.commit()
            await interaction.response.send_message(f"Hráč(s) obsahující jméno '{name}' byl úspěšně smazán.",
                                                    ephemeral=True)
        else:
            # Pokud hráč neexistuje
            await interaction.response.send_message(f"Hráč(s) s jménem obsahujícím '{name}' nebyl nalezen.",
                                                    ephemeral=True)

        conn.close()

    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba při práci s databází: {e}", ephemeral=True)


TOKEN = "token"
client.run(TOKEN)
