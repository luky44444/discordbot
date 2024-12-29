import discord
from discord.ext import commands
from discord import app_commands
import requests

intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# URL základy pro servery
url_base = "https://api.gtacnr.net/cnr/players?serverId="

# Seznam dostupných serverů
available_servers = ["EU1", "EU2", "US1", "US2", "SEA"]


@bot.event
async def on_ready():
    print(f"Bot je přihlášen jako {bot.user}")


# Příkaz pro zobrazení všech hráčů na vybraném serveru
@bot.tree.command(name="players", description="Zobrazí seznam všech hráčů na serveru")
@app_commands.describe(server="Vyberte server: EU1, EU2, US1, US2, SEA")
async def players(interaction: discord.Interaction, server: str):
    if server not in available_servers:
        await interaction.response.send_message(
            "Neplatný server. Zadejte jeden z těchto serverů: EU1, EU2, US1, US2, SEA.")
        return

    try:
        url = f"{url_base}{server}"  # Sestavení správné URL pro server
        response = requests.get(url)
        if response.status_code == 200:
            json_data = response.json()

            try:
                names = [item['Username']['Username'] for item in json_data]
                if names:
                    # Vytvoření embedu pro všechny hráče
                    embed_list = []  # List pro uložení více embedů
                    current_embed = discord.Embed(title=f"Seznam hráčů na serveru {server}", color=discord.Color.blue())
                    row_count = 0  # Počítadlo pro počet polí v aktuálním embedu

                    # Generování tabulky: Vkládání jmen hráčů do sloupců (každý řádek má až 5 hráčů)
                    for i in range(0, len(names), 5):
                        row = "\n".join(names[i:i + 5])  # Každých 5 jmen na řádek, oddělené většími mezerami
                        if row_count < 25:  # Pokud počet polí není větší než 25
                            current_embed.add_field(name="\u200b", value=row, inline=False)
                            row_count += 1
                        else:
                            embed_list.append(current_embed)  # Uložení aktuálního embedu
                            current_embed = discord.Embed(title=f"Seznam hráčů na serveru {server}",
                                                          color=discord.Color.blue())  # Vytvoření nového embedu
                            current_embed.add_field(name="\u200b", value=row,
                                                    inline=False)  # Přidání první položky do nového embedu
                            row_count = 1  # Resetování počítadla

                    embed_list.append(current_embed)  # Uložení posledního embedu

                    # Odeslání embedů v dávkách
                    for embed in embed_list:
                        await interaction.response.send_message(embed=embed)

                    # Přidání celkového počtu hráčů na konec
                    await interaction.followup.send(f"Celkový počet hráčů na serveru {server}: {len(names)}")
                else:
                    await interaction.response.send_message("Nenalezeni žádní hráči.")
            except (KeyError, TypeError) as e:
                await interaction.response.send_message(f"Chyba při zpracování dat: {e}")
        else:
            await interaction.response.send_message(f"Chyba API: {response.status_code}")
    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba: {e}")


# Příkaz pro vyhledání hráče na všech serverech
@bot.tree.command(name="search", description="Vyhledá hráče podle uživatelského jména na všech serverech")
@app_commands.describe(username="Uživatelské jméno hráče, které chcete vyhledat")
async def search(interaction: discord.Interaction, username: str):
    try:
        all_found_players = []

        # Prohledávání všech serverů
        for server in available_servers:
            page = 1  # Začínáme na první stránce
            while True:
                url = f"{url_base}{server}&page={page}"  # URL s parametrem pro stránkování
                response = requests.get(url)
                if response.status_code == 200:
                    json_data = response.json()

                    # Pokud jsou hráči na této stránce
                    found_players = [item for item in json_data if
                                     username.lower() in item['Username']['Username'].lower()]
                    for player in found_players:
                        player['Server'] = server  # Přidání serveru, na kterém byl hráč nalezen
                    all_found_players.extend(found_players)

                    # Pokud byla stránka prázdná, znamená to, že jsme dosáhli poslední stránky
                    if len(json_data) == 0:
                        break

                    # Přejdeme na další stránku
                    page += 1
                else:
                    await interaction.response.send_message(f"Chyba API na serveru {server}: {response.status_code}")
                    return

        if all_found_players:
            # Vytvoření embedu pro nalezené hráče
            embed = discord.Embed(title=f"Výsledky hledání pro '{username}' na všech serverech",
                                  color=discord.Color.green())
            for player in all_found_players:
                embed.add_field(name=f"{player['Username']['Username']} - {player['Server']}", value="\u200b",
                                inline=False)

            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"Žádný hráč s částí uživatelského jména '{username}' na žádném serveru nebyl nalezen.")
    except Exception as e:
        await interaction.response.send_message(f"Nastala chyba: {e}")


# Před použitím bot.run() přidejte tento příkaz pro synchronizaci slash commands
@bot.event
async def on_ready():
    # Synchronizace globálních slash commands
    await bot.tree.sync()
    print(f"Bot je přihlášen jako {bot.user}")


TOKEN = "MTMyMjY3MDYzMzcyMDQ4Mzk0MA.GwpgDu.HvTln-u4HAmyaJgWmSnPBjysQyemtTLkUpciGI"
bot.run(TOKEN)
