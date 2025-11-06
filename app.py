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

# --- NOUVELLES CONSTANTES : LOGIQUE TRAFFIC LIGHT ---
SEUIL_VERT_MAX = 5     
SEUIL_ORANGE_MAX = 15  

# Fonction pour attribuer un "Traffic Light"
def get_traffic_light(count):
    if count <= SEUIL_VERT_MAX:
        return "🟢 Faible (Green)"
    elif count <= SEUIL_ORANGE_MAX:
        return "🟠 Modéré (Amber)"
    else:
        return "🔴 Critique (Red)"

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
            "nom_fabricant_ou_marque": "nom_marque_du_produit" 
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

        for col in ["distributeurs", "zone_geographique_de_vente", "risques_encourus", "motif_du_rappel", "categorie_de_produit", "nom_marque_du_produit", "identifiant_de_l_etablissement_d_ou_provient_le_produit"]:
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
        return ["Toutes"] + sorted(list(set(valid_list)))
    
    return ["Toutes"]

# --- 3. CHARGEMENT ET FILTRES GLOBAUX ---
df = load_data_from_csv()
geojson_data = load_geojson() 

if df.empty:
    st.stop()

# --- SIDEBAR: FILTRES GLOBAUX ---
st.sidebar.header("⚙️ Filtres Transversaux")
df_temp = df.copy()

distributeurs_list = safe_filter_list(df_temp, "distributeurs", exploded=True)
motifs_list = safe_filter_list(df_temp, "motif_du_rappel")
categories = safe_filter_list(df_temp, "categorie_de_produit")
marques = safe_filter_list(df_temp, "nom_marque_du_produit")

periode = st.sidebar.selectbox("Période d'Analyse", ["12 derniers mois", "6 derniers mois", "3 derniers mois", "Toute la période"])
cat = st.sidebar.selectbox("Catégorie de Produit", categories)
marque = st.sidebar.selectbox("Marque (Benchmarking)", marques)
distrib = st.sidebar.selectbox("Distributeur (Canal)", distributeurs_list)
motif = st.sidebar.selectbox("Motif de Rappel", motifs_list)


# --- APPLICATION DES FILTRES ---
df_filtered = df.copy()

if "date_publication" in df_filtered.columns:
    now = pd.Timestamp.now(tz='UTC') 
    if periode == "12 derniers mois":
        df_filtered = df_filtered[df_filtered["date_publication"] >= now - pd.DateOffset(months=12)]
    elif periode == "6 derniers mois":
        df_filtered = df_filtered[df_filtered["date_publication"] >= now - pd.DateOffset(months=6)]
    elif periode == "3 derniers mois":
        df_filtered = df_filtered[df_filtered["date_publication"] >= now - pd.DateOffset(months=3)]

if cat != "Toutes" and "categorie_de_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["categorie_de_produit"] == cat]
if marque != "Toutes" and "nom_marque_du_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["nom_marque_du_produit"] == marque]
if motif != "Toutes" and "motif_du_rappel" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["motif_du_rappel"] == motif]

if distrib != "Toutes" and "distributeurs" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["distributeurs"].str.contains(distrib, case=False, na=False)]


# --- 4. CALCULS TRANSVERSAUX (KPIs) ---
total_rappels = len(df_filtered)

if total_rappels == 0:
    st.warning("⚠️ Aucun rappel trouvé avec les filtres actuels. Veuillez ajuster la période ou les sélections dans la sidebar.")
    st.stop()


df_risques_exploded = explode_column(df_filtered, "risques_encourus")

# Risque principal
risque_principal = "N/A"
if not df_risques_exploded.empty and "risques_encourus" in df_risques_exploded.columns:
    risque_counts = df_risques_exploded["risques_encourus"].value_counts()
    if not risque_counts.empty:
        risque_major = next(iter(risque_counts.index), None)
        if risque_major:
            risque_principal = risque_major.title()

# Vitesse de Réponse Moyenne (Proxy)
vitesse_reponse = "N/A"
if "date_debut_commercialisation" in df_filtered.columns and not df_filtered["date_debut_commercialisation"].isnull().all():
    df_temp_dates = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation"]).copy()
    if not df_temp_dates.empty:
        df_temp_dates["duree_commercialisation"] = (df_temp_dates["date_publication"] - df_temp_dates["date_debut_commercialisation"]).dt.days
        df_temp_dates = df_temp_dates[df_temp_dates["duree_commercialisation"] >= 0]
        if not df_temp_dates.empty:
            avg_days = df_temp_dates["duree_commercialisation"].mean()
            vitesse_reponse = f"{avg_days:.1f} jours"
    
# --- IMR FUNCTION (Rappel) ---
def calculate_imr(df_calc):
    if df_calc.empty or 'risques_encourus' not in df_calc.columns:
        return 0.0, 0.0

    df_imr = df_calc.copy()
    
    # 1. Calcul de la gravité
    df_imr["is_risque_grave"] = df_imr["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
    df_imr['score_gravite'] = np.where(df_imr['is_risque_grave'], 2, 1) # Risque grave = poids 2, mineur = poids 1
    
    total_rappels_period = len(df_imr)
    total_score = df_imr['score_gravite'].sum()
    
    if total_rappels_period > 0:
        imr = (total_score / total_rappels_period) * 10 
    else:
        imr = 0.0
        
    df_imr['cout_implicite'] = np.where(df_imr['is_risque_grave'], COUT_RAPPEl_GRAVE_UNITAIRE, COUT_RAPPEl_MINEUR_UNITAIRE)
    total_cout = df_imr['cout_implicite'].sum()

    return imr, total_cout

# Calcul de l'IMR pour la marque filtrée
imr_marque, cout_marque = calculate_imr(df_filtered)

# Calcul du % Rappels graves
if total_rappels > 0 and 'risques_encourus' in df_filtered.columns:
    count_graves = df_filtered["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False).sum()
    pc_risques_graves = (count_graves / total_rappels * 100)
    pc_risques_graves_str = f"{pc_risques_graves:.1f}%"
else:
    pc_risques_graves_str = "N/A"

# Calcul de l'IMR pour le marché (pour la comparaison)
if "date_publication" in df.columns:
    df_marche_comp = df[df["date_publication"] >= df_filtered["date_publication"].min()].copy()
    imr_marche_comp, _ = calculate_imr(df_marche_comp)
else:
    imr_marche_comp = 0.0


# --- 5. STRUCTURE DU TABLEAU DE BORD PAR ACTEUR (TABS) ---

tab1, tab2, tab3 = st.tabs(["🏭 Fabricants & Marques", "🛒 Distributeurs & Retailers", "🔬 Risque & Conformité"])


# ----------------------------------------------------------------------
# TAB 1: FABRICANTS & MARQUES (BENCHMARKING IMR & RISQUE FOURNISSEUR)
# ----------------------------------------------------------------------
with tab1:
    st.header("🎯 Intelligence Concurrentielle & Maîtrise du Risque Fournisseur")

    # --- KPI FABRICANT ---
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("Total Rappels (Périmètre)", total_rappels)
    with col2:
        st.metric("IMR de la Marque", f"{imr_marque:.2f}")
    with col3:
        st.metric("IMR du Marché", f"{imr_marche_comp:.2f}")
    with col4:
        st.metric("Coût Implicite", f"{cout_marque:,.0f} €")
    with col5:
        st.metric("Risque Principal", risque_principal)
    
    # NOUVEAU KPI: Taux de Non-Conformité Fournisseur (NCF)
    if 'identifiant_de_l_etablissement_d_ou_provient_le_produit' in df_filtered.columns:
        df_fournisseurs = explode_column(df_filtered, 'identifiant_de_l_etablissement_d_ou_provient_le_produit')
        total_fournisseurs_impactes = df_fournisseurs['identifiant_de_l_etablissement_d_ou_provient_le_produit'].nunique() if not df_fournisseurs.empty else 0
    else:
        total_fournisseurs_impactes = 0 

    total_fournisseurs_t1 = 30 
    with col6:
        if total_fournisseurs_t1 > 0 and 'identifiant_de_l_etablissement_d_ou_provient_le_produit' in df_filtered.columns:
            taux_ncf = (total_fournisseurs_impactes / total_fournisseurs_t1) * 100
            st.metric("NCF T1 (Simulé)", f"{taux_ncf:.1f}%", help="Taux de Non-Conformité Fournisseur : % des fournisseurs T1 impliqués dans au moins 1 rappel.")
        else:
            st.metric("NCF T1 (Simulé)", "N/A", help="Données d'identification fournisseur manquantes pour le calcul précis.")


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
            df_trend = df_trend[df_trend["date_publication"] >= df_filtered["date_publication"].min()]
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

    # --- KPI DISTRIBUTEUR ---
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("Total Rappels (Filtré)", total_rappels)
    with col2:
        st.metric("Délai Moyen (Marché)", vitesse_reponse)
    with col3:
        st.metric("Coût Logistique Max/Distributeur", f"{COUT_LOGISTIQUE_JOUR_SUPP:,.0f} € / Jour")
    with col4:
        st.metric("% Rappels à Risque Grave", pc_risques_graves_str)
    
    # NOUVEAU KPI 1 : Densité Distributeurs
    with col5:
        if "distributeurs" in df_filtered.columns:
            df_distrib_exploded = explode_column(df_filtered, 'distributeurs')
            distrib_counts = df_distrib_exploded['distributeurs'].value_counts()
            densite_distrib = distrib_counts.mean() if not distrib_counts.empty else 0.0
            st.metric("Densité Moy. Rappel/Distributeur", f"{densite_distrib:.1f}")
        else:
            st.metric("Densité Moy. Rappel/Distributeur", "N/A")
        
    # NOUVEAU KPI 2 : Taux de Couverture du Rappel (TCR) (Simulé)
    with col6:
        taux_couverture_rappel = 85.0
        st.metric("Taux de Couverture du Rappel (Simulé)", f"{taux_couverture_rappel:.1f}%", help="KPI Simulé : % des zones géographiques couvertes par une action de retrait documentée (cible : 95%).")


    st.markdown("### 1. Matrice de Priorisation du Risque Distributeur (Bubble Chart)")
    st.markdown("---") # Séparation visuelle
    
    if "date_debut_commercialisation" in df_filtered.columns and "distributeurs" in df_filtered.columns:
            
        df_reponse = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation", "distributeurs"]).copy()
        
        if df_reponse.empty:
            st.info("⚠️ Les filtres appliqués n'ont généré aucune donnée valide (manque d'information de date de commercialisation et/ou distributeur) pour la Matrice de Risque Distributeur.")
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
                
                # Attribuer les couleurs pour la carte Plotly
                def get_plotly_color(count):
                    if count <= SEUIL_VERT_MAX: return '#2ECC71' # Green
                    elif count <= SEUIL_ORANGE_MAX: return '#F39C12' # Orange
                    else: return '#E74C3C' # Red
                
                geo_counts['Couleur_Hex'] = geo_counts['Nombre_Rappels'].apply(get_plotly_color)
                
                try:
                    # CODE MODIFIÉ POUR L'AGRANDISSEMENT DE LA CARTE
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

    # --- KPI CONFORMITÉ ---
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("Risque Principal", risque_principal)
    with col2:
        st.metric("% Rappels Graves", pc_risques_graves_str)
    with col3:
        st.metric("Délai Moyen Commercialisation", vitesse_reponse)
    
    with col4:
        df_vol = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="Rappels")
        volatilite = df_vol["Rappels"].std() if not df_vol.empty and len(df_vol) > 1 else 0
        st.metric("Volatilité Mensuelle", f"{volatilite:.1f}")
    
    # NOUVEAU KPI 1 : Diversité des Risques
    with col5:
        if not df_risques_exploded.empty:
            diversite_risques = df_risques_exploded['risques_encourus'].nunique()
            st.metric("Diversité des Risques", diversite_risques, help="Nombre de types de risques encourus différents identifiés dans la période (e.g. Bactérie, Physique, Allergène).")
        else:
            st.metric("Diversité des Risques", "N/A")
        
    # NOUVEAU KPI 2 : Risque Moyen Pondéré par Catégorie (RMPC) - Simulation
    with col6:
        if "motif_du_rappel" in df_filtered.columns and "risques_encourus" in df_filtered.columns and not df_filtered.empty:
            df_temp_imr = df_filtered.copy()
            df_temp_imr["is_risque_grave"] = df_temp_imr["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
            df_temp_imr['score_gravite'] = np.where(df_temp_imr['is_risque_grave'], 2, 1)

            motif_graves = df_temp_imr.groupby('motif_du_rappel')['score_gravite'].mean().reset_index()
            top_motifs_graves = motif_graves.sort_values(by='score_gravite', ascending=False).head(1)
            
            rmpc = top_motifs_graves['score_gravite'].mean() * 10 if not top_motifs_graves.empty else 0.0
            st.metric("RMPC (Simulé)", f"{rmpc:.2f}", help="Risque Moyen Pondéré par Catégorie : Gravité moyenne des motifs principaux (échelle de 0 à 20).")
        else:
            st.metric("RMPC (Simulé)", "N/A")


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
