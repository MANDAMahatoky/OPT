import pandas as pd
import numpy as np

MOIS_FR_MAP = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
    'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
}

def calculer_indices_saisonnalite(df: pd.DataFrame, annee_col: str = 'annee', mois_col: str = 'mois', valeur_col: str = 'volume') -> pd.DataFrame:
    """
    Calcule les indices de saisonnalité (base moyenne mensuelle = 100) 
    à partir de l'historique des ventes.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=['mois', 'indice_saisonnalite'])

    df_clean = df.copy()

    # Normalisation et conversion des colonnes temporelles
    if df_clean[mois_col].dtype == object:
        df_clean[mois_col] = df_clean[mois_col].astype(str).str.lower().str.strip().map(MOIS_FR_MAP)
    
    df_clean[annee_col] = pd.to_numeric(df_clean[annee_col], errors='coerce')
    df_clean[mois_col] = pd.to_numeric(df_clean[mois_col], errors='coerce')
    df_clean[valeur_col] = pd.to_numeric(df_clean[valeur_col], errors='coerce')

    df_clean = df_clean.dropna(subset=[annee_col, mois_col, valeur_col])

    if df_clean.empty:
        return pd.DataFrame(columns=['mois', 'indice_saisonnalite'])

    # Identifier les années complètes (12 mois de données)
    counts_mois_annee = df_clean.groupby(annee_col)[mois_col].nunique()
    annees_completes = counts_mois_annee[counts_mois_annee == 12].index.tolist()

    if not annees_completes:
        annees_completes = df_clean[annee_col].unique().tolist()

    df_filtered = df_clean[df_clean[annee_col].isin(annees_completes)]
    if df_filtered.empty:
        df_filtered = df_clean

    # Calcul de la moyenne par mois
    moyennes_mensuelles = df_filtered.groupby(mois_col)[valeur_col].mean().reset_index()

    if moyennes_mensuelles.empty or moyennes_mensuelles[valeur_col].sum() == 0:
        mois_dispos = sorted(df_clean[mois_col].unique()) if not df_clean.empty else list(range(1, 13))
        return pd.DataFrame({'mois': mois_dispos, 'indice_saisonnalite': [100.0] * len(mois_dispos)})

    moyenne_globale = moyennes_mensuelles[valeur_col].mean()

    if moyenne_globale == 0:
        moyennes_mensuelles['indice_saisonnalite'] = 100.0
    else:
        moyennes_mensuelles['indice_saisonnalite'] = (moyennes_mensuelles[valeur_col] / moyenne_globale) * 100.0

    return moyennes_mensuelles[['mois', 'indice_saisonnalite']].sort_values('mois')
