import streamlit as st
import pandas as pd
import numpy as np
import psycopg2
import os
import altair as alt
import plotly.graph_objects as go
from collections import defaultdict
import plotly.express as px

pg_conn = psycopg2.connect(
    host="localhost",  # ou l’adresse IP de PostgreSQL
    database="poke",
    user="postgres",
    password="postgre",
)
pg_cur = pg_conn.cursor()

st.markdown(
    """
    <div style="text-align: center;">
        <a href="https://developer.android.com/static/images/cards/distribute/stories/pokemon_tcg_pocket_logo.png?hl=fr" target="_blank">
            <img src="https://developer.android.com/static/images/cards/distribute/stories/pokemon_tcg_pocket_logo.png?hl=fr" width="400">
        </a>
    </div>    
    """,
    unsafe_allow_html=True,
)
st.write(" ")
st.markdown(
    "<h1 style='text-align: center;'>Metagame analysis TCGP</h1>",
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["Winrate", "Card usage", "Matchups", "Card versionning"]
)

with tab1:
    st.markdown("<div class='custom-box'>", unsafe_allow_html=True)
    df_top_20 = pd.read_sql_query("""
    select * from (select 
                d.carte_id,
                c.type_carte,c.nom,
                COUNT(d.carte_id) AS count_carte
            FROM
                deck d
                LEFT JOIN (
                    SELECT m.tournament_id, MAX(c.code_version) AS version_max
                    FROM (
                        SELECT t.tournament_id, d.carte_id
                        FROM tournament t 
                        LEFT JOIN deck d ON d.tournament_id = t.tournament_id
                    ) m
                    LEFT JOIN cartes c ON c.carte_id = m.carte_id
                    where c.type_carte = 'Pokémon'
                    GROUP BY m.tournament_id
                ) vet ON d.tournament_id = vet.tournament_id
                LEFT JOIN cartes c ON c.carte_id = d.carte_id
               where c.type_carte = 'Pokémon' and c.carte_id in (  select carte_id from cartes c where c.nom not in (select c2.evol_from from cartes c2 where c2.evol_from is not null group by c2.evol_from) and type_carte ='Pokémon')
            GROUP BY
                d.carte_id,
                c.type_carte,
                c.nom) a 
                order by count_carte desc
                limit 20
    """,pg_conn)

    df_top_20 = (df_top_20.sort_values('count_carte'))['carte_id'].head(20)

    df_winrate = pd.read_sql_query("""select AVG(winrate) as winrate,nom as name,version_max as extension, type_carte as card_type,carte_id as card_id from (SELECT sum(cast(p.lose as float))/(sum(p.win)+sum(p.lose)) as winrate, d.tournament_id,c.nom, e.version_max, c.type_carte,c.carte_id from players p 
    left outer join deck d on (p.player_id = d.player_id and p.tournament_id=d.tournament_id)
    left outer join cartes c on d.carte_id =c.carte_id 
    left join(SELECT m.tournament_id, MAX(c.code_version) AS version_max
                    FROM (
                        SELECT t.tournament_id, d.carte_id
                        FROM tournament t 
                        LEFT JOIN deck d ON d.tournament_id = t.tournament_id
                    ) m
                    LEFT JOIN cartes c ON c.carte_id = m.carte_id
                    GROUP BY m.tournament_id) e on e.tournament_id = d.tournament_id 
    where c.type_carte is not null and (p.lose > 0 or p.win >0)
    group by  d.tournament_id,c.nom,e.version_max, c.type_carte,c.carte_id)a 
    group by nom,version_max, type_carte,carte_id
    """,pg_conn)
    
    st.write("Winrate evolution of the top 20 pokemon by pickrate ")
    df_winrate = df_winrate[df_winrate['card_id'].isin(df_top_20)]
    chart = alt.Chart(df_winrate).mark_line().encode(
        x='extension',
        y='winrate',
        color='name:N',
        tooltip=[
            alt.Tooltip('name', title='Card name'),
            alt.Tooltip('extension', title='Version'),
            alt.Tooltip('winrate', title='winrate', format='.2%')]
    )
    st.altair_chart(chart)
    
    poke_search_input = st.text_input("🔍 Search for a pokemon")
    if poke_search_input=="":
        poke_search = ""
    else:
        poke_search=poke_search_input
    df_winrate_output = df_winrate[df_winrate['name'].str.contains(poke_search, case=False, na=False)]
    df_winrate_output = df_winrate_output.drop('card_id',axis=1)
    st.dataframe(df_winrate_output)
with tab2:
    query = """SELECT 
        pv,
        SUM(nb) / CAST((
        SELECT SUM(nb) 
        FROM (
            SELECT * 
            FROM (
                SELECT carte_id, COUNT(*) AS nb 
                FROM deck 
                GROUP BY carte_id
            ) a
            LEFT JOIN cartes c ON c.carte_id = a.carte_id
            WHERE type_carte = 'Pokémon'
        ) AS total_sub
    ) AS FLOAT) * 100 AS rate
    FROM (
        SELECT * 
        FROM (
            SELECT carte_id, COUNT(*) AS nb 
            FROM deck 
            GROUP BY carte_id
        ) a
        LEFT JOIN cartes c ON c.carte_id = a.carte_id
        WHERE type_carte = 'Pokémon'
    ) AS data
    GROUP BY pv
    ORDER BY rate DESC; """
    # Exécution de la requête et chargement directe dans un DataFrame
    df = pd.read_sql(query, pg_conn)
    df = df.sort_values("rate", ascending=False)
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("pv:N", sort=df["pv"].tolist(), title="HP"),  # ordre forcé
            y=alt.Y("rate:Q", title="Usage rate"),
            tooltip=["pv", "rate"],
        )
        .properties(width=700, height=400, title="Pokemon Usage by HP")
    )

    # Affichage dans Streamlit
    st.altair_chart(chart, use_container_width=True)

    query = """SELECT 
        faiblesse as weakness,
        SUM(nb) / CAST((
        SELECT SUM(nb) 
        FROM (
            SELECT * 
            FROM (
                SELECT carte_id, COUNT(*) AS nb 
                FROM deck 
                GROUP BY carte_id
            ) a
            LEFT JOIN cartes c ON c.carte_id = a.carte_id
            WHERE type_carte = 'Pokémon'
        ) AS total_sub
    ) AS FLOAT) * 100 AS rate
    FROM (
        SELECT * 
        FROM (
            SELECT carte_id, COUNT(*) AS nb 
            FROM deck 
            GROUP BY carte_id
        ) a
        LEFT JOIN cartes c ON c.carte_id = a.carte_id
        WHERE type_carte = 'Pokémon'
    ) AS data
    GROUP BY faiblesse
    ORDER BY rate DESC; """
    # Exécution de la requête et chargement directe dans un DataFrame
    df = pd.read_sql(query, pg_conn)
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(
                "weakness:N", sort=df["weakness"].tolist(), title="weakness"
            ),  # ordre forcé
            y=alt.Y("rate:Q", title="Usage rate"),
            tooltip=["weakness", "rate"],
        )
        .properties(width=700, height=400, title="Pokemon usage by weakness")
    )

    # Affichage dans Streamlit
    st.altair_chart(chart, use_container_width=True)

    query = """SELECT 
        type_pokemon,
        SUM(nb) / CAST((
        SELECT SUM(nb) 
        FROM (
            SELECT * 
            FROM (
                SELECT carte_id, COUNT(*) AS nb 
                FROM deck 
                GROUP BY carte_id
            ) a
            LEFT JOIN cartes c ON c.carte_id = a.carte_id
            WHERE type_carte = 'Pokémon'
        ) AS total_sub
    ) AS FLOAT) * 100 AS rate
    FROM (
        SELECT * 
        FROM (
            SELECT carte_id, COUNT(*) AS nb 
            FROM deck 
            GROUP BY carte_id
        ) a
        LEFT JOIN cartes c ON c.carte_id = a.carte_id
        WHERE type_carte = 'Pokémon'
    ) AS data
    GROUP BY type_pokemon
    ORDER BY rate DESC; """
    # Exécution de la requête et chargement directe dans un DataFrame
    df = pd.read_sql(query, pg_conn)
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(
                "type_pokemon:N", sort=df["type_pokemon"].tolist(), title="type"
            ),  # ordre forcé
            y=alt.Y("rate:Q", title="Usage rate"),
            tooltip=["type_pokemon", "rate"],
        )
        .properties(width=700, height=400, title="Pokemon usage by type")
    )

    # Affichage dans Streamlit
    st.altair_chart(chart, use_container_width=True)

with tab3:
    poke_names = pd.read_sql_query("SELECT * from cartes c where c.nom not in (select c2.evol_from from cartes c2 WHERE c2.evol_from IS NOT NULL group by c2.evol_from) and type_carte = 'Pokémon'", pg_conn)['nom'].tolist()
    
    # Selectbox pour choisir un Pokémon
    poke_search2 = st.selectbox("🔍 Research a pokemon", poke_names)
    
    matchups_query  ="""
      WITH decks_pokemon AS (
      SELECT
        d.tournament_id,
        d.player_id,
        c.nom AS carte
      FROM deck d
      LEFT JOIN cartes c ON c.carte_id = d.carte_id
      WHERE d."type" = 'Pokémon'
        AND c.nom NOT IN (
          SELECT c2.evol_from FROM cartes c2 WHERE c2.evol_from IS NOT NULL GROUP BY c2.evol_from
        )
    ),
    match_cartes AS (
      -- Cartes jouées par joueur1 avec résultat
      SELECT
        m.tournament_id,
        dp1.carte AS carte1,
        dp2.carte AS carte2,
        CASE 
          WHEN m.score1 > m.score2 THEN 1
          WHEN m.score1 < m.score2 THEN 0
          ELSE NULL
        END AS carte1_win
      FROM matchs m
      JOIN decks_pokemon dp1 ON m.joueur1_id = dp1.player_id AND m.tournament_id = dp1.tournament_id
      JOIN decks_pokemon dp2 ON m.joueur2_id = dp2.player_id AND m.tournament_id = dp2.tournament_id
    
      UNION ALL
    
      -- Cartes jouées par joueur2 avec résultats inversés
      SELECT
        m.tournament_id,
        dp2.carte AS carte1,
        dp1.carte AS carte2,
        CASE 
          WHEN m.score2 > m.score1 THEN 1
          WHEN m.score2 < m.score1 THEN 0
          ELSE NULL
        END AS carte1_win
      FROM matchs m
      JOIN decks_pokemon dp1 ON m.joueur1_id = dp1.player_id AND m.tournament_id = dp1.tournament_id
      JOIN decks_pokemon dp2 ON m.joueur2_id = dp2.player_id AND m.tournament_id = dp2.tournament_id
    ),
    stats AS (
      SELECT
        carte1,
        carte2,
        COUNT(*) AS nb_matchs,
        SUM(carte1_win) AS victoires_carte1
      FROM match_cartes
      WHERE carte1_win IS NOT NULL
      GROUP BY carte1, carte2
    )
    SELECT
      carte1 as card,
      carte2 as oponent,
      nb_matchs as games,
      victoires_carte1 as wins,
      ROUND((victoires_carte1::DECIMAL / nb_matchs) * 100, 2) AS winrate
    FROM stats
    ORDER BY nb_matchs DESC, winrate DESC;
    
    """
    
    # Récupération des données de matchups
    df_matchups = pd.read_sql_query(matchups_query, pg_conn)
    
    # Filtrage : on ne garde que les lignes où carte1 == Pokémon sélectionné
    df_matchups_output = df_matchups[df_matchups['card'] == poke_search2]
    
    df_filtered = df_matchups[df_matchups['card'] == poke_search2].copy()
    df_filtered['winrate'] = df_filtered['wins'] / df_filtered['games'] * 100
    df_filtered = df_filtered[df_filtered['games'] >= 8]
    
    # Top 5 & Bottom 5
    df_top5 = df_filtered.sort_values(by='winrate', ascending=False).head(5)
    df_bot5 = df_filtered.sort_values(by='winrate', ascending=True).head(5)
    
    
    #---------------- TOP 5 ----------------
    
    fig_top5 = px.bar(
        df_top5,
        x='oponent',
        y='winrate',
        text='winrate',
        color_discrete_sequence=['#1f77b4'],  # bleu uni
        labels={'oponent': 'oponent', 'winrate': 'Winrate (%)'},
        title=f"Top 5 best matchups for {poke_search2}"
    )
    fig_top5.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    fig_top5.update_layout(yaxis_range=[0, 100])
    
    
    # ---------------- BOTTOM 5 ----------------
    
    fig_bot5 = px.bar(
        df_bot5,
        x='oponent',
        y='winrate',
        text='winrate',
        color_discrete_sequence=['#1f77b4'],  # même bleu
        labels={'oponent': 'oponent', 'winrate': 'Winrate (%)'},
        title=f"Top 5 best answers to {poke_search2}"
    )
    fig_bot5.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    fig_bot5.update_layout(yaxis_range=[0, 100])
   
    
    if df_filtered.empty:
        st.subheader("Not enough data to display graphics !")
    else:
        st.subheader(f"🏆 Top 5 best matchups for {poke_search2}")
        st.plotly_chart(fig_top5)
        st.subheader(f"💀 Top 5 best answers to {poke_search2}")
        st.plotly_chart(fig_bot5)
    # Affichage
    st.write("Whole dataset")
    st.dataframe(df_matchups_output)
with tab4:

    @st.cache_data
    def get_data():
        query = """
        SELECT
            CAST(cartes.carte_id AS VARCHAR) AS carte_id,
            CAST(cartes.version_max AS VARCHAR) AS version_max,
            CAST(cartes.type_carte AS VARCHAR) AS type_carte,
            cartes.nom as name,
            CAST(cartes.count_carte AS FLOAT) / total.count_total AS ratio
        FROM (
            SELECT
                d.carte_id,
                vet.version_max,
                c.type_carte,
                c.nom,
                COUNT(d.carte_id) AS count_carte
            FROM
                deck d
                LEFT JOIN (
                    SELECT m.tournament_id, MAX(c.code_version) AS version_max
                    FROM (
                        SELECT t.tournament_id, d.carte_id
                        FROM tournament t 
                        LEFT JOIN deck d ON d.tournament_id = t.tournament_id
                    ) m
                    LEFT JOIN cartes c ON c.carte_id = m.carte_id
                    GROUP BY m.tournament_id
                ) vet ON d.tournament_id = vet.tournament_id
                LEFT JOIN cartes c ON c.carte_id = d.carte_id
            GROUP BY
                d.carte_id,
                vet.version_max,
                c.type_carte,
                c.nom
        ) AS cartes
        JOIN (
            SELECT
                vet.version_max,
                COUNT(DISTINCT d.player_id || '-' || d.tournament_id) AS count_total
            FROM
                deck d
                LEFT JOIN (
                    SELECT m.tournament_id, MAX(c.code_version) AS version_max
                    FROM (
                        SELECT t.tournament_id, d.carte_id
                        FROM tournament t 
                        LEFT JOIN deck d ON d.tournament_id = t.tournament_id
                    ) m
                    LEFT JOIN cartes c ON c.carte_id = m.carte_id
                    GROUP BY m.tournament_id
                ) vet ON d.tournament_id = vet.tournament_id
            GROUP BY vet.version_max
        ) AS total ON cartes.version_max = total.version_max;
        """
        df = pd.read_sql_query(query, pg_conn)
        df["ratio"] = df["ratio"].astype(float)
        return df

    # Chargement initial
    df = get_data()

    # Filtres dynamiques
    categories = df["type_carte"].dropna().unique()
    choix = st.multiselect(
        "Card type filter :", categories.tolist(), default=categories.tolist()
    )

    # Filtrage instantané
    df_filtre = df[df["type_carte"].isin(choix)]

    # Top 20 par version
    df_top20 = (
        df_filtre.sort_values(["version_max", "ratio"], ascending=[True, False])
        .groupby("version_max")
        .head(20)
        .reset_index(drop=True)
    )

    # Graphique Altair
    line = (
        alt.Chart(df_top20)
        .mark_line(opacity=0.3)
        .encode(
            x=alt.X("version_max:N", title="Extension"),
            y=alt.Y("ratio:Q", title="Usage rate"),
            color="name:N",
            detail="name:N",
        )
    )

    points = (
        alt.Chart(df_top20)
        .mark_circle(size=60)
        .encode(
            x="version_max:N",
            y="ratio:Q",
            color="name:N",
            tooltip=[
                alt.Tooltip("name", title="Name"),
                alt.Tooltip("version_max", title="Version"),
                alt.Tooltip("ratio", title="Usage %", format=".2%"),
            ],
        )
    )

    chart = (
        (line + points)
        .properties(
            width=800,
            height=450,
            title="Usage rate of the most picked cards (top 20)",
        )
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)

    @st.cache_data
    def get_data_top5_cumul():
        query = (
            query
        ) = """
        SELECT
        CAST(cartes.carte_id AS VARCHAR) AS carte_id,
        CAST(cartes.version_max AS VARCHAR) AS version_max,
        CAST(cartes.type_carte AS VARCHAR) AS type_carte,
        cartes.nom as name,
        CAST(cartes.count_carte AS FLOAT) / total.count_total AS ratio
    FROM
        (
            SELECT
                d.carte_id,
                vet.version_max,
                c.type_carte,c.nom,
                COUNT(d.carte_id) AS count_carte
            FROM
                deck d
                LEFT JOIN (
                    SELECT m.tournament_id, MAX(c.code_version) AS version_max
                    FROM (
                        SELECT t.tournament_id, d.carte_id
                        FROM tournament t 
                        LEFT JOIN deck d ON d.tournament_id = t.tournament_id
                    ) m
                    LEFT JOIN cartes c ON c.carte_id = m.carte_id
                    GROUP BY m.tournament_id
                ) vet ON d.tournament_id = vet.tournament_id
                LEFT JOIN cartes c ON c.carte_id = d.carte_id
            GROUP BY
                d.carte_id,
                vet.version_max,
                c.type_carte,
                c.nom
        ) AS cartes
    JOIN
        (
            SELECT
                vet.version_max,
                COUNT(DISTINCT d.player_id || '-' || d.tournament_id) AS count_total
            FROM
                deck d
                LEFT JOIN (
                    SELECT m.tournament_id, MAX(c.code_version) AS version_max
                    FROM (
                        SELECT t.tournament_id, d.carte_id
                        FROM tournament t 
                        LEFT JOIN deck d ON d.tournament_id = t.tournament_id
                    ) m
                    LEFT JOIN cartes c ON c.carte_id = m.carte_id
                    GROUP BY m.tournament_id
                ) vet ON d.tournament_id = vet.tournament_id
            GROUP BY
                vet.version_max
        ) AS total
    ON cartes.version_max = total.version_max;
        """
        df = pd.read_sql_query(
            query,
            pg_conn,
            dtype={
                "carte_id": "string",
                "version_max": "string",
                "type_carte": "string",
                "name": "string",
            },
        )
        df["ratio"] = df["ratio"].astype(float)
        return df

    # Chargement des données
    df_top5_all = get_data_top5_cumul()

    # 2. Filtres utilisateur
    # Filtre type de carte
    type_carte_list = df_top5_all["type_carte"].unique()
    type_carte_select = st.multiselect(
        "Card type filter", type_carte_list, default=type_carte_list
    )

    # Filtre version de départ (top 5)
    version_list = sorted(df_top5_all["version_max"].unique())
    version_select = st.multiselect(
        "Extensions used to detect top 5",
        version_list,
        default=version_list,
    )

    # 3. Application du filtre sur les types de cartes (mais pas sur les versions)
    df_top5_filtre = df_top5_all[df_top5_all["type_carte"].isin(type_carte_select)]

    # 4. Top 5 par version sélectionnée
    df_top5_sorted = df_top5_filtre.sort_values(
        ["version_max", "ratio"], ascending=[True, False]
    )
    df_top5_unique = (
        df_top5_sorted[df_top5_sorted["version_max"].isin(version_select)]
        .groupby("version_max")
        .head(5)
    )

    # 5. Construire la liste cumulative de cartes top 5
    versions_top5 = sorted(df_top5_unique["version_max"].unique())
    cartes_cumulatives = set()
    cartes_par_version = {}

    cartes_par_version = {
        v: df_top5_unique[df_top5_unique["version_max"] == v]["name"].tolist()
        for v in versions_top5
    }

    # 6. Construire le DataFrame final avec toutes les versions futures
    df_top5_evolution = pd.DataFrame()

    for v in versions_top5:
        cartes_actuelles = cartes_par_version[v]
        df_partiel = df_top5_filtre[
            (df_top5_filtre["version_max"] >= v)
            & (df_top5_filtre["name"].isin(cartes_actuelles))
        ].copy()
        df_partiel["version_reference"] = v
        df_top5_evolution = pd.concat(
            [df_top5_evolution, df_partiel], ignore_index=True
        )

    # 7. Choix version de départ
    if versions_top5:
        version_depart = st.selectbox("Starting extension", versions_top5)
        df_top5_affiche = df_top5_evolution[
            df_top5_evolution["version_reference"] == version_depart
        ]

        # 8. Graphique final
        graph_top5_cumul = (
            alt.Chart(df_top5_affiche)
            .mark_line(point=True)
            .encode(
                x=alt.X("version_max:N", title="extension"),
                y=alt.Y("ratio:Q", title="Usage rate"),
                color="name:N",
                tooltip=[
                    alt.Tooltip("name", title="Card name"),
                    alt.Tooltip("version_max", title="extension"),
                    alt.Tooltip("ratio", format=".2%", title="Usage Rate"),
                ],
            )
            .properties(
                title=f"Top 5 card changes after the {version_depart} extension",
                width=800,
                height=400,
            )
            .interactive()
        )

        st.altair_chart(graph_top5_cumul, use_container_width=True)
    else:
        st.warning("Aucune version valide sélectionnée avec des cartes dans le top 5.")