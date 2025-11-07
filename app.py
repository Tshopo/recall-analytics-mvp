import streamlit as st
import pandas as pd
import plotly.express as px
import os 
from datetime import datetime
import numpy as np
import json 
import plotly.graph_objects as go


# --- 0. SIMULATION DES COUTS STRATEGIQUES (EN DUR) ---
COUT_RAPPEl_GRAVE_UNITAIRE = 50000.0  
COUT_RAPPEl_MINEUR_UNITAIRE = 5000.0   
COUT_LOGISTIQUE_JOUR_SUPP = 500.0      
SEUIL_IMR_ALERTE = 10.0                
risques_graves_keywords = "listeriose|salmonellose|e\.coli|blessures|allergene non declare|corps étranger" 

# Nouveaux Keywords pour les indicateurs de cause racine (simulés)
keywords_fournisseur = "allergene non declare|composition|etiquetage non conforme|matiere premiere"
keywords_logistique = "temperature|rupture de la chaine du froid|probleme de distribution|conditionnement"
keywords_recurrence_simule = ["salmonelle", "listeria", "e.coli"] # Pour la simulation du TRCR

# --- NOUVELLES CONSTANTES : LOGIQUE TRAFFIC LIGHT ---
SEUIL_VERT_MAX = 5     
SEUIL_ORANGE_MAX = 15  
# Seuils pour l'IPC (Indice de Pression Concurrentielle : IMR Marque / IMR Marché)
SEUIL_IPC_BON = 0.95   # Marque fait mieux que le marché
SEUIL_IPC_MOYEN = 1.05 # Marque fait légèrement moins bien que le marché

# Fonction pour attribuer un "Traffic Light" à une fréquence
def get_traffic_light(count):
    if count <= SEUIL_VERT_MAX:
        return "🟢 Faible (Green)"
    elif count <= SEUIL_ORANGE_MAX:
        return "🟠 Modéré (Amber)"
    else:
        return "🔴 Critique (Red)"

# Fonction pour attribuer la couleur de la flèche (delta_color)
# 'inverse' = True si une valeur plus basse est meilleure (ex: IMR)
def get_delta_color(value, target_threshold, inverse=False):
    if inverse:
        # Pour IMR : Plus bas que le seuil est Bon (Green), au-dessus est Mauvais (Red)
        if value <= target_threshold:
            return "normal"  # Green
        else:
            return "inverse" # Red
    else:
        # Pour IPC : Autour de 1.0 est neutre/bonne, très au-dessus est Mauvais
        if value < SEUIL_IPC_BON:
            return "normal" # Marque meilleure que le marché
        elif value <= SEUIL_IPC_MOYEN:
            return "off"    # Proche du marché (Neutre)
        else:
            return "inverse" # Marque moins bonne que le marché
            
# Charger un GeoJSON simple pour la France
@st.cache_data(ttl=3600)
def load_geojson():
    """
    Tente de charger un fichier GeoJSON pour la cartographie.
    Si le fichier est manquant ou non supporté, retourne None.
    """
    geojson_path = "departements.geojson" 
    
    if os.path.exists(geojson_path):
        try:
            with open(geojson_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            st.sidebar.success("GeoJSON chargé avec succès pour la cartographie.")
            return data
        except Exception as e:
            st.sidebar.error(f"Erreur lors du chargement du GeoJSON : {e}")
            return None
    else:
        return None

# --- 1. CONFIGURATION ET MISE EN PAGE GLOBALE ---
st.set_page_config(page_title="Recall Analytics (RappelConso) - B2B PRO", layout="wide", initial_sidebar_state="expanded")
st.title("🛡️ Recall Analytics — Dashboard d'Intelligence Marché (B2B PRO) - Vue Stratégie DS")

# --- CSS INJECTION POUR L'ESTHÉTIQUE, LA POLICE ET LA SÉPARATION DES KPI ---
st.markdown("""
<style>
/* Style appliqué directement à l'ensemble du widget st.metric */
div[data-testid="stMetric"] { 
    background-color: #FFFFFF; /* Fond blanc pour chaque boîte de métrique */
    padding: 10px; /* Espace interne pour le texte */
    border-radius: 8px; /* Bords arrondis */
    border: 1px solid #e0e0e0; /* Bordure légère */
    margin-bottom: 10px; /* Espace sous chaque métrique */
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); /* Ombre légère */
    min-height: 100px; /* Hauteur minimale pour mieux contenir le texte */
    display: flex; /* Utilise flexbox pour un meilleur alignement interne */
    flex-direction: column; /* Organise label et valeur verticalement */
    justify-content: center; /* Centre verticalement le contenu */
    align-items: flex-start; /* Aligne le contenu à gauche */
}

/* Augmente la taille de la police des valeurs st.metric */
div[data-testid="stMetricValue"] {
    font-size: 1.5rem; /* **AUGMENTÉ : Taille de la valeur (ex: 15659)** */
    font-weight: 700;
    white-space: normal; /* Permet au texte de s'enrouler */
    overflow: hidden; /* Cache le texte qui déborde */
    text-overflow: ellipsis; /* Ajoute des points de suspension si le texte est coupé */
    line-height: 1.2; /* Ajuste l'espacement entre les lignes si le texte s'enroule */
}

/* Réduit la taille de la police des labels st.metric */
div[data-testid="stMetricLabel"] > div {
    font-size: 0.6rem; /* **RÉDUIT : Taille du label (ex: Total Rappels (Périmètre))** */
    font-weight: 600;
    opacity: 0.8;
    white-space: normal; /* Permet au texte de s'enrouler */
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.2; /* Ajuste l'espacement entre les lignes */
}

/* Sépare visuellement les différentes sections (onglets) lors du scroll en donnant un fond léger */
.stTabs [data-testid="stVerticalBlock"] {
    padding-top: 20px;
    padding-bottom: 20px;
    background-color: #F8F8F8; /* Gris très léger pour contraster avec le fond de page */
    border-radius: 5px;
}
.stMetric {
    cursor: help; /* Rend l'icône I plus intuitive */
}

</style>
""", unsafe_allow_html=True)
# --- FIN DE L'AJOUT CSS ---

st.markdown("""
**Focus DS :** Intégration des **Coûts Stratégiques Simulé**, **Indicateurs Denses** et **Analyse Géospatiale**.
""")

st.markdown("---")

# --- 2. FONCTIONS UTILITAIRES DE DATA PROCESSING (STABLES) ---

@st.cache_data(ttl=3600)
def load_data_from_csv(file_path="rappelconso_export.csv"):
    """Charge les données, standardise les colonnes et gère les séparateurs."""
    
    if not os.path.exists(file_path):
        st.error(f"❌ Fichier non trouvé : '{file_path}'. Veuillez vous assurer que le fichier CSV téléchargé est placé dans le même dossier que l'application et porte ce nom.")
        return pd.DataFrame()
    
    df = pd.DataFrame()
    
    try:
        try:
            df = pd.read_csv(file_path, sep=";", encoding='utf-8')
            if df.shape[1] <= 1:
                df = pd.read_csv(file_path, sep=",", encoding='utf-8')
        except Exception:
            df = pd.read_csv(file_path, sep=",", encoding='utf-8')

        if df.empty or df.shape[1] <= 1:
            raise ValueError("Le fichier ne contient pas de données.")
            
        column_mapping = {
            "categorie_produit": "categorie_de_produit",
            "marque_produit": "nom_marque_du_produit",
            "motif_rappel": "motif_du_rappel",
            "numero_fiche": "reference_fiche",
            "lien_vers_la_fiche_rappel": "liens_vers_la_fiche_rappel",
            "date_debut_commercialisation_produit": "date_debut_commercialisation",
            "nom_fabricant_ou_marque": "nom_marque_du_produit",
            "denomination_sociale_du_producteur": "nom_marque_du_produit" # Ajout potentiel
        }
        
        rename_dict = {old_name: new_name for old_name, new_name in column_mapping.items() if old_name in df.columns and old_name != new_name}
        df = df.rename(columns=rename_dict)

        required_cols = ["categorie_de_produit", "nom_marque_du_produit", "motif_du_rappel", "distributeurs", "date_publication"]
        missing_cols = [c for c in required_cols if c not in df.columns]

        if missing_cols:
            st.error(f"⚠️ Alerte Colonnes : Le script ne trouve pas les colonnes nécessaires : **{', '.join(missing_cols)}**.")
            st.stop()
            
        if "date_publication" in df.columns:
            df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce", utc=True)
            df = df.sort_values(by="date_publication", ascending=False) 
        
        if "date_debut_commercialisation" in df.columns:
            df["date_debut_commercialisation"] = pd.to_datetime(df["date_debut_commercialisation"], errors="coerce", utc=True)

        for col in ["distributeurs", "zone_geographique_de_vente", "risques_encourus", "motif_du_rappel", "categorie_de_produit", "nom_marque_du_produit", "identifiant_de_l_etablissement_d_ou_provient_le_produit", "etat_fiche", "denomination_vente", "sous_categorie_produit"]:
            if col in df.columns:
                df[col] = (df[col].astype(str)
                                 .str.lower()
                                 .str.replace("|", ";", regex=False)
                                 .str.replace(", ", ";", regex=False)
                                 .str.strip()
                                 .replace('nan', '', regex=False)
                                 .replace('', pd.NA) 
                )
        st.success(f"✅ {len(df)} enregistrements chargés depuis {file_path}.")
        return df

    except Exception as e:
        st.error(f"❌ Erreur critique lors de la lecture du fichier CSV. Message : {e}")
        return pd.DataFrame()

def explode_column(df, column_name):
    """Divise une colonne de chaînes de caractères séparées par des points-virgules (;) en lignes distinctes."""
    if column_name in df.columns and not df.empty:
        s = df[column_name].copy().astype(str).str.split(";")
        exploded_s = s.explode()
        exploded_df = exploded_s.to_frame(name=column_name)
        exploded_df = exploded_df.dropna(subset=[column_name])
        exploded_df[column_name] = exploded_df[column_name].str.strip()
        exploded_df = exploded_df[exploded_df[column_name] != 'nan']
        exploded_df = exploded_df[exploded_df[column_name] != '']
        return exploded_df
    return pd.DataFrame() 

def safe_filter_list(df_source, col_name, exploded=False):
    """Construit une liste de valeurs uniques pour les filtres."""
    if col_name not in df_source.columns or df_source.empty:
        return ["Toutes"]
    
    df_work = explode_column(df_source, col_name) if exploded else df_source.copy()

    if col_name in df_work.columns and not df_work.empty:
        raw_list = df_work[col_name].dropna().astype(str).unique().tolist()
        valid_list = [s.strip() for s in raw_list if s.strip() and s.strip() != 'nan']
        # Limite le nombre d'options si la liste est trop longue (par exemple, pour la dénomination de vente)
        if len(valid_list) > 1000:
            st.sidebar.warning(f"Liste trop longue pour {col_name}. Affichage des 1000 premières.")
            return ["Toutes"] + sorted(list(set(valid_list[:1000])))
        return ["Toutes"] + sorted(list(set(valid_list)))
    
    return ["Toutes"]

# --- 3. CHARGEMENT ET FILTRES GLOBAUX ---
df = load_data_from_csv()
geojson_data = load_geojson() 

if df.empty:
    st.stop()

# Gestion de l'état pour la marque sélectionnée (pour maintenir la cohérence)
if 'selected_marque' not in st.session_state:
    st.session_state['selected_marque'] = "Toutes"
    
# --- FILTRAGE PRÉLIMINAIRE PAR PÉRIODE (pour les listes déroulantes) ---
df_temp = df.copy()

# Période
if "date_publication" in df_temp.columns:
    now = pd.Timestamp.now(tz='UTC') 
    periode_options = {
        "12 derniers mois": pd.DateOffset(months=12),
        "6 derniers mois": pd.DateOffset(months=6),
        "3 derniers mois": pd.DateOffset(months=3),
        "Toute la période": None
    }
    
    st.sidebar.header("⚙️ Filtres Transversaux")
    
    # 1. Période
    periode = st.sidebar.selectbox("Période d'Analyse", list(periode_options.keys()))
    offset = periode_options[periode]
    if offset:
        df_temp = df_temp[df_temp["date_publication"] >= now - offset]
    else:
        df_temp = df.copy() 

# 2. Catégorie de Produit
categories = safe_filter_list(df_temp, "categorie_de_produit")
cat = st.sidebar.selectbox("Catégorie de Produit", categories)

# --- APPLICATION DU FILTRE CATÉGORIE POUR COHÉRENCE MARQUE ---
df_coherence = df_temp.copy()
if cat != "Toutes" and "categorie_de_produit" in df_coherence.columns:
    df_coherence = df_coherence[df_coherence["categorie_de_produit"] == cat]
    
# 3. Marque (Benchmarking) - COHÉRENCE AVEC LA CATÉGORIE
marques_coherentes = safe_filter_list(df_coherence, "nom_marque_du_produit")
current_marque_selection = st.session_state['selected_marque']
if current_marque_selection not in marques_coherentes:
    current_marque_selection = "Toutes"
marque = st.sidebar.selectbox("Marque (Benchmarking)", marques_coherentes, index=marques_coherentes.index(current_marque_selection))
st.session_state['selected_marque'] = marque # Sauvegarde pour le prochain cycle

# --- NOUVEAUX FILTRES BASÉS SUR LES AUTRES CHAMPS ---

# 4. Sous-Catégorie / Nature du Produit
col_nature = "denomination_vente"
if "sous_categorie_produit" in df.columns:
    col_nature = "sous_categorie_produit"
    
nature_list = safe_filter_list(df_coherence, col_nature)
nature = st.sidebar.selectbox(f"Nature du Produit ({col_nature.replace('_', ' ').title()})", nature_list)

# 5. Distributeur (Canal)
distributeurs_list = safe_filter_list(df_coherence, "distributeurs", exploded=True)
distrib = st.sidebar.selectbox("Distributeur (Canal)", distributeurs_list)

# 6. Motif de Rappel (Cause)
motifs_list = safe_filter_list(df_coherence, "motif_du_rappel")
motif = st.sidebar.selectbox("Motif de Rappel (Cause)", motifs_list)

# 7. Lieu de Vente (Zone Géographique)
zone_list = safe_filter_list(df_coherence, "zone_geographique_de_vente", exploded=True)
zone = st.sidebar.selectbox("Lieu de Vente (Zone Géographique)", zone_list)

# 8. Statut de la Fiche
statut_list = safe_filter_list(df_coherence, "etat_fiche")
statut = st.sidebar.selectbox("Statut de la Fiche", statut_list)


# --- APPLICATION FINALE DES FILTRES SUR LE DATAFRAME GLOBAL ---
df_filtered = df.copy() 

# 1. Période
if offset:
    df_filtered = df_filtered[df_filtered["date_publication"] >= now - offset]

# 2. Catégorie
if cat != "Toutes" and "categorie_de_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["categorie_de_produit"] == cat]
    
# 3. Marque
if marque != "Toutes" and "nom_marque_du_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["nom_marque_du_produit"] == marque]

# 4. Nature du Produit
if nature != "Toutes" and col_nature in df_filtered.columns:
    df_filtered = df_filtered[df_filtered[col_nature] == nature]
    
# 5. Distributeur
if distrib != "Toutes" and "distributeurs" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["distributeurs"].str.contains(distrib, case=False, na=False)]

# 6. Motif
if motif != "Toutes" and "motif_du_rappel" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["motif_du_rappel"].str.contains(motif, case=False, na=False)]

# 7. Zone
if zone != "Toutes" and "zone_geographique_de_vente" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["zone_geographique_de_vente"].str.contains(zone, case=False, na=False)]
    
# 8. Statut
if statut != "Toutes" and "etat_fiche" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["etat_fiche"] == statut]

# --- 4. CALCULS TRANSVERSAUX (KPIs) ---
total_rappels = len(df_filtered)

if total_rappels == 0:
    st.warning("⚠️ Aucun rappel trouvé avec les filtres actuels. Veuillez ajuster la période ou les sélections dans la sidebar.")
    st.stop()


df_risques_exploded = explode_column(df_filtered, "risques_encourus")
df_motifs_exploded = explode_column(df_filtered, "motif_du_rappel")

# Risque principal
risque_principal = "N/A"
if not df_risques_exploded.empty and "risques_encourus" in df_risques_exploded.columns:
    risque_counts = df_risques_exploded["risques_encourus"].value_counts()
    if not risque_counts.empty:
        risque_major = next(iter(risque_counts.index), None)
        if risque_major:
            # Tronque le texte si "Listeria Monocytogenes" est présent
            if "listeria monocytogenes" in risque_major.lower():
                risque_principal = "Listeria Monocytogenes"
            else:
                risque_principal = risque_major.title()
    
# Vitesse de Réponse Moyenne (Proxy) - Délai Moyen (DM)
DM_label = "N/A"
DM_value = 0.0
df_temp_dates = pd.DataFrame()
if "date_debut_commercialisation" in df_filtered.columns and not df_filtered["date_debut_commercialisation"].isnull().all():
    df_temp_dates = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation"]).copy()
    if not df_temp_dates.empty:
        df_temp_dates["duree_commercialisation"] = (df_temp_dates["date_publication"] - df_temp_dates["date_debut_commercialisation"]).dt.days
        df_temp_dates = df_temp_dates[df_temp_dates["duree_commercialisation"] >= 0]
        if not df_temp_dates.empty:
            DM_value = df_temp_dates["duree_commercialisation"].mean()
            DM_label = f"{DM_value:.1f} jours"
    
# --- IMR FUNCTION (Rappel) ---
def calculate_imr(df_calc):
    if df_calc.empty or 'risques_encourus' not in df_calc.columns:
        return 0.0, 0.0, 0.0

    df_imr = df_calc.copy()
    
    # 1. Calcul de la gravité
    df_imr["is_risque_grave"] = df_imr["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
    df_imr['score_gravite'] = np.where(df_imr['is_risque_grave'], 2, 1) # Risque grave = poids 2, mineur = poids 1
    
    total_rappels_period = len(df_imr)
    total_score = df_imr['score_gravite'].sum()
    
    if total_rappels_period > 0:
        imr = (total_score / total_rappels_period) * 10 
        avg_gravite = total_score / total_rappels_period # Gravité Moyenne
    else:
        imr = 0.0
        avg_gravite = 0.0
        
    df_imr['cout_implicite'] = np.where(df_imr['is_risque_grave'], COUT_RAPPEl_GRAVE_UNITAIRE, COUT_RAPPEl_MINEUR_UNITAIRE)
    total_cout = df_imr['cout_implicite'].sum()

    return imr, total_cout, avg_gravite

# Calcul de l'IMR pour la marque filtrée
imr_marque, cout_marque, _ = calculate_imr(df_filtered)

# Calcul de l'IMR pour le marché (pour la comparaison)
imr_marche_comp = 0.0
if "date_publication" in df.columns:
    df_marche_comp = df_temp.copy() # On prend le DF filtré uniquement par la Période
    imr_marche_comp, _, _ = calculate_imr(df_marche_comp)

# NOUVEAU KPI: Indice de Pression Concurrentielle (IPC)
ipc_value = imr_marque / imr_marche_comp if imr_marche_comp > 0 else 0.0

# Calcul du % Rappels graves
pc_risques_graves = 0.0
pc_risques_graves_str = "N/A"
if total_rappels > 0 and 'risques_encourus' in df_filtered.columns:
    count_graves = df_filtered["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False).sum()
    pc_risques_graves = (count_graves / total_rappels * 100)
    pc_risques_graves_str = f"{pc_risques_graves:.1f}%"


# --- CALCULS NOUVEAUX KPIs ---

# 1. Taux d'Impact Fournisseur Critique (TIFC) - Simulé sur motifs
tifc_value = 0.0
if total_rappels > 0 and 'motif_du_rappel' in df_filtered.columns:
    count_fournisseur_causes = df_filtered["motif_du_rappel"].str.contains(keywords_fournisseur, case=False, na=False).sum()
    tifc_value = (count_fournisseur_causes / total_rappels * 100)

# 2. Indice de Sévérité du Risque (ISR) - Gravité Moyenne par Catégorie Principale
isr_value = 0.0
if "categorie_de_produit" in df_filtered.columns:
    df_isr = df_filtered.copy()
    if not df_isr.empty:
        _, _, avg_gravite_filtered = calculate_imr(df_isr) # 1 à 2
        # Ne compter que les rappels dans la catégorie sélectionnée (si filtre actif)
        df_cat_active = df_filtered[df_filtered["categorie_de_produit"] == cat] if cat != "Toutes" else df_filtered
        
        count_cat = len(df_cat_active)
        
        # Le calcul de l'ISR doit se faire sur le périmètre de la marque/catégorie
        isr_value = avg_gravite_filtered * (count_cat / total_rappels) * 10 if total_rappels > 0 else 0.0
        
# 3. Délai d'Alerte Précoce (DAP)
dap_value = 0.0
if not df_temp_dates.empty:
    # Simuler le DAP comme le pourcentage de rappels avec un délai de commercialisation très court (< 7 jours)
    dap_count = df_temp_dates[df_temp_dates["duree_commercialisation"] <= 7].shape[0]
    dap_value = (dap_count / total_rappels) * 100 if total_rappels > 0 else 0.0

# 4. Taux d'Anomalie Logistique (TAL) - Simulé sur motifs
tal_value = 0.0
if total_rappels > 0 and 'motif_du_rappel' in df_filtered.columns:
    count_log_causes = df_filtered["motif_du_rappel"].str.contains(keywords_logistique, case=False, na=False).sum()
    tal_value = (count_log_causes / total_rappels * 100)

# 5. Volatilité IMR (IMR_STD)
imr_std_value = 0.0
if marque != "Toutes" and "date_publication" in df_filtered.columns:
    df_trend = df.copy()
    # On filtre par la période uniquement (la marque sera filtrée après)
    if offset:
        df_trend = df_trend[df_trend["date_publication"] >= now - offset]
    df_trend["Mois"] = df_trend["date_publication"].dt.to_period("M")

    def compute_imr_per_month(df_input):
        if 'risques_encourus' not in df_input.columns or df_input.empty: return pd.Series(dtype='float64')
        df_input['is_risque_grave'] = df_input["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
        df_input['score_gravite'] = np.where(df_input['is_risque_grave'], 2, 1)
        imr_monthly = df_input.groupby('Mois').agg(
            Total_Score=('score_gravite', 'sum'),
            Total_Rappels=('score_gravite', 'count')
        )
        imr_monthly['IMR'] = np.where(imr_monthly['Total_Rappels'] > 0, 
                                      (imr_monthly['Total_Score'] / imr_monthly['Total_Rappels']) * 10, 
                                      0.0)
        return imr_monthly['IMR']

    imr_series = compute_imr_per_month(df_trend[df_trend["nom_marque_du_produit"] == marque])
    if len(imr_series) > 1:
        imr_std_value = imr_series.std()

# 6. Taux de Récurrence des Causes Racines (TRCR) - Simulé
trcr_value = 0.0
if total_rappels > 0 and "risques_encourus" in df_filtered.columns:
    # Simuler la récurrence si Listeria, Salmonella ou E.Coli apparaissent au moins deux fois.
    df_temp_recurrence = df_filtered.copy()
    df_temp_recurrence['Recurrence_Flag'] = df_temp_recurrence["risques_encourus"].apply(
        lambda x: any(kw in str(x) for kw in keywords_recurrence_simule)
    )
    if df_temp_recurrence['Recurrence_Flag'].sum() >= 2:
        # TRCR simulé à 15% si on détecte au moins 2 cas de risque haut
        trcr_value = 15.0 
    else:
        trcr_value = 2.0

# 7. Ratio Risque/Opportunité (RRO) - Simulation sur la catégorie
rro_value = 0.0
if total_rappels > 0 and "categorie_de_produit" in df_filtered.columns:
    rappels_par_cat = df_marche_comp.groupby("categorie_de_produit").size() if 'df_marche_comp' in locals() else pd.Series()
    
    # Calculer l'IMR de la catégorie sur le marché filtré
    imr_cat_marche = 0.0
    if cat != "Toutes":
        imr_cat_marche, _, _ = calculate_imr(df_marche_comp[df_marche_comp["categorie_de_produit"] == cat])
    else:
        imr_cat_marche = imr_marche_comp

    if imr_cat_marche > 0 and cat != "Toutes" and cat in rappels_par_cat:
        # RRO = IMR_Marque / IMR_Catégorie_Marché (Facteur de risque pur)
        rro_value = imr_marque / imr_cat_marche 
    else:
        rro_value = imr_marque * 0.5 / 10


# --- CALCUL DES COULEURS TRAFFIC LIGHT ---
# 1. IMR de la Marque (plus bas est meilleur)
imr_marque_delta = imr_marque - (SEUIL_IMR_ALERTE / 2) # Arbitraire pour simuler une 'variation' par rapport à un objectif de 5
imr_marque_color = get_delta_color(imr_marque, SEUIL_IMR_ALERTE, inverse=True)

# 2. IPC (Indice de Pression Concurrentielle) (cible = 1.0)
# Le delta est calculé par rapport à l'objectif 1.0
ipc_delta = ipc_value - 1.0 
ipc_color = get_delta_color(ipc_value, 1.0, inverse=False)


# --- 5. STRUCTURE DU TABLEAU DE BORD PAR ACTEUR (TABS) ---

tab1, tab2, tab3 = st.tabs(["🏭 Fabricants & Marques", "🛒 Distributeurs & Retailers", "🔬 Risque & Conformité"])


# ----------------------------------------------------------------------
# TAB 1: FABRICANTS & MARQUES (BENCHMARKING IMR & RISQUE FOURNISSEUR)
# ----------------------------------------------------------------------
with tab1:
    st.header("🎯 Intelligence Concurrentielle & Maîtrise du Risque Fournisseur")
    
    # --- FEUILLE DE ROUTE FABRICANTS ---
    with st.expander("📖 Feuille de Route : Filtrage et Interprétation pour Fabricants/Marques"):
        st.markdown("""
        Cet onglet est conçu pour les équipes de **Direction Générale**, **Qualité Produit**, et **Achats**.
        
        ### ⚙️ Stratégie de Filtrage Recommandée
        | Étape | Filtre à Appliquer | Objectif du Filtre |
        | :---: | :--- | :--- |
        | **1.** | **Période d'Analyse** | Sélectionnez **"12 derniers mois"** pour une vue annuelle stable, ou **"3 derniers mois"** pour identifier rapidement les tendances émergentes. |
        | **2.** | **Catégorie de Produit** | **Filtrer par votre Catégorie principale.** Calibre l'IMR du Marché (benchmark) et concentre l'analyse sur vos concurrents directs. |
        | **3.** | **Marque (Benchmarking)** | **Sélectionnez votre propre marque** (et non "Toutes"). Active le calcul de l'IMR de la Marque, de l'IPC et de la Tendance. |
        
        ### 📊 Interprétation des Indicateurs Clés
        | Indicateur (KPI) | Lecture et Objectif | Interprétation Stratégique |
        | :--- | :--- | :--- |
        | **IMR de la Marque** | Mesure la gravité pondérée des rappels de votre marque. **Cible : le plus bas possible (ex: < 5)**. | **Performance :** S'il est **élevé (ex: > 10)**, vous avez un problème de maîtrise du risque grave, souvent lié à la sécurité alimentaire (Listeria, Salmonella). |
        | **Indice de Pression Concurrentielle (IPC)** | Votre IMR / IMR du Marché. **Cible : < 1.0 (Idéalement 0.90-0.95)**. | **Benchmarking :** Si **IPC > 1.0**, vous êtes **moins performant/plus risqué** que la moyenne de votre catégorie. Si **IPC < 1.0**, vous avez un avantage concurrentiel sur la maîtrise du risque. |
        | **Taux d'Impact Fournisseur Critique (TIFC)** | % des rappels dont la cause est externe. **Cible : le plus bas possible (< 5%)**. | **Achats/Fournisseurs :** Un TIFC élevé pointe un défaut dans l'audit ou la spécification de vos fournisseurs T1. |
        """)
    
    # --- KPI FABRICANT (4 colonnes x 2 lignes = 8 KPIs) ---
    col1, col2, col3, col4 = st.columns(4)
    col5, col6, col7, col8 = st.columns(4)
    
    # LIGNE 1 : PRESSION & CONTEXTE
    with col1:
        st.metric("Total Rappels (Périmètre)", total_rappels, 
            help="Nombre total de fiches de rappel publiées, tenant compte de la période et des filtres sélectionnés. 📈 **Message :** Mesure la **pression volume** globale.")
    with col2:
        st.metric("IMR du Marché", f"{imr_marche_comp:.2f}",
            help="Indice de Maîtrise du Risque (IMR) calculé sur l'ensemble des marques dans la période filtrée. 📊 **Benchmark :** Point de référence pour évaluer la performance de votre marque.")
    with col3:
        st.metric("Risque Principal", risque_principal,
            help="Le risque encouru le plus fréquemment mentionné. ⚠️ **Priorité :** Indique le danger sanitaire ou physique majeur à adresser en priorité.")
    with col4:
        st.metric("Taux d'Impact Fournisseur Critique (TIFC)", f"{tifc_value:.1f}%",
            help="Proportion des rappels dont la cause est liée à une non-conformité fournisseur. 🚨 **Contrôle :** Un TIFC élevé suggère des audits fournisseurs insuffisants ou une faible spécification d'achat.")
    
    # LIGNE 2 : PERFORMANCE & PROJECTION
    with col5:
        # IMR de la Marque avec Traffic Light (Bas est meilleur)
        st.metric("IMR de la Marque", f"{imr_marque:.2f}", delta=f"Cible < {SEUIL_IMR_ALERTE}", delta_color=imr_marque_color,
            help="Indice de Maîtrise du Risque de votre marque (Score Gravité Pondéré). 🎯 **Performance :** L'objectif est de maintenir un score bas (moins de risque) et stable.")
    with col6:
        # IPC avec Traffic Light (Proche de 1.0 est meilleur)
        st.metric("Indice de Pression Concurrentielle (IPC)", f"{ipc_value:.2f}", delta=f"Vs Cible 1.0 (Marché)", delta_color=ipc_color, 
            help="Formule : IMR Marque / IMR Marché. 📉 **Positionnement :** Un score **supérieur à 1.0** indique une **sous-performance** (votre marque est plus risquée que la moyenne du marché).")
    with col7:
        st.metric("Coût Implicite", f"{cout_marque:,.0f} €",
            help="Coût de rappel simulé (Graves x 50K€ + Mineurs x 5K€). 💰 **Impact :** Chiffre la perte financière minimale due à la crise.")
    with col8:
        st.metric("Indice de Sévérité du Risque (ISR)", f"{isr_value:.2f}",
            help="Gravité Moyenne Pondérée par le Volume de Rappels dans la Catégorie. 🧭 **Stratégie :** Aide à réorienter les budgets de prévention vers les catégories de produits les plus dangereuses.")

    st.markdown("### Analyse de Positionnement et Causes Racines")
    st.markdown("---") # Séparation visuelle
    col_gauche, col_droite = st.columns(2)

    with col_gauche:
        st.subheader("1. Benchmark : Part de Rappel par Marque (SoR)")
        
        if "nom_marque_du_produit" in df_filtered.columns and total_rappels > 0:
            top_marques = df_filtered["nom_marque_du_produit"].value_counts(normalize=True).mul(100).reset_index().rename(columns={
                "nom_marque_du_produit": "Marque", 
                "proportion": "Part_de_Rappel_pourcent"
            })
            top_marques = top_marques.head(10)
            fig_sor = px.bar(top_marques, y="Marque", x="Part_de_Rappel_pourcent", orientation='h', title="Top 10 : Contribution (%) aux rappels du marché",
                             color='Part_de_Rappel_pourcent', color_continuous_scale=px.colors.sequential.Plotly3)
            fig_sor.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Part (%) des Rappels Filtrés")
            st.plotly_chart(fig_sor, use_container_width=True)
        else:
            st.info("Aucune donnée pour le benchmarking des marques.")

    with col_droite:
        st.subheader("2. Tendance : IMR de la Marque vs. Marché (Courbe de Contrôle)")
        if marque != "Toutes" and "date_publication" in df_filtered.columns:
            
            df_trend = df.copy()
            if offset:
                df_trend = df_trend[df_trend["date_publication"] >= now - offset]
            df_trend["Mois"] = df_trend["date_publication"].dt.to_period("M")

            def compute_imr_per_month(df_input):
                if 'risques_encourus' not in df_input.columns or df_input.empty:
                    return pd.DataFrame()
                    
                df_input['is_risque_grave'] = df_input["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
                df_input['score_gravite'] = np.where(df_input['is_risque_grave'], 2, 1)
                
                imr_monthly = df_input.groupby('Mois').agg(
                    Total_Score=('score_gravite', 'sum'),
                    Total_Rappels=('score_gravite', 'count')
                ).reset_index()
                
                imr_monthly['IMR'] = np.where(imr_monthly['Total_Rappels'] > 0, 
                                              (imr_monthly['Total_Score'] / imr_monthly['Total_Rappels']) * 10, 
                                              0.0)
                imr_monthly['Mois'] = imr_monthly['Mois'].dt.to_timestamp()
                return imr_monthly[['Mois', 'IMR']]

            df_imr_marque = compute_imr_per_month(df_trend[df_trend["nom_marque_du_produit"] == marque])
            df_imr_marche = compute_imr_per_month(df_trend)
            
            if not df_imr_marque.empty or not df_imr_marche.empty:
                df_imr_marche = df_imr_marche.rename(columns={'IMR': 'IMR_Marché'})
                
                df_comp = pd.merge(df_imr_marque.rename(columns={'IMR': f'IMR_{marque.title()}'}), df_imr_marche, on='Mois', how='outer').fillna(0)
                
                fig_trend = px.line(df_comp, x="Mois", y=[f"IMR_{marque.title()}", "IMR_Marché"], 
                                    title=f"Évolution Mensuelle de l'IMR : {marque.title()} vs. Marché (Seuil Alerte {SEUIL_IMR_ALERTE})",
                                    labels={"value": "IMR (Score Pondéré)", "Mois": "Mois"},
                                    color_discrete_map={f'IMR_{marque.title()}': '#2C3E50', 'IMR_Marché': '#BDC3C7'},
                                    line_shape='spline', markers=True)
                
                fig_trend.add_hline(y=SEUIL_IMR_ALERTE, line_dash="dot", line_color="red", 
                                    annotation_text="Seuil Alerte IMR", 
                                    annotation_position="top right")

                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("Sélectionnez une marque dans la sidebar pour afficher l'IMR et la tendance.")

    st.markdown("---")
    # Donut Chart NCF Fournisseur / Matrice Corrélation
    total_fournisseurs_t1 = 100 # Simulé
    total_fournisseurs_impactes = 15 # Simulé
    if 'identifiant_de_l_etablissement_d_ou_provient_le_produit' in df_filtered.columns and total_fournisseurs_impactes > 0:
        st.subheader("3. Dépendance au Risque Fournisseur (NCF T1)")
        df_ncf = pd.DataFrame({
            'Type': ['Fournisseurs Impactés', 'Fournisseurs non Impactés'],
            'Count': [total_fournisseurs_impactes, max(0, total_fournisseurs_t1 - total_fournisseurs_impactes)]
        })
        fig_donut = px.pie(df_ncf, values='Count', names='Type', hole=.5, 
                           title=f"Taux de Non-Conformité (NCF) des {total_fournisseurs_t1} Fournisseurs T1 (Simulé)",
                           color_discrete_sequence=['#E74C3C', '#2ECC71'])
        st.plotly_chart(fig_donut, use_container_width=True)
    else:
         st.markdown("### 3. Corrélation : Matrice des Motifs vs. Risques")
         if "risques_encourus" in df_filtered.columns and "motif_du_rappel" in df_filtered.columns:
            df_corr = df_filtered.copy()
            df_corr["Motif_court"] = df_corr["motif_du_rappel"].str.split(r'[;.,]').str[0].str.strip()
            
            df_exploded_motif_risque = df_corr.assign(risques_encourus=df_corr['risques_encourus'].str.split(';')).explode('risques_encourus')
            df_exploded_motif_risque['risques_encourus'] = df_exploded_motif_risque['risques_encourus'].str.strip()
            
            if df_exploded_motif_risque.empty:
                st.info("Pas assez de données pour générer la matrice de corrélation Motif/Risque (après explosion des risques).")
            else:
                cooccurrence = df_exploded_motif_risque.groupby(['Motif_court', 'risques_encourus']).size().reset_index(name='Nombre')
                cooccurrence = cooccurrence[cooccurrence['Nombre'] > 0]
                
                top_motifs_list = cooccurrence['Motif_court'].value_counts().head(5).index
                top_risques_list = cooccurrence['risques_encourus'].value_counts().head(5).index
                
                cooccurrence_filtered = cooccurrence[
                    cooccurrence['Motif_court'].isin(top_motifs_list) & 
                    cooccurrence['risques_encourus'].isin(top_risques_list)
                ]
                
                if not cooccurrence_filtered.empty:
                    fig_heatmap = px.density_heatmap(cooccurrence_filtered, x="Motif_court", y="risques_encourus", z="Nombre", 
                                                     title="Fréquence d'association des Top 5 Motifs et Top 5 Risques",
                                                     text_auto=True, color_continuous_scale="Plasma")
                    st.plotly_chart(fig_heatmap, use_container_width=True)
                else:
                    st.info("Pas assez de données pour générer la matrice de corrélation Motif/Risque.")
         else:
             st.info("Colonnes de risque et/ou de motif manquantes pour la matrice.")


# ----------------------------------------------------------------------
# TAB 2: DISTRIBUTEURS & RETAILERS (MATRICE DE RISQUE LOGISTIQUE & GÉOSPATIALITÉ)
# ----------------------------------------------------------------------
with tab2:
    st.header("🛒 Analyse du Canal de Distribution & Risque Logistique")

    # --- FEUILLE DE ROUTE DISTRIBUTEURS ---
    with st.expander("📖 Feuille de Route : Filtrage et Interprétation pour Distributeurs/Retailers"):
        st.markdown("""
        Cet onglet est conçu pour les équipes de **Supply Chain**, **Logistique**, et **Opérations Commerciales**.

        ### ⚙️ Stratégie de Filtrage Recommandée
        | Étape | Filtre à Appliquer | Objectif du Filtre |
        | :---: | :--- | :--- |
        | **1.** | **Période d'Analyse** | **"12 ou 6 derniers mois"** pour analyser l'efficacité de vos procédures de retrait/rappel et les risques logistiques. |
        | **2.** | **Distributeur (Canal)** | **Sélectionnez votre réseau ou un concurrent.** Isole l'impact des rappels au sein du canal spécifique pour le benchmark. |
        | **3.** | **Motif de Rappel** | **(Optionnel)** Filtrer sur les motifs logistiques (ex: "température", "rupture") pour calculer le Taux d'Anomalie Logistique (TAL) spécifique. |
        | **4.** | **Lieu de Vente (Zone Géographique)** | **(Optionnel)** Isole une région ou un département pour analyser les problématiques locales. |

        ### 📊 Interprétation des Indicateurs Clés
        | Indicateur (KPI) | Lecture et Objectif | Interprétation Stratégique |
        | :--- | :--- | :--- |
        | **Délai Moyen (DM) Avant Rappel** | Durée moyenne entre la commercialisation et la publication du rappel. **Cible : le plus bas possible**. | **Réactivité :** Un DM long signifie une exposition prolongée des consommateurs. Implique une amélioration des alertes en magasin et des systèmes d'information. |
        | **Taux d'Anomalie Logistique (TAL)** | % des rappels liés à des causes de transport, stockage ou distribution. **Cible : le plus bas possible (< 3%)**. | **Supply Chain :** Un TAL élevé pointe directement des faiblesses dans le réseau de distribution, le respect de la chaîne du froid, ou le stockage en entrepôt. |
        | **Matrice de Priorisation du Risque** | Classement des distributeurs selon la fréquence et le délai avant rappel. | **Négociation/Audit :** Les partenaires dans le quadrant **"Risque Élevé"** (Fréquence Élevée + Délai Long) sont les plus coûteux et doivent être audités en priorité. |
        """)

    # --- KPI DISTRIBUTEUR (4 colonnes x 2 lignes = 8 KPIs) ---
    col1, col2, col3, col4 = st.columns(4)
    col5, col6, col7, col8 = st.columns(4)
    
    # LIGNE 1 : PRESSION & CONTEXTE
    with col1:
        st.metric("Total Rappels (Filtré)", total_rappels,
            help="Nombre total de fiches de rappel publiées, tenant compte de la période et des filtres sélectionnés. 📈 **Message :** Mesure la **pression volume** globale.")
    with col2:
        st.metric("Score d'Exposition Géographique (Simulé)", "Élevé" if total_rappels > SEUIL_ORANGE_MAX * 5 else "Faible",
            help="Évaluation simplifiée de l'impact potentiel du rappel (volume et densité). 🗺️ **Logistique :** Un score élevé signifie que la charge logistique et la pression médiatique sont maximales pour les zones de vente concernées.")
    with col3:
        st.metric("Délai Moyen (DM) Avant Rappel", DM_label,
            help="Moyenne des (Date Publication - Date Début Commercialisation) en jours. ⏱️ **Réactivité :** Plus ce délai est long, plus l'exposition du consommateur au risque a été importante (faible réactivité interne).")
    with col4:
        st.metric("Taux d'Anomalie Logistique (TAL)", f"{tal_value:.1f}%",
            help="Pourcentage des rappels dont le motif est lié à un défaut de distribution/stockage. 📦 **Chaîne de Froid :** Un TAL élevé pointe directement vers des faiblesses dans le réseau de distribution ou le stockage en magasin.")
        
    # LIGNE 2 : PERFORMANCE & PROJECTION
    with col5:
        st.metric("Délai d'Alerte Précoce (DAP)", f"{dap_value:.1f}%",
            help="Proportion des rappels dont la durée de commercialisation a été très courte (< 7 jours). 💡 **Efficacité :** Un DAP élevé peut indiquer que vos systèmes d'alerte internes sont lents, ou au contraire que le contrôle externe est très rapide.")
    with col6:
        st.metric("Coût Logistique Max/Distributeur", f"{COUT_LOGISTIQUE_JOUR_SUPP:,.0f} € / Jour",
            help="Coût simulé d'un jour d'exposition au risque logistique par rappel. 💸 **Négociation :** Sert de base pour prioriser les distributeurs ayant le risque de *durée* le plus coûteux.")
    with col7:
        if "distributeurs" in df_filtered.columns:
            df_distrib_exploded = explode_column(df_filtered, 'distributeurs')
            distrib_counts = df_distrib_exploded['distributeurs'].value_counts()
            densite_distrib = distrib_counts.mean() if not distrib_counts.empty else 0.0
            st.metric("Densité Moy. Rappel/Distributeur", f"{densite_distrib:.1f}",
                help="Total Rappels (Filtré) / Nombre de Distributeurs Uniques Impliqués. ⚖️ **Concentration :** Mesure la fréquence d'incidents chez les partenaires. Un ratio élevé indique une dépendance à des distributeurs plus risqués.")
        else:
            st.metric("Densité Moy. Rappel/Distributeur", "N/A",
                help="Total Rappels (Filtré) / Nombre de Distributeurs Uniques Impliqués. ⚖️ **Concentration :** Mesure la fréquence d'incidents chez les partenaires. Un ratio élevé indique une dépendance à des distributeurs plus risqués.")
    with col8:
        taux_couverture_rappel = 85.0 # Simulé
        st.metric("Taux de Couverture du Rappel (TCR) (Simulé)", f"{taux_couverture_rappel:.1f}%", 
            help="Pourcentage des zones géographiques couvertes par une action de retrait documentée. ✅ **Conformité :** Évalue l'efficacité et l'exhaustivité de l'exécution du plan de retrait sur le terrain.")


    st.markdown("### 1. Matrice de Priorisation du Risque Distributeur (Bubble Chart)")
    st.markdown("---") # Séparation visuelle
    
    if "date_debut_commercialisation" in df_filtered.columns and "distributeurs" in df_filtered.columns:
            
        df_reponse = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation", "distributeurs"]).copy()
        
        if df_reponse.empty:
            st.info("⚠️ Les filtres appliqués n'ont généré aucune donnée valide pour la Matrice de Risque Distributeur.")
        else:
            df_reponse = df_reponse.assign(distributeurs=df_reponse['distributeurs'].str.split(';')).explode('distributeurs')
            df_reponse['distributeurs'] = df_reponse['distributeurs'].str.strip()
            df_reponse = df_reponse[df_reponse['distributeurs'] != '']
            
            if df_reponse.empty:
                st.info("⚠️ Les données de distributeurs sont vides après nettoyage et explosion. (Vérifiez les valeurs de la colonne 'distributeurs')")
            else:
                df_reponse["Délai_Jours"] = (df_reponse["date_publication"] - df_reponse["date_debut_commercialisation"]).dt.days
                df_reponse = df_reponse[df_reponse["Délai_Jours"] >= 0]
                
                if 'risques_encourus' in df_reponse.columns:
                    df_reponse['is_risque_grave'] = df_reponse["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
                    df_reponse['Score_Gravite'] = np.where(df_reponse['is_risque_grave'], 2, 1) 
                else:
                    df_reponse['Score_Gravite'] = 1
                
                avg_distrib = df_reponse.groupby("distributeurs").agg(
                    Délai_Moyen_Jours=('Délai_Jours', 'mean'),
                    Nb_Rappels=('Délai_Jours', 'count'),
                    Gravite_Moyenne=('Score_Gravite', 'mean')
                ).reset_index()
                
                # Coût d'exposition au risque simulé (en k€)
                avg_distrib['Coût_Risque_Simulé'] = avg_distrib['Délai_Moyen_Jours'] * avg_distrib['Nb_Rappels'] * avg_distrib['Gravite_Moyenne'] * COUT_LOGISTIQUE_JOUR_SUPP / 1000 
                
                if not avg_distrib.empty:
                    fig_bubble = px.scatter(avg_distrib, 
                                            x="Délai_Moyen_Jours", 
                                            y="Nb_Rappels", 
                                            size="Coût_Risque_Simulé", 
                                            color="Gravite_Moyenne",
                                            hover_name="distributeurs",
                                            size_max=40,
                                            title="Matrice de Priorisation du Risque Distributeur (Coût Logistique/Jours Simulé)",
                                            labels={
                                                "Délai_Moyen_Jours": "Axe X: Délai Moyen avant Rappel (Jours) ➡ Risque de Durée",
                                                "Nb_Rappels": "Axe Y: Fréquence des Rappels ➡ Risque de Volume",
                                                "Gravite_Moyenne": "Gravité Moyenne (Couleur)",
                                                "Coût_Risque_Simulé": "Coût d'Exposition au Risque Simulé (k€)"
                                            },
                                            color_continuous_scale=px.colors.sequential.YlOrRd)
                    
                    if not avg_distrib.empty:
                        fig_bubble.add_vline(x=avg_distrib['Délai_Moyen_Jours'].median(), line_dash="dash", line_color="#34495E")
                        fig_bubble.add_hline(y=avg_distrib['Nb_Rappels'].median(), line_dash="dash", line_color="#34495E")

                    fig_bubble.update_layout(xaxis_range=[0, avg_distrib['Délai_Moyen_Jours'].max() * 1.1])
                    st.plotly_chart(fig_bubble, use_container_width=True)
                else:
                    st.info("Données insuffisantes pour la matrice de risque distributeur (après agrégation).")
    else:
        st.info("Colonnes de date de commercialisation et/ou distributeurs manquantes.")
        
    
    st.markdown("---") # Séparation visuelle
    st.subheader("2. Score de Risque Géographique (Traffic Light) ")
    st.caption(f"Seuils : 🟢 0-{SEUIL_VERT_MAX} rappels, 🟠 {SEUIL_VERT_MAX+1}-{SEUIL_ORANGE_MAX} rappels, 🔴 >{SEUIL_ORANGE_MAX} rappels.")

    if "zone_geographique_de_vente" in df_filtered.columns:
        df_geo = explode_column(df_filtered, "zone_geographique_de_vente")
        
        # Tentative d'extraction du code départemental/régional (très simplifié)
        df_geo['zone_clean'] = df_geo['zone_geographique_de_vente'].str.extract(r'(\d{2,3})') 
        df_geo.loc[df_geo['zone_clean'].isna(), 'zone_clean'] = df_geo.loc[df_geo['zone_clean'].isna(), 'zone_geographique_de_vente'].str.split('-').str[0].str.strip()
        df_geo = df_geo.dropna(subset=['zone_clean'])
        
        # Agrégation par zone
        geo_counts = df_geo.groupby('zone_clean').size().reset_index(name='Nombre_Rappels')
        
        if not geo_counts.empty:
            # Attribution du Traffic Light
            geo_counts['Niveau_Risque'] = geo_counts['Nombre_Rappels'].apply(get_traffic_light)
            
            # Affichage de la carte Choropleth si GeoJSON disponible (avec attribution de couleur)
            if geojson_data:
                
                st.info("✅ GeoJSON détecté. Affichage de la carte de risque géospatial (Taille ajustée).")
                
                def get_plotly_color(count):
                    if count <= SEUIL_VERT_MAX: return '#2ECC71' # Green
                    elif count <= SEUIL_ORANGE_MAX: return '#F39C12' # Orange
                    else: return '#E74C3C' # Red
                
                geo_counts['Couleur_Hex'] = geo_counts['Nombre_Rappels'].apply(get_plotly_color)
                
                try:
                    fig_map = px.choropleth(geo_counts,
                                            geojson=geojson_data,
                                            locations='zone_clean',
                                            featureidkey="properties.code", 
                                            color='Nombre_Rappels', 
                                            hover_name='zone_clean',
                                            color_continuous_scale=["#2ECC71", "#F39C12", "#E74C3C"], 
                                            range_color=[0, SEUIL_ORANGE_MAX + 1], 
                                            title="Répartition Géospatiale du Risque (Traffic Light)",
                                            height=1000) 
                    
                    fig_map.update_geos(
                        fitbounds="locations", 
                        visible=False,
                        center={"lat": 46.603354, "lon": 1.888334}, 
                        projection_scale=3 
                    )
                    fig_map.update_layout(coloraxis_showscale=False) 
                    
                    st.plotly_chart(fig_map, use_container_width=True)
                except Exception as e:
                    st.warning(f"⚠️ Impossible d'afficher la carte Choropleth (Erreur Plotly : {e}). Vérifiez la correspondance des codes dans le GeoJSON.")
                    
                    # Affichage du tableau de bord Traffic Light (Méthode de repli)
                    st.dataframe(geo_counts[['zone_clean', 'Nombre_Rappels', 'Niveau_Risque']].rename(columns={
                        'zone_clean': 'Zone Géographique', 
                        'Nombre_Rappels': 'Nbre de Rappels'
                    }).sort_values(by='Nbre de Rappels', ascending=False), 
                    hide_index=True, use_container_width=True)

            else:
                # Affichage du tableau de bord Traffic Light (par défaut si pas de GeoJSON)
                st.info("Impossible de charger la carte Choropleth (GeoJSON manquant). Affichage du tableau de bord Traffic Light par Zone de Vente.")
                
                st.markdown("---")
                st.markdown("#### Tableau de Risque Géographique (Repli)")
                st.dataframe(geo_counts[['zone_clean', 'Nombre_Rappels', 'Niveau_Risque']].rename(columns={
                    'zone_clean': 'Zone Géographique', 
                    'Nombre_Rappels': 'Nbre de Rappels'
                }).sort_values(by='Nbre de Rappels', ascending=False), 
                hide_index=True, use_container_width=True)
                
        else:
            st.info("Données de zone géographique de vente insuffisantes pour l'analyse Traffic Light.")
    else:
        st.info("Colonne 'zone_geographique_de_vente' manquante pour l'analyse géospatiale.")


# ----------------------------------------------------------------------
# TAB 3: RISQUE & CONFORMITÉ (DÉRIVE DES CAUSES RACINES & PROFIL DE RISQUE)
# ----------------------------------------------------------------------
with tab3:
    st.header("🔬 Évaluation de la Gravité et Tendance du Risque (Assurance & Conseil)")
    
    # --- FEUILLE DE ROUTE CONFORMITÉ ---
    with st.expander("📖 Feuille de Route : Filtrage et Interprétation pour Risque/Conformité/Audit"):
        st.markdown("""
        Cet onglet est conçu pour les équipes d'**Audit Interne**, **Qualité/HACCP** et les **Consultants en Risque**.

        ### ⚙️ Stratégie de Filtrage Recommandée
        | Étape | Filtre à Appliquer | Objectif du Filtre |
        | :---: | :--- | :--- |
        | **1.** | **Période d'Analyse** | **"12 derniers mois"** pour la Volatilité IMR (IMR_STD) ou **"Toute la période"** pour le Taux de Récurrence (TRCR). |
        | **2.** | **Catégorie de Produit** | **Sélectionner la catégorie la plus risquée** (celle avec l'IMR le plus élevé dans l'onglet 1) pour une analyse approfondie. |
        | **3.** | **Marque / Nature du Produit** | **(Optionnel)** Isolez les produits spécifiques pour comprendre l'origine de la Volatilité (DCR). |
        | **4.** | **Statut de la Fiche** | Filtrer sur **"Rappel en cours"** pour évaluer la charge de risque actuelle non résolue. |

        ### 📊 Interprétation des Indicateurs Clés
        | Indicateur (KPI) | Lecture et Objectif | Interprétation Stratégique |
        | :--- | :--- | :--- |
        | **% Rappels Graves** | Proportion de rappels concernant des risques majeurs (Listeria, Salmonelle, corps étranger). **Cible : 0%**. | **Audit Critique :** Si > 5%, révision urgente des CCP (Critical Control Points) et des plans HACCP. |
        | **Volatilité IMR (IMR_STD)** | Mesure l'instabilité de votre risque dans le temps (Écart-type de l'IMR mensuel). **Cible : le plus bas possible**. | **Maîtrise :** Une forte volatilité indique un manque de stabilité dans le système qualité (contrôles non systématiques ou aléatoires). |
        | **Taux de Récurrence des Causes Racines (TRCR)** | % des rappels liés à une cause déjà observée (ex: Listeria récurrente). **Cible : 0%**. | **Échec Correctif :** Un TRCR élevé indique que les actions correctives (CAPA) précédentes n'ont pas été efficaces. Nécessite un audit du processus de gestion des non-conformités. |
        | **Dérive des Causes Racines (DCR)** | Graphique de tendance du classement des motifs. | **Veille Réglementaire :** Si un motif monte rapidement dans le classement (ex: étiquetage), cela peut indiquer un nouveau manquement réglementaire ou une dérive d'un fournisseur T1. |
        """)
    
    # --- KPI CONFORMITÉ (4 colonnes x 2 lignes = 8 KPIs) ---
    col1, col2, col3, col4 = st.columns(4)
    col5, col6, col7, col8 = st.columns(4)
    
    # LIGNE 1 : PRESSION & CONTEXTE
    with col1:
        st.metric("Total Rappels (Filtré)", total_rappels,
            help="Nombre total de fiches de rappel publiées, tenant compte de la période et des filtres sélectionnés. 📈 **Message :** Mesure la **pression volume** globale.")
    with col2:
        st.metric("% Rappels Graves", pc_risques_graves_str,
            help="Proportion des rappels dont le risque est jugé grave. 🛑 **Gravité :** Un taux élevé justifie un renforcement immédiat des contrôles qualité critiques (CCP).")
    with col3:
        st.metric("Taux de Récurrence des Causes Racines (TRCR)", f"{trcr_value:.1f}%",
            help="Pourcentage des rappels dont la cause racine a déjà été observée dans le passé. 🔁 **Audit :** Un TRCR élevé indique un **échec des actions correctives** et nécessite un audit du système qualité.")
    with col4:
        if not df_risques_exploded.empty:
            diversite_risques = df_risques_exploded['risques_encourus'].nunique()
            st.metric("Diversité des Risques", diversite_risques, 
                help="Nombre de types de risques encourus différents identifiés. 🤯 **Systémique :** Une grande diversité signale des problèmes de maîtrise générale plutôt qu'un risque ponctuel.")
        else:
            st.metric("Diversité des Risques", "N/A", 
                help="Nombre de types de risques encourus différents identifiés. 🤯 **Systémique :** Une grande diversité signale des problèmes de maîtrise générale plutôt qu'un risque ponctuel.")
        
    # LIGNE 2 : PERFORMANCE & PROJECTION
    with col5:
        st.metric("Volatilité IMR (IMR_STD)", f"{imr_std_value:.2f}",
            help="Écart-type (STD) des valeurs mensuelles de l'IMR sur 6 mois. 🎢 **Stabilité :** Une forte volatilité indique que le risque n'est pas maîtrisé et varie fortement d'un mois à l'autre (imprévisibilité).")
    with col6:
        df_vol = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="Rappels")
        volatilite = df_vol["Rappels"].std() if not df_vol.empty and len(df_vol) > 1 else 0
        st.metric("Volatilité Mensuelle Rappel", f"{volatilite:.1f}",
            help="Écart-type (STD) du nombre de rappels publiés chaque mois sur la période filtrée. 🌪️ **Planification :** Une forte volatilité complique la planification des ressources de gestion de crise.")
    with col7:
        if "motif_du_rappel" in df_filtered.columns and "risques_encourus" in df_filtered.columns and not df_filtered.empty:
            df_temp_imr = df_filtered.copy()
            df_temp_imr["is_risque_grave"] = df_temp_imr["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
            df_temp_imr['score_gravite'] = np.where(df_temp_imr['is_risque_grave'], 2, 1)

            motif_graves = df_temp_imr.groupby('motif_du_rappel')['score_gravite'].mean().reset_index()
            top_motifs_graves = motif_graves.sort_values(by='score_gravite', ascending=False).head(1)
            
            rmpc = top_motifs_graves['score_gravite'].mean() * 10 if not top_motifs_graves.empty else 0.0
            st.metric("RMPC (Simulé)", f"{rmpc:.2f}", help="Risque Moyen Pondéré par Catégorie (RMPC). 💡 **Analyse :** Aide à identifier les motifs qui, bien que peu fréquents, portent la plus grande charge de risque (gravité élevée).")
        else:
            st.metric("RMPC (Simulé)", "N/A", help="Risque Moyen Pondéré par Catégorie (RMPC). 💡 **Analyse :** Aide à identifier les motifs qui, bien que peu fréquents, portent la plus grande charge de risque (gravité élevée).")
    with col8:
        st.metric("Ratio Risque/Opportunité (RRO)", f"{rro_value:.2f}",
            help="Simule si le niveau de risque (IMR) est justifié par l'activité dans la catégorie. 🚀 **R&D :** Un score élevé (mauvais) suggère que l'entreprise prend des risques disproportionnés par rapport à l'activité concurrentielle du secteur.")


    st.markdown("### 1. Tendance : Dérive des Causes Racines (DCR) - Taux d'Émergence des Motifs")
    st.markdown("---") # Séparation visuelle
    
    if "date_publication" in df_filtered.columns and "motif_du_rappel" in df_filtered.columns:
        
        df_trend = df_filtered.copy()
        
        if df_trend.empty:
            st.info("⚠️ Les données filtrées sont vides pour l'analyse des tendances.")
        else:
            df_trend["Mois"] = df_trend["date_publication"].dt.to_period("M")
            
            df_motifs = explode_column(df_trend, "motif_du_rappel")
            
            if not df_motifs.empty:
                df_motifs = df_motifs.reset_index().rename(columns={'index': 'original_index'})
                df_motifs_merged = pd.merge(df_motifs, df_trend[['Mois']].reset_index().rename(columns={'index': 'original_index'}), on='original_index', how='left')
                
                motif_counts = df_motifs_merged.groupby(['Mois', 'motif_du_rappel']).size().reset_index(name='Rappels')
                motif_counts['Rang'] = motif_counts.groupby('Mois')['Rappels'].rank(method='first', ascending=False)
                
                top_motifs_global = motif_counts['motif_du_rappel'].value_counts().head(5).index
                df_rank = motif_counts[motif_counts['motif_du_rappel'].isin(top_motifs_global)].copy()
                
                df_rank['Mois'] = df_rank['Mois'].dt.to_timestamp()
                
                if not df_rank.empty:
                    fig_bump = px.line(df_rank, 
                                       x="Mois", 
                                       y="Rang", 
                                       color="motif_du_rappel", 
                                       line_shape='spline',
                                       markers=True,
                                       title="Évolution du Classement (Rang) des 5 Principaux Motifs de Rappel",
                                       labels={"Rang": "Classement (1 = Plus Fréquent)", "Mois": "Mois"},
                                       color_discrete_sequence=px.colors.qualitative.Dark24)
                    
                    fig_bump.update_yaxes(autorange="reversed", tickvals=[1, 2, 3, 4, 5], title="Classement (1 = le plus fréquent)")
                    fig_bump.update_traces(marker=dict(size=10))
                    
                    st.plotly_chart(fig_bump, use_container_width=True)
                else:
                    st.info("Données insuffisantes pour la Dérive des Causes Racines.")
            else:
                 st.info("Données de motif de rappel insuffisantes après nettoyage.")
    else:
        st.info("Colonnes manquantes pour l'analyse des motifs.")

    st.markdown("---") # Séparation visuelle
    st.subheader("2. Profil de Risque (Radar Chart RMPC)")
    
    if "categorie_de_produit" in df_filtered.columns and "risques_encourus" in df_filtered.columns:
        df_radar = df_filtered.copy()
        
        if df_radar.empty:
            st.info("⚠️ Les données filtrées sont vides. Ajustez les filtres pour générer le Profil de Risque (Radar Chart).")
        else:
            df_radar['is_risque_grave'] = df_radar["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
            df_radar['score_gravite'] = np.where(df_radar['is_risque_grave'], 2, 1)

            cat_scores = df_radar.groupby('categorie_de_produit').agg(
                RMPC=('score_gravite', 'mean'),
                Frequence=('categorie_de_produit', 'count')
            ).reset_index()
            
            cat_scores['RMPC'] = cat_scores['RMPC'] * 10 
            
            top_cats = cat_scores.sort_values(by='Frequence', ascending=False).head(5)
            
            if not top_cats.empty:
                fig_radar = px.line_polar(top_cats, r='RMPC', theta='categorie_de_produit', line_close=True,
                                          title="Profil de Risque Moyen Pondéré par Catégorie (RMPC)",
                                          color_discrete_sequence=['#E67E22'])
                fig_radar.update_traces(fill='toself')
                fig_radar.update_layout(polar=dict(
                    radialaxis=dict(visible=True, range=[0, 20])
                ))
                st.plotly_chart(fig_radar, use_container_width=True)
            else:
                st.info("Données insuffisantes pour le Profil de Risque (Radar Chart) : aucune catégorie fréquente identifiée.")
    else:
         st.info("Données de risque et/ou de catégorie manquantes.")


st.markdown("---")

# --- 6. TABLEAU DE DONNÉES DÉTAILLÉ ---
with st.expander("🔍 Registre Détaillé des Rappels (Filtré)"):
    display_cols = [c for c in ["reference_fiche", "date_publication", "date_debut_commercialisation", "categorie_de_produit", "nom_marque_du_produit", "motif_du_rappel", "risques_encourus", "distributeurs", "zone_geographique_de_vente", "liens_vers_la_fiche_rappel"] if c in df_filtered.columns]
    
    st.dataframe(df_filtered[display_cols].sort_values(by="date_publication", ascending=False).reset_index(drop=True), use_container_width=True)

    csv = df_filtered[display_cols].to_csv(index=False).encode('utf-8')
    st.download_button(label="💾 Télécharger les Données Filtrées (CSV)", data=csv, file_name="recall_analytics_export_filtered.csv", mime="text/csv")


st.caption("Prototype Recall Analytics — Données publiques (c) RappelConso.gouv.fr / Ministère de l'Économie")
