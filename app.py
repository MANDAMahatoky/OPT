import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import io
from seasonality_index import calculer_indices_saisonnalite, MOIS_FR_MAP

# Configuration de la page
st.set_page_config(
    page_title="Moteur S&OP - Prévision & SAAR",
    page_icon="📈",
    layout="wide"
)

st.title("🚀 Moteur S&OP - Prévision SAAR & Rolling Forecast")

# -------------------------------------------------------------------------
# CHARGEMENT DES DONNÉES (AUTOMATIQUE)
# -------------------------------------------------------------------------
@st.cache_data
def load_data():
    brut_df = pd.DataFrame()
    ref_df = pd.DataFrame()
    
    try:
        # DATA_BRUT.xlsx possède 7 colonnes sans en-tête explicite d'origine
        raw_data = pd.read_excel("data/input/DATA_BRUT.xlsx", header=None)
        if raw_data.shape[1] >= 7:
            brut_df = raw_data.iloc[:, :7].copy()
            brut_df.columns = ['annee', 'mois', 'segment', 'produit', 'agence', 'article', 'volume']
        else:
            brut_df = pd.read_excel("data/input/DATA_BRUT.xlsx")
    except Exception as e:
        st.warning(f"Fichier `data/input/DATA_BRUT.xlsx` non trouvé ou illisible ({e}). Utilisation d'un jeu de données de démo.")
        # Données de démonstration sécurisées
        np.random.seed(42)
        annees = [2023, 2024, 2025]
        mois_noms = list(MOIS_FR_MAP.keys())
        segments = ["4-EAUX"]
        agences = ["01-Tanjombato", "04-Tulear", "05-Fianarantsoa"]
        articles = ["190-Cristalline 100 cl PET", "189-Cristalline 200 cl PET"]
        
        data_list = []
        for a in annees:
            for m in mois_noms:
                for seg in segments:
                    for ag in agences:
                        for art in articles:
                            data_list.append({
                                'annee': a,
                                'mois': m,
                                'segment': seg,
                                'produit': "1-Cristalline",
                                'agence': ag,
                                'article': art,
                                'volume': np.random.uniform(500, 3000)
                            })
        brut_df = pd.DataFrame(data_list)

    try:
        ref_df = pd.read_excel("Classeur2.xlsx")
    except Exception:
        ref_df = pd.DataFrame()

    return brut_df, ref_df

df_brut_raw, df_ref = load_data()

if df_brut_raw.empty:
    st.error("Le jeu de données principal est vide. Veuillez vérifier le fichier `data/input/DATA_BRUT.xlsx`.")
    st.stop()

# Nettoyage et préparation du dataset brut
df_work = df_brut_raw.copy()
# Standardisation des noms de colonnes si présents sous forme de texte
df_work.columns = [str(c).strip().lower() for c in df_work.columns]

# Mapping des mois textuels français vers numériques
if 'mois' in df_work.columns and df_work['mois'].dtype == object:
    df_work['mois_num'] = df_work['mois'].astype(str).str.lower().str.strip().map(MOIS_FR_MAP)
else:
    df_work['mois_num'] = df_work['mois']

df_work['annee_num'] = pd.to_numeric(df_work['annee'], errors='coerce')

# Exclusion des lignes de totaux ou lignes vides (lignes agglomérées du fichier brut)
df_work = df_work.dropna(subset=['annee_num', 'mois_num'])
df_work = df_work[
    (df_work['article'].notna()) & (df_work['article'].astype(str).str.lower() != 'total') &
    (df_work['agence'].notna()) & (df_work['agence'].astype(str).str.lower() != 'total') &
    (df_work['segment'].notna()) & (df_work['segment'].astype(str).str.lower() != 'total')
]

df_work['annee'] = df_work['annee_num'].astype(int)
df_work['mois'] = df_work['mois_num'].astype(int)
df_work['volume'] = pd.to_numeric(df_work['volume'], errors='coerce').fillna(0.0)

if df_work.empty:
    st.error("Aucune donnée détaillée exploitable après filtrage des totaux. Vérifiez la structure de `DATA_BRUT.xlsx`.")
    st.stop()

metrique_choisie = 'volume'

# -------------------------------------------------------------------------
# BARRE LATÉRALE DE CONFIGURATION
# -------------------------------------------------------------------------
st.sidebar.header("⚙️ Paramètres S&OP")

annees_dispos = sorted(df_work['annee'].dropna().unique().tolist())
annee_defaut = annees_dispos[-1] if annees_dispos else 2025

annee_cloture = st.sidebar.selectbox("Année de clôture (Historique)", options=annees_dispos, index=len(annees_dispos)-1 if annees_dispos else 0)
mois_pivot = st.sidebar.slider("Mois pivot (Cutoff S&OP)", min_value=1, max_value=12, value=6, help="Dernier mois de réalisé connu.")
annee_cible = st.sidebar.selectbox("Année cible (Projections)", options=[annee_cloture, annee_cloture + 1], index=1 if annee_cloture + 1 in annees_dispos or len(annees_dispos) > 0 else 0)

nb_decimales = st.sidebar.number_input("Nombre de décimales", min_value=0, max_value=4, value=2, step=1)
hausse_min = st.sidebar.number_input("Hausse minimale annuelle (%)", min_value=-50.0, max_value=100.0, value=2.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtres en cascade")

# Filtre Agence
agences_dispos = sorted(df_work['agence'].dropna().unique().tolist())
selected_agences = st.sidebar.multiselect("Agence(s)", options=agences_dispos, default=agences_dispos)

df_filtered_agence = df_work[df_work['agence'].isin(selected_agences)] if selected_agences else df_work

# Filtre Segment
segments_dispos = sorted(df_filtered_agence['segment'].dropna().unique().tolist())
selected_segments = st.sidebar.multiselect("Segment(s)", options=segments_dispos, default=segments_dispos)

df_filtered_seg = df_filtered_agence[df_filtered_agence['segment'].isin(selected_segments)] if selected_segments else df_filtered_agence

# Filtre Article
articles_dispos = sorted(df_filtered_seg['article'].dropna().unique().tolist())
selected_articles = st.sidebar.multiselect("Article(s)", options=articles_dispos, default=articles_dispos)

if selected_articles:
    df_work_filtered = df_filtered_seg[df_filtered_seg['article'].isin(selected_articles)]
else:
    df_work_filtered = df_filtered_seg

if df_work_filtered.empty:
    st.warning("⚠️ Aucun filtre ne correspond aux données disponibles. Veuillez élargir vos sélections dans la barre latérale.")
    st.stop()

# -------------------------------------------------------------------------
# MOTEUR DE CALCUL SAAR & ROLLING FORECAST
# -------------------------------------------------------------------------
df_saison = calculer_indices_saisonnalite(df_work, annee_col='annee', mois_col='mois', valeur_col='volume')

# -------------------------------------------------------------------------
# ONGLETS PRINCIPAUX
# -------------------------------------------------------------------------
tab1, tab2 = st.tabs(["📊 Indice saisonnier", "📋 Détail des cumuls & prévisions"])

with tab1:
    st.subheader("Profils Saisonniers (Base Moyenne Mensuelle = 100)")
    if not df_saison.empty:
        chart_data = df_saison.copy()
        mois_noms_inv = {1: 'Janv', 2: 'Févr', 3: 'Mars', 4: 'Avr', 5: 'Mai', 6: 'Juin', 
                         7: 'Juil', 8: 'Août', 9: 'Sept', 10: 'Oct', 11: 'Nov', 12: 'Déc'}
        chart_data['libelle_mois'] = chart_data['mois'].map(mois_noms_inv)

        base_chart = alt.Chart(chart_data).encode(
            x=alt.X('libelle_mois:N', sort=list(mois_noms_inv.values()), title='Mois'),
            y=alt.Y('indice_saisonnalite:Q', title='Indice (Base 100)')
        )
        bars = base_chart.mark_bar(color='#1f77b4', cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        text = base_chart.mark_text(align='center', baseline='bottom', dy=-5).encode(
            text=alt.Text('indice_saisonnalite:Q', format=f'.{nb_decimales}f')
        )
        
        st.altair_chart((bars + text).interactive(), use_container_width=True)
        
        st.dataframe(
            chart_data[['mois', 'libelle_mois', 'indice_saisonnalite']].rename(
                columns={'mois': 'Numéro', 'libelle_mois': 'Mois', 'indice_saisonnalite': 'Indice Base 100'}
            ).style.format({'Indice Base 100': f'{{:.{nb_decimales}f}}'}),
            use_container_width=True
        )
    else:
        st.info("Données insuffisantes pour calculer les indices de saisonnalité.")

with tab2:
    st.subheader("Tableaux Croisés Dynamiques & Atterrissement S&OP")
    
    df_ytd = df_work_filtered[(df_work_filtered['annee'] == annee_cloture) & (df_work_filtered['mois'] <= mois_pivot)]
    df_hist_complet = df_work_filtered[df_work_filtered['annee'] == annee_cloture]

    group_cols = ['agence', 'segment', 'article']
    
    pivot_ytd = df_ytd.groupby(group_cols)['volume'].sum().reset_index().rename(columns={'volume': 'Realise_YTD'})
    pivot_total_an = df_hist_complet.groupby(group_cols)['volume'].sum().reset_index().rename(columns={'volume': 'Volume_Annee_N_1'})
    
    df_synthese = pd.merge(pivot_total_an, pivot_ytd, on=group_cols, how='left').fillna({'Realise_YTD': 0.0})
    
    sum_hist_total = df_synthese['Volume_Annee_N_1'].replace(0, np.nan)
    df_synthese['Poids_YTD'] = df_synthese['Realise_YTD'] / sum_hist_total
    df_synthese['Poids_YTD'] = df_synthese['Poids_YTD'].fillna(mois_pivot / 12.0)
    
    facteur_croissance = 1.0 + (hausse_min / 100.0)
    df_synthese['Atterri_Prevu'] = df_synthese['Realise_YTD'] + (df_synthese['Volume_Annee_N_1'] * facteur_croissance * (1.0 - (mois_pivot / 12.0)))
    df_synthese['Ecart_vs_N_1'] = df_synthese['Atterri_Prevu'] - df_synthese['Volume_Annee_N_1']
    df_synthese['Taux_Croissance_%'] = np.where(
        df_synthese['Volume_Annee_N_1'] > 0, 
        (df_synthese['Ecart_vs_N_1'] / df_synthese['Volume_Annee_N_1']) * 100.0, 
        0.0
    )

    # Fusion avec Classeur2 si disponible
    if not df_ref.empty:
        # Normalisation de la colonne de jointure article sur Classeur2
        ref_cols = {c.lower(): c for c in df_ref.columns}
        art_col_ref = ref_cols.get('article', df_ref.columns[0])
        df_synthese = pd.merge(df_synthese, df_ref, left_on='article', right_on=art_col_ref, how='left')

    format_dict = {
        'Volume_Annee_N_1': f'{{:,.{nb_decimales}f}}',
        'Realise_YTD': f'{{:,.{nb_decimales}f}}',
        'Atterri_Prevu': f'{{:,.{nb_decimales}f}}',
        'Ecart_vs_N_1': f'{{:,.{nb_decimales}f}}',
        'Taux_Croissance_%': '{:.2f}%'
    }

    # Application sécurisée du formatage
    valid_format_dict = {k: v for k, v in format_dict.items() if k in df_synthese.columns}
    st.dataframe(df_synthese.style.format(formatter=valid_format_dict), use_container_width=True)

    # -------------------------------------------------------------------------
    # EXPORT EXCEL MULTI-ONGLETS
    # -------------------------------------------------------------------------
    st.markdown("---")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info("📥 Téléchargez le rapport complet de synthèse S&OP au format Excel.")
    with col2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_synthese.to_excel(writer, sheet_name='Atterrissement_SOP', index=False)
            if not df_saison.empty:
                df_saison.to_excel(writer, sheet_name='Indices_Saisonnalite', index=False)
            df_work_filtered.to_excel(writer, sheet_name='Donnees_Filtrees', index=False)
        
        excel_data = output.getvalue()
        st.download_button(
            label="📊 Télécharger Excel S&OP",
            data=excel_data,
            file_name=f"Rapport_SOP_{annee_cloture}_M{mois_pivot}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
