from bs4 import BeautifulSoup
import aiohttp
import asyncio
import re
import os
import aiofiles
import psycopg2

# Configuration de la connexion PostgreSQL
db_config = {
    "dbname": "poke",
    "user": "postgres",
    "password": "postgre",
    "host": "localhost",
    "port": "5432",
}

# Connexion à la base de données PostgreSQL
conn = psycopg2.connect(**db_config)
cur = conn.cursor()

# Nettoyage et création des tables
cur.execute(
    """
DROP TABLE IF EXISTS tournament CASCADE;
DROP TABLE IF EXISTS players CASCADE;
DROP TABLE IF EXISTS deck CASCADE;
DROP TABLE IF EXISTS cartes CASCADE;
DROP TABLE IF EXISTS player_names CASCADE;
DROP TABLE IF EXISTS matchs CASCADE;
"""
)

cur.execute(
    """
CREATE TABLE tournament (
    tournament_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lien TEXT,
    date TEXT,
    organisateur TEXT,
    nb_players INTEGER
);

CREATE TABLE player_names (
    player_id SERIAL PRIMARY KEY,
    player_name TEXT UNIQUE NOT NULL
);

CREATE TABLE matchs (
    tournament_id TEXT NOT NULL,
    joueur1_id INTEGER NOT NULL,
    score1 INTEGER,
    joueur2_id INTEGER NOT NULL,
    score2 INTEGER,
    FOREIGN KEY (joueur1_id) REFERENCES player_names(player_id),
    FOREIGN KEY (joueur2_id) REFERENCES player_names(player_id),
    FOREIGN KEY (tournament_id) REFERENCES tournament(tournament_id)
);

CREATE TABLE players (
    tournament_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    "placing" TEXT,
    win INTEGER DEFAULT 0,
    lose INTEGER DEFAULT 0,
    draw INTEGER DEFAULT 0,
    country TEXT,
    has_decklist BOOLEAN DEFAULT FALSE,
    deck_lien TEXT,
    FOREIGN KEY (player_id) REFERENCES player_names(player_id),
    FOREIGN KEY (tournament_id) REFERENCES tournament(tournament_id)
);

CREATE TABLE cartes (
    carte_id SERIAL PRIMARY KEY,
    nom TEXT NOT NULL,
    type_carte TEXT,
    type_pokemon TEXT,
    PV TEXT,
    stade TEXT,
    evol_from TEXT,
    abilite BOOLEAN DEFAULT FALSE,
    faiblesse TEXT,
    version TEXT,
    code_version TEXT,
    url TEXT UNIQUE
);

CREATE TABLE deck (
    tournament_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    type TEXT,
    nom TEXT,
    quantite INTEGER DEFAULT 1,
    carte_id INTEGER,
    FOREIGN KEY (player_id) REFERENCES player_names(player_id),
    FOREIGN KEY (carte_id) REFERENCES cartes(carte_id),
    FOREIGN KEY (tournament_id) REFERENCES tournament(tournament_id)
);
"""
)

conn.commit()

urls_cartes_traitees = set()
carte_cache_ram = {}


# Fonction pour obtenir ou créer un ID de joueur
def get_or_create_player_id(player_name):
    cur.execute(
        "SELECT player_id FROM player_names WHERE player_name = %s", (player_name,)
    )
    res = cur.fetchone()
    if res:
        return res[0]
    cur.execute(
        "INSERT INTO player_names (player_name) VALUES (%s) RETURNING player_id",
        (player_name,),
    )
    conn.commit()
    return cur.fetchone()[0]


# Fonction pour obtenir l'ID de la carte à partir de l'URL
def get_carte_id_by_url(url):
    cur.execute("SELECT carte_id FROM cartes WHERE url = %s", (url,))
    row = cur.fetchone()
    return row[0] if row else None


# Fonction asynchrone pour récupérer le contenu HTML d'une URL
async def async_soup_from_url(session, sem, url, use_cache=True):
    if url is None:
        return None

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    safe_filename = re.sub(r"[^a-zA-Z0-9]", "_", url)
    cache_filepath = os.path.join(cache_dir, f"cache_{safe_filename}.html")

    html = ""
    if use_cache and os.path.isfile(cache_filepath):
        async with sem:
            async with aiofiles.open(cache_filepath, "r", encoding="utf-8") as file:
                html = await file.read()
    else:
        async with sem:
            async with session.get(url) as resp:
                html = await resp.text()
            async with aiofiles.open(cache_filepath, "w", encoding="utf-8") as file:
                await file.write(html)

    return BeautifulSoup(html, "html.parser")


# Fonction pour extraire les lignes de tableau (tr) d'une table spécifique
def extract_trs(soup, table_class):
    table = soup.find(class_=table_class)
    if not table:
        return []
    trs = table.find_all("tr")
    return trs[1:] if len(trs) > 1 else []


# Regex pour les URLs spécifiques
regex_standings_url = re.compile(r"/tournament/[\w\-]+/standings")
regex_player_id = re.compile(r"/tournament/[\w\-]+/player/[\w_]+")
regex_decklist_url = re.compile(r"/tournament/[\w\-]+/player/[\w_]+/decklist")
regex_tournament_id = re.compile(r"[a-zA-Z0-9_\-]*")


# Fonction asynchrone pour scraper les cartes
async def carte_scrap(session, sem, url):
    if url in carte_cache_ram:
        return carte_cache_ram[url]
    if url in urls_cartes_traitees:
        return []
    urls_cartes_traitees.add(url)
    carte = []
    soup = await async_soup_from_url(session, sem, url)
    if not soup:
        return []

    evo_block = soup.find("p", class_="card-text-type")
    titre = soup.find("p", class_="card-text-title")

    if not evo_block or not titre:
        return []

    if "Trainer" in evo_block.text:
        nom_carte = titre.text.strip()
        type_carte = evo_block.text.strip().split()[-1]
        version_bloc = soup.find("span", class_="text-lg")
        version_longue = version_bloc.text.strip() if version_bloc else None
        version_code = None
        version_courte = None
        if version_bloc:
            version_code = re.search(
                r"\((.*?)\)", version_bloc.text.strip().split()[-1]
            )
            version_courte = version_code.group(1) if version_code else None

        carte.append(
            (
                nom_carte,
                type_carte,
                None,
                None,
                None,
                None,
                None,
                None,
                version_longue,
                version_courte,
                url,
            )
        )
    else:
        infos = " ".join(titre.text.split()).split(" - ")
        if len(infos) < 3:
            return []
        nom_pokemon, type_pokemon, vie_pokemon = infos[:3]

        stade_evolution, evol_from = None, None
        type_carte = evo_block.text.strip().split()[0]
        evo_text = " ".join(evo_block.text.split())

        if "Evolves from" in evo_text:
            parts = evo_text.split(" - ")
            if len(parts) > 1:
                stade_evolution = parts[1]
            evol_from = evo_text.split("Evolves from")[-1].strip()
        else:
            parts = evo_text.split(" - ")
            if parts:
                stade_evolution = parts[-1]

        abilite = soup.find("p", class_="card-text-ability-info") is not None
        faiblesse_bloc = soup.find("p", class_="card-text-wrr")
        faiblesse_pokemon = None
        if faiblesse_bloc:
            parts = " ".join(faiblesse_bloc.text.split()).split(" ")
            if len(parts) > 1:
                faiblesse_pokemon = parts[1]

        version_bloc = soup.find("span", class_="text-lg")
        version_longue = version_bloc.text.strip() if version_bloc else None
        version_code = None
        version_courte = None
        if version_bloc:
            version_code = re.search(
                r"\((.*?)\)", version_bloc.text.strip().split()[-1]
            )
            version_courte = version_code.group(1) if version_code else None

        carte.append(
            (
                nom_pokemon,
                type_carte,
                type_pokemon,
                vie_pokemon,
                stade_evolution,
                evol_from,
                abilite,
                faiblesse_pokemon,
                version_longue,
                version_courte,
                url,
            )
        )

    carte_cache_ram[url] = carte
    return carte


# Fonction asynchrone pour scraper les decks des joueurs
async def deck_scrap(session, sem, url, tournament_id, player_id):
    cards_data = []
    soup = await async_soup_from_url(session, sem, url)
    if soup:
        for section in soup.find_all("div", class_="cards"):
            heading = section.find("div", class_="heading")
            if not heading:
                continue
            title = heading.text.strip().split(" ")[0]
            for card in section.find_all("a"):
                parts = card.text.strip().split()
                if not parts:
                    continue
                try:
                    quantite = int(parts[0])
                except ValueError:
                    continue
                nom = " ".join(parts[1:])
                href = card.get("href")
                if href:
                    cards_data.append(
                        (tournament_id, player_id, title, nom, quantite, href)
                    )
    return cards_data


# Fonction asynchrone pour scraper les joueurs d'un tournoi
async def joueurs_scrap(session, sem, url, tournament_id):
    soup = await async_soup_from_url(session, sem, url)
    players_donnees, deck_tasks = [], []
    if soup:
        th_list = soup.find_all("th")
        record_index = None
        for i, th in enumerate(th_list):
            if th.get_text(strip=True) == "Record":
                record_index = i
                break

        if record_index is None:
            record_index = 0

        for player in extract_trs(soup, "striped"):
            tds = player.find_all("td")
            if len(tds) <= record_index:
                continue

            record_value = tds[record_index].get_text(strip=True)
            score = record_value.replace("drop", "0-0-0").split(" - ")
            if len(score) < 3:
                score = ["0", "0", "0"]

            try:
                win, lose, draw = int(score[0]), int(score[1]), int(score[2])
            except ValueError:
                win, lose, draw = 0, 0, 0

            player_name = player.attrs.get("data-name")
            if not player_name:
                continue

            player_link = player.find("a", {"href": regex_player_id})
            if not player_link:
                continue

            player_id_lien = player_link.attrs["href"].split("/")[4]
            player_id = get_or_create_player_id(player_name)
            deck_anchor = player.find("a", {"href": regex_decklist_url})
            deck_lien = None
            if deck_anchor:
                deck_lien = f"https://play.limitlesstcg.com/tournament/{tournament_id}/player/{player_id_lien}/decklist"
                deck_tasks.append(
                    deck_scrap(session, sem, deck_lien, tournament_id, player_id)
                )

            players_donnees.append(
                (
                    tournament_id,
                    player_id,
                    player.attrs.get("data-placing", -1),
                    win,
                    lose,
                    draw,
                    player.attrs.get("data-country", None),
                    deck_anchor is not None,
                    deck_lien,
                )
            )
    decks_data = await asyncio.gather(*deck_tasks)
    return players_donnees, [card for sublist in decks_data for card in sublist]


def extract_previous_pairings_urls(pairings: BeautifulSoup):
    pairing_urls = pairings.find(class_="mini-nav")

    if pairing_urls is None:
        return []

    pairing_urls = pairing_urls.find_all("a")

    # Remove current page (last one)
    pairing_urls.pop(-1)

    base_url = "https://play.limitlesstcg.com"
    return [base_url + a.attrs["href"] for a in pairing_urls]


def is_bracket_pairing(pairings: BeautifulSoup):
    return pairings.find("div", class_="live-bracket") is not None


async def extract_matches(
    session: aiohttp.ClientSession, sem: asyncio.Semaphore, tournament_id: str
) -> list[tuple]:
    matches = []
    last_pairings = await async_soup_from_url(
        session,
        sem,
        f"https://play.limitlesstcg.com/tournament/{tournament_id}/pairings",
    )
    previous_pairings_urls = extract_previous_pairings_urls(last_pairings)

    pairings = await asyncio.gather(
        *[async_soup_from_url(session, sem, url) for url in previous_pairings_urls]
    )
    pairings.append(last_pairings)

    for pairing in pairings:
        if is_bracket_pairing(pairing):
            matches += extract_matches_from_bracket_pairings(pairing, tournament_id)
        elif is_table_pairing(pairing):
            matches += extract_matches_from_table_pairings(pairing, tournament_id)
        else:
            raise Exception("Unrecognized pairing type")

    return matches


def is_table_pairing(pairings: BeautifulSoup):
    pairings = pairings.find("div", class_="pairings")
    if pairings is not None:
        table = pairings.find("table", {"data-tournament": regex_tournament_id})
        if table is not None:
            return True

    return False


def extract_matches_from_table_pairings(
    pairings: BeautifulSoup, tournament_id: str
) -> list[tuple]:
    matches = []
    matches_tr = pairings.find_all("tr", {"data-completed": "1"})

    for match in matches_tr:
        p1 = match.find("td", class_="p1")
        p2 = match.find("td", class_="p2")

        if p1 is not None and p2 is not None:
            name1 = p1.attrs["data-id"]
            name2 = p2.attrs["data-id"]
            score1 = int(p1.attrs["data-count"])
            score2 = int(p2.attrs["data-count"])

            player1_id = get_or_create_player_id(name1)
            player2_id = get_or_create_player_id(name2)

            matches.append(
                (
                    tournament_id,
                    player1_id,
                    score1,
                    player2_id,
                    score2,
                )
            )

    return matches


def extract_matches_from_bracket_pairings(
    pairings: BeautifulSoup, tournament_id: str
) -> list[tuple]:
    matches = []

    rounds = pairings.find_all("div", class_="round")
    for round_ in rounds:
        matches_divs = round_.find_all("div", class_="match")

        for match in matches_divs:
            p1 = match.find("div", class_="p1")
            p2 = match.find("div", class_="p2")

            if p1 is not None and p2 is not None:
                name1 = p1.attrs["data-id"]
                name2 = p2.attrs["data-id"]
                score1 = int(p1.attrs["data-count"])
                score2 = int(p2.attrs["data-count"])

                player1_id = get_or_create_player_id(name1)
                player2_id = get_or_create_player_id(name2)

                matches.append(
                    (
                        tournament_id,
                        player1_id,
                        score1,
                        player2_id,
                        score2,
                    )
                )

    return matches


async def tournois_scrap(session, sem):
    first_page = "https://play.limitlesstcg.com/tournaments/completed?game=POCKET&format=STANDARD&platform=all&type=online&time=all"
    soup = await async_soup_from_url(session, sem, first_page)
    if not soup:
        return

    pagination = soup.find("ul", class_="pagination")
    max_page = 1
    if pagination:
        max_page = int(pagination.attrs.get("data-max", 1))

    tournament_data, player_data, deck_data, cartes_data, matchs_data = (
        [],
        [],
        [],
        [],
        [],
    )

    for page in range(1, max_page + 1):
        page_url = f"{first_page}&page={page}"
        print(f"Page {page} : {page_url}")
        soup = await async_soup_from_url(session, sem, page_url)
        if not soup:
            continue

        trs = extract_trs(soup, "completed-tournaments")

        tasks_joueurs = []
        tournoi_temp_data = []
        tournoi_ids = []

        for tr in trs:
            standings_link = tr.find("a", {"href": regex_standings_url})
            if not standings_link:
                continue

            tournament_id = standings_link.attrs["href"].split("/")[2]
            lien = f"https://play.limitlesstcg.com/tournament/{tournament_id}/standings?players"

            tournoi_temp_data.append(
                (
                    tournament_id,
                    tr.attrs.get("data-name", ""),
                    lien,
                    tr.attrs.get("data-date", ""),
                    tr.attrs.get("data-organizer", ""),
                    tr.attrs.get("data-players", 0),
                )
            )
            tournoi_ids.append(tournament_id)
            tasks_joueurs.append(joueurs_scrap(session, sem, lien, tournament_id))

        tournament_data.extend(tournoi_temp_data)

        results = await asyncio.gather(*tasks_joueurs)

        all_carte_urls = []
        for pdata, ddata in results:
            player_data.extend(pdata)
            deck_data.extend(ddata)
            carte_urls = [url for *_, url in ddata if url]
            all_carte_urls.extend(carte_urls)

        carte_tasks = [carte_scrap(session, sem, url) for url in all_carte_urls]
        cartes_groupes = await asyncio.gather(*carte_tasks)
        for cartes in cartes_groupes:
            cartes_data.extend(cartes)

        tasks_matchs = [extract_matches(session, sem, tid) for tid in tournoi_ids]
        matchs_groupes = await asyncio.gather(*tasks_matchs)
        for matchs in matchs_groupes:
            matchs_data.extend(matchs)

    if cartes_data:
        cur.executemany(
            "INSERT INTO cartes (nom, type_carte, type_pokemon, PV, stade, evol_from, abilite, faiblesse, version, code_version, url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING",
            cartes_data,
        )
        conn.commit()

    deck_data_final = []
    for row in deck_data:
        if len(row) < 6:
            continue
        tournament_id, player_id, type_carte, nom, quantite, url = row
        carte_id = get_carte_id_by_url(url)
        if carte_id is not None:
            deck_data_final.append(
                (tournament_id, player_id, type_carte, nom, quantite, carte_id)
            )

    await insert_data(tournament_data, player_data, deck_data_final, matchs_data)

    return tournament_data, player_data, deck_data_final, cartes_data, matchs_data


async def insert_data(tournament_data, player_data, deck_data, matchs_data):
    with conn.cursor() as cur:
        for data in tournament_data:
            cur.execute(
                """
                INSERT INTO tournament (tournament_id, name, lien, date, organisateur, nb_players)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tournament_id) DO NOTHING
            """,
                data,
            )

        cur.executemany(
            """
            INSERT INTO players (tournament_id, player_id, "placing", win, lose, draw, country, has_decklist, deck_lien)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            player_data,
        )

        cur.executemany(
            """
            INSERT INTO deck (tournament_id, player_id, type, nom, quantite, carte_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            deck_data,
        )

        cur.executemany(
            """
            INSERT INTO matchs (tournament_id, joueur1_id, score1, joueur2_id, score2)
            VALUES (%s, %s, %s, %s, %s)
        """,
            matchs_data,
        )

        conn.commit()


async def main():
    sem = asyncio.Semaphore(1000)
    try:
        async with aiohttp.ClientSession() as session:
            await tournois_scrap(session, sem)
    except Exception as e:
        print(f"Erreur lors de l'exécution: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
