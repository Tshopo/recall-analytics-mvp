import streamlit as st
import pandas as pd
import plotly.express as px
import os 
from datetime import datetime
import numpy as np
from collections import defaultdict

# --- 0. SIMULATION DES COUTS STRATEGIQUES (EN DUR) ---
# Ces valeurs sont des estimations de coûts internes simulées pour la stratégie.
COUT_RAPPEl_GRAVE_UNITAIRE = 50000.0  # Coût estimé d'un rappel impliquant un risque grave (Listeria, Salmonelle)
COUT_RAPPEl_MINEUR_UNITAIRE = 5000.0   # Coût estimé d'un rappel mineur (défaut d'étiquetage simple)
COUT_LOGISTIQUE_JOUR_SUPP = 500.0      # Coût logistique / jour pour chaque distributeur après le délai "normal"
SEUIL_IMR_ALERTE = 10.0                # Seuil à partir duquel un IMR est considéré critique
risques_graves_keywords = "listeriose|salmonellose|e\.coli|blessures|allergene non declare|corps étranger" # Rendu global pour les fonctions

# --- 1. CONFIGURATION ET MISE EN PAGE GLOBALE ---
# ATTENTION: Correction de l'erreur st.set_page_page_config -> st.set_page_config
st.set_page_config(page_title="Recall Analytics (RappelConso) - B2B PRO", layout="wide", initial_sidebar_state="expanded")
st.title("🛡️ Recall Analytics — Dashboard d'Intelligence Marché (B2B PRO) - Vue Stratégie DS")

st.markdown("""
**Prototype de plateforme SaaS B2B** exploitant les données de RappelConso pour l'analyse des risques et le benchmarking concurrentiel. 
**Focus DS :** Intégration des **Coûts Stratégiques Simulé** et des indicateurs prospectifs (IMR, Matrice de Risque Distributeur, DCR).
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

        for col in ["distributeurs", "zone_geographique_de_vente", "risques_encourus", "motif_du_rappel", "categorie_de_produit", "nom_marque_du_produit"]:
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
    
# --- NOUVEL INDICATEUR STRATEGIQUE : Indice de Maturité du Rappel (IMR) ---
def calculate_imr(df_calc):
    if df_calc.empty:
        return 0.0, 0.0

    df_imr = df_calc.copy()
    
    # FIX : S'assurer que 'is_risque_grave' est calculé si la colonne 'risques_encourus' est présente
    if 'risques_encourus' in df_imr.columns:
         df_imr["is_risque_grave"] = df_imr["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
    else:
        return 0.0, 0.0
    
    # 1. Calcul du Score de Gravité pour chaque rappel
    df_imr['score_gravite'] = np.where(df_imr['is_risque_grave'], 2, 1) # Risque grave = poids 2, mineur = poids 1
    
    # 2. Calcul du nombre total de rappels (non uniques, pour la fréquence)
    total_rappels_period = len(df_imr)
    
    # 3. Calcul du coût implicite (pour l'affichage financier)
    df_imr['cout_implicite'] = np.where(df_imr['is_risque_grave'], COUT_RAPPEl_GRAVE_UNITAIRE, COUT_RAPPEl_MINEUR_UNITAIRE)
    
    # 4. Calcul de l'IMR (pondéré)
    total_score = df_imr['score_gravite'].sum()
    
    # Formule simplifiée pour IMR : Score Pondéré / Fréquence
    if total_rappels_period > 0:
        imr = (total_score / total_rappels_period) * 10 
    else:
        imr = 0.0
        
    total_cout = df_imr['cout_implicite'].sum()

    return imr, total_cout

# Calcul de l'IMR pour la marque filtrée
imr_marque, cout_marque = calculate_imr(df_filtered)

# Calcul du % Rappels graves (utilisation de la même logique sans appeler calculate_imr)
if total_rappels > 0:
    count_graves = df_filtered["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False).sum()
    pc_risques_graves = (count_graves / total_rappels * 100)
    pc_risques_graves_str = f"{pc_risques_graves:.1f}%"
else:
    pc_risques_graves_str = "N/A"

# Calcul de l'IMR pour le marché (pour la comparaison)
df_marche_comp = df[df["date_publication"] >= df_filtered["date_publication"].min()].copy()
imr_marche_comp, _ = calculate_imr(df_marche_comp)


# --- 5. STRUCTURE DU TABLEAU DE BORD PAR ACTEUR (TABS) ---

tab1, tab2, tab3 = st.tabs(["🏭 Fabricants & Marques", "🛒 Distributeurs & Retailers", "🔬 Risque & Conformité"])


# ----------------------------------------------------------------------
# TAB 1: FABRICANTS & MARQUES (BENCHMARKING IMR)
# ----------------------------------------------------------------------
with tab1:
    st.header("🎯 Intelligence Concurrentielle & Maîtrise du Risque Fournisseur")

    # --- KPI FABRICANT ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Rappels (Périmètre)", total_rappels)
    col2.metric("Risque Principal", risque_principal)
    col3.metric("IMR de la Marque (Simulé)", f"{imr_marque:.2f}", help="Indice de Maturité du Rappel : Score de gravité (2x Grave + 1x Mineur) pondéré. Seuil d'alerte : 10.0.")
    col4.metric("Coût Implicite (Simulé)", f"{cout_marque:,.0f} €", help="Estimation du coût financier total des rappels (simulé en dur).")

    st.markdown("### Analyse de Positionnement et Causes Racines")
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
            
            # Calcul IMR mensuel pour la marque et le marché
            df_trend = df.copy()
            df_trend = df_trend[df_trend["date_publication"] >= df_filtered["date_publication"].min()]
            df_trend["Mois"] = df_trend["date_publication"].dt.to_period("M")

            def compute_imr_per_month(df_input):
                # FIX : S'assurer que 'is_risque_grave' est calculé dans cette fonction
                if 'risques_encourus' in df_input.columns:
                    df_input['is_risque_grave'] = df_input["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
                else:
                    return pd.DataFrame()
                    
                df_input['score_gravite'] = np.where(df_input['is_risque_grave'], 2, 1)
                
                imr_monthly = df_input.groupby('Mois').agg(
                    Total_Score=('score_gravite', 'sum'),
                    Total_Rappels=('score_gravite', 'count')
                ).reset_index()
                
                # Éviter la division par zéro
                imr_monthly['IMR'] = np.where(imr_monthly['Total_Rappels'] > 0, 
                                              (imr_monthly['Total_Score'] / imr_monthly['Total_Rappels']) * 10, 
                                              0.0)
                imr_monthly['Mois'] = imr_monthly['Mois'].dt.to_timestamp()
                return imr_monthly[['Mois', 'IMR']]

            df_imr_marque = compute_imr_per_month(df_trend[df_trend["nom_marque_du_produit"] == marque])
            df_imr_marche = compute_imr_per_month(df_trend)
            df_imr_marche = df_imr_marche.rename(columns={'IMR': 'IMR_Marché'})
            
            df_comp = pd.merge(df_imr_marque.rename(columns={'IMR': f'IMR_{marque.title()}'}), df_imr_marche, on='Mois', how='outer').fillna(0)
            
            fig_trend = px.line(df_comp, x="Mois", y=[f"IMR_{marque.title()}", "IMR_Marché"], 
                                title=f"Évolution Mensuelle de l'IMR : {marque.title()} vs. Marché (Seuil Alerte {SEUIL_IMR_ALERTE})",
                                labels={"value": "IMR (Score Pondéré)", "Mois": "Mois"},
                                color_discrete_map={f'IMR_{marque.title()}': '#2C3E50', 'IMR_Marché': '#BDC3C7'},
                                line_shape='spline', markers=True)
            
            # Ajout du seuil d'alerte critique
            fig_trend.add_hline(y=SEUIL_IMR_ALERTE, line_dash="dot", line_color="red", 
                                annotation_text="Seuil Alerte IMR", 
                                annotation_position="top right")

            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Sélectionnez une marque dans la sidebar pour afficher l'IMR et la tendance.")

    st.markdown("---")
    st.subheader("3. Corrélation : Matrice des Motifs vs. Risques")
    
    if "risques_encourus" in df_filtered.columns and "motif_du_rappel" in df_filtered.columns:
        df_corr = df_filtered.copy()
        df_corr["Motif_court"] = df_corr["motif_du_rappel"].str.split(r'[;.,]').str[0].str.strip()
        
        df_exploded_motif_risque = df_corr.assign(risques_encourus=df_corr['risques_encourus'].str.split(';')).explode('risques_encourus')
        df_exploded_motif_risque['risques_encourus'] = df_exploded_motif_risque['risques_encourus'].str.strip()
        
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


# ----------------------------------------------------------------------
# TAB 2: DISTRIBUTEURS & RETAILERS (MATRICE DE RISQUE LOGISTIQUE)
# ----------------------------------------------------------------------
with tab2:
    st.header("🛒 Analyse du Canal de Distribution & Risque Fournisseur")

    # --- KPI DISTRIBUTEUR ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Rappels (Filtré)", total_rappels)
    col2.metric("Délai Moyen (Marché)", vitesse_reponse)
    col3.metric("Coût Logistique Max/Distributeur (Simulé)", f"{COUT_LOGISTIQUE_JOUR_SUPP:,.0f} € / Jour", help="Coût logistique journalier estimé pour la gestion des stocks à retirer.")
    col4.metric("% Rappels à Risque Grave", pc_risques_graves_str)

    st.markdown("### Matrice de Priorisation du Risque Distributeur (Bubble Chart)")
    
    if "date_debut_commercialisation" in df_filtered.columns and "distributeurs" in df_filtered.columns:
            
        # 1. Joindre le distributeur aux données de dates
        df_reponse = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation", "distributeurs"]).copy()
        df_reponse = df_reponse.assign(distributeurs=df_reponse['distributeurs'].str.split(';')).explode('distributeurs')
        df_reponse['distributeurs'] = df_reponse['distributeurs'].str.strip()
        df_reponse = df_reponse[df_reponse['distributeurs'] != '']
        
        # 2. Calculer le Délai et la Gravité
        df_reponse["Délai_Jours"] = (df_reponse["date_publication"] - df_reponse["date_debut_commercialisation"]).dt.days
        df_reponse = df_reponse[df_reponse["Délai_Jours"] >= 0]
        # FIX : Calculer is_risque_grave ici pour le score
        if 'risques_encourus' in df_reponse.columns:
            df_reponse['is_risque_grave'] = df_reponse["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)
            df_reponse['Score_Gravite'] = np.where(df_reponse['is_risque_grave'], 2, 1) # 2x plus important si Grave
        else:
            df_reponse['Score_Gravite'] = 1
        
        # 3. Agrégation par Distributeur
        avg_distrib = df_reponse.groupby("distributeurs").agg(
            Délai_Moyen_Jours=('Délai_Jours', 'mean'),
            Nb_Rappels=('Délai_Jours', 'count'),
            Gravite_Moyenne=('Score_Gravite', 'mean')
        ).reset_index()
        
        # 4. Calcul du Coût d'Exposition au Risque (Taille de la bulle)
        # Simulation: Délai * (Nb_Rappels * Coût Logistique Jour * Gravité)
        avg_distrib['Coût_Risque_Simulé'] = avg_distrib['Délai_Moyen_Jours'] * avg_distrib['Nb_Rappels'] * avg_distrib['Gravite_Moyenne'] * COUT_LOGISTIQUE_JOUR_SUPP / 1000 # Divisé par 1000 pour taille lisible
        
        # 5. Création de la Matrice (Bubble Chart)
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
            
            # Ajout des lignes de quadrants (stratégiques)
            if not avg_distrib.empty:
                fig_bubble.add_vline(x=avg_distrib['Délai_Moyen_Jours'].median(), line_dash="dash", line_color="#34495E")
                fig_bubble.add_hline(y=avg_distrib['Nb_Rappels'].median(), line_dash="dash", line_color="#34495E")

            fig_bubble.update_layout(xaxis_range=[0, avg_distrib['Délai_Moyen_Jours'].max() * 1.1])
            st.plotly_chart(fig_bubble, use_container_width=True)
        else:
            st.info("Données insuffisantes pour la matrice de risque distributeur.")
    else:
        st.info("Colonnes de date de commercialisation et/ou distributeurs manquantes dans le fichier CSV.")


# ----------------------------------------------------------------------
# TAB 3: RISQUE & CONFORMITÉ (DÉRIVE DES CAUSES RACINES)
# ----------------------------------------------------------------------
with tab3:
    st.header("🔬 Évaluation de la Gravité et Tendance du Risque (Assurance & Conseil)")

    # --- KPI CONFORMITÉ ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Risque Principal (Focus)", risque_principal)
    col2.metric("% Rappels Graves", pc_risques_graves_str)
    col3.metric("Délai Moyen Commercialisation", vitesse_reponse, help="Durée moyenne (en jours) de présence du produit défectueux sur le marché avant le rappel. Un nombre faible = meilleure réactivité globale du marché.")
    
    # Indicateur de Volatilité du Marché
    df_vol = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="Rappels")
    volatilite = df_vol["Rappels"].std() if not df_vol.empty else 0
    col4.metric("Volatilité Mensuelle (Écart-type)", f"{volatilite:.1f}", help="Écart-type du nombre de rappels par mois. Un nombre élevé signifie un marché imprévisible.")


    st.markdown("### 2. Tendance : Dérive des Causes Racines (DCR) - Taux d'Émergence des Motifs")
    
    if "date_publication" in df_filtered.columns and "motif_du_rappel" in df_filtered.columns:
        
        # 1. Préparer les données
        df_trend = df_filtered.copy()
        df_trend["Mois"] = df_trend["date_publication"].dt.to_period("M")
        
        df_motifs = explode_column(df_trend, "motif_du_rappel")
        # S'assurer que les indices correspondent après l'explosion
        df_motifs = df_motifs.reset_index().rename(columns={'index': 'original_index'})
        df_motifs_merged = pd.merge(df_motifs, df_trend[['Mois']].reset_index().rename(columns={'index': 'original_index'}), on='original_index', how='left')
        
        # 2. Calcul du classement mensuel
        motif_counts = df_motifs_merged.groupby(['Mois', 'motif_du_rappel']).size().reset_index(name='Rappels')
        
        # Calcul du Rang (Rank) par mois
        motif_counts['Rang'] = motif_counts.groupby('Mois')['Rappels'].rank(method='first', ascending=False)
        
        # Filtrer le top 5 des motifs globaux pour lisibilité
        top_motifs_global = motif_counts['motif_du_rappel'].value_counts().head(5).index
        df_rank = motif_counts[motif_counts['motif_du_rappel'].isin(top_motifs_global)].copy()
        
        df_rank['Mois'] = df_rank['Mois'].dt.to_timestamp()
        
        if not df_rank.empty:
            # 3. Création du Bump Chart
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
        st.info("Colonnes manquantes pour l'analyse des motifs.")

    st.markdown("---")
    st.subheader("3. Corrélation : Risque vs. Catégorie (Analyse de Portefeuille)")
    
    if not df_risques_exploded.empty and "categorie_de_produit" in df_filtered.columns:
        
        df_temp_risques = df_filtered.assign(risques_encourus=df_filtered['risques_encourus'].str.split(';')).explode('risques_encourus')
        df_temp_risques['risques_encourus'] = df_temp_risques['risques_encourus'].str.strip()

        risque_cat_counts = df_temp_risques.groupby(['categorie_de_produit', 'risques_encourus']).size().reset_index(name='Nombre')
        risque_cat_counts = risque_cat_counts[risque_cat_counts['Nombre'] > 0]
        
        top_risques_list = risque_cat_counts['risques_encourus'].value_counts().head(5).index
        risque_cat_filtered = risque_cat_counts[risque_cat_counts['risques_encourus'].isin(top_risques_list)]

        if not risque_cat_filtered.empty:
            fig_bar = px.bar(risque_cat_filtered, x="categorie_de_produit", y="Nombre", color="risques_encourus", 
                             title="Distribution des 5 principaux risques par Catégorie de Produit",
                             labels={"categorie_de_produit": "Catégorie", "Nombre": "Nombre de Rappels"},
                             color_discrete_sequence=px.colors.qualitative.G10)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
             st.info("Pas assez de données pour générer le croisement Risque/Catégorie.")
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
