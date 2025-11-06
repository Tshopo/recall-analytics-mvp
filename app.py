import streamlit as st
import pandas as pd
import plotly.express as px
import os 
from datetime import datetime
import numpy as np

# --- 1. CONFIGURATION ET MISE EN PAGE GLOBALE ---
# Utilisation d'une palette de couleurs cohérente et un layout large
st.set_page_config(page_title="Recall Analytics (RappelConso) - B2B PRO", layout="wide", initial_sidebar_state="expanded")
st.title("🛡️ Recall Analytics — Dashboard d'Intelligence Marché (B2B PRO)")

st.markdown("""
**Prototype de plateforme SaaS B2B** exploitant les données de RappelConso pour l'analyse des risques et le benchmarking concurrentiel. 
**Objectif :** Fournir des insights actionnables sur la fréquence, la gravité et l'exposition géographique des rappels.
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
        # Tente avec le point-virgule (FR), puis la virgule
        try:
            df = pd.read_csv(file_path, sep=";", encoding='utf-8')
            if df.shape[1] <= 1:
                df = pd.read_csv(file_path, sep=",", encoding='utf-8')
        except Exception:
            df = pd.read_csv(file_path, sep=",", encoding='utf-8')

        if df.empty or df.shape[1] <= 1:
            raise ValueError("Le fichier ne contient pas de données.")
            
        # --- STANDARDISATION DES NOMS DE COLONNES (POUR LA STABILITÉ) ---
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
            
        # 1. Conversion de la date
        if "date_publication" in df.columns:
            df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce", utc=True)
            df = df.sort_values(by="date_publication", ascending=False) 
        
        if "date_debut_commercialisation" in df.columns:
            df["date_debut_commercialisation"] = pd.to_datetime(df["date_debut_commercialisation"], errors="coerce", utc=True)

        # 2. Nettoyage des colonnes multi-valeurs
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

# % de Rappels graves
risques_graves_keywords = "listeriose|salmonellose|e\.coli|blessures|allergene non declare|corps étranger"
df_risques_grave = explode_column(df_filtered, "risques_encourus")
pc_risques_graves = 0.0
if not df_risques_grave.empty and total_rappels > 0:
    count_graves = df_risques_grave[df_risques_grave["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)].shape[0]
    pc_risques_graves = (count_graves / total_rappels * 100)
    pc_risques_graves_str = f"{pc_risques_graves:.1f}%"
else:
    pc_risques_graves_str = "N/A"

# Vitesse de Réponse Moyenne (Proxy) - Pour Tab 3
vitesse_reponse = "N/A"
if "date_debut_commercialisation" in df_filtered.columns and not df_filtered["date_debut_commercialisation"].isnull().all():
    df_temp_dates = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation"]).copy()
    if not df_temp_dates.empty:
        df_temp_dates["duree_commercialisation"] = (df_temp_dates["date_publication"] - df_temp_dates["date_debut_commercialisation"]).dt.days
        df_temp_dates = df_temp_dates[df_temp_dates["duree_commercialisation"] >= 0]
        if not df_temp_dates.empty:
            avg_days = df_temp_dates["duree_commercialisation"].mean()
            vitesse_reponse = f"{avg_days:.1f} jours"
    
# Concentration du Risque Fournisseur - Pour Tab 2
concentration_risque = "N/A"
if "nom_marque_du_produit" in df_filtered.columns and total_rappels > 0:
    top_5_marques = df_filtered["nom_marque_du_produit"].value_counts().nlargest(5)
    if not top_5_marques.empty:
        concentration = top_5_marques.sum() / total_rappels * 100
        concentration_risque = f"{concentration:.1f}%"


# --- 5. STRUCTURE DU TABLEAU DE BORD PAR ACTEUR (TABS) ---

tab1, tab2, tab3 = st.tabs(["🏭 Fabricants & Marques", "🛒 Distributeurs & Retailers", "🔬 Risque & Conformité"])


# ----------------------------------------------------------------------
# TAB 1: FABRICANTS & MARQUES (BENCHMARKING)
# ----------------------------------------------------------------------
with tab1:
    st.header("🎯 Intelligence Concurrentielle & Maîtrise du Risque Fournisseur")

    # --- KPI FABRICANT ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Rappels (Périmètre)", total_rappels)
    col2.metric("Marques Impactées", df_filtered["nom_marque_du_produit"].nunique() if "nom_marque_du_produit" in df.columns else 0)
    col3.metric("Risque Principal", risque_principal)
    col4.metric("% Rappels à Risque Grave", pc_risques_graves_str, help="Pourcentage des rappels liés à des risques sérieux (Listeria, Salmonelle, Allergènes non déclarés).")


    # --- GRAPHIQUES FABRICANT ---
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
        st.subheader("2. Tendance : SoR de la Marque vs. Marché")
        if marque != "Toutes" and "date_publication" in df_filtered.columns:
            df_trend = df.copy()
            df_trend = df_trend[df_trend["date_publication"] >= df_filtered["date_publication"].min()]
            
            # Agrégation mensuelle
            df_month = df_trend.groupby(df_trend["date_publication"].dt.to_period("M")).size().reset_index(name="Total_Marché")
            df_marque_month = df_trend[df_trend["nom_marque_du_produit"] == marque].groupby(df_trend["date_publication"].dt.to_period("M")).size().reset_index(name=marque.title())

            df_comp = pd.merge(df_month, df_marque_month, on="date_publication", how="outer").fillna(0)
            df_comp["date_publication"] = df_comp["date_publication"].dt.to_timestamp()
            
            # Calcul du SoR
            df_comp[f"SoR_{marque.title()}"] = (df_comp[marque.title()] / df_comp["Total_Marché"]) * 100
            
            fig_trend = px.line(df_comp, x="date_publication", y=[f"SoR_{marque.title()}"], 
                                title=f"Évolution Mensuelle du Share of Recall (SoR) pour {marque.title()}",
                                labels={"value": "SoR (%)", "date_publication": "Mois"},
                                color_discrete_sequence=['#FF4B4B'])
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Sélectionnez une marque dans la sidebar pour afficher la tendance SoR.")

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
# TAB 2: DISTRIBUTEURS & RETAILERS (CANAL)
# ----------------------------------------------------------------------
with tab2:
    st.header("🛒 Analyse du Canal de Distribution & Risque Fournisseur")

    # --- KPI DISTRIBUTEUR ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Rappels (Filtré)", total_rappels)
    col2.metric("Nombre de Marques Impactées", df_filtered["nom_marque_du_produit"].nunique() if "nom_marque_du_produit" in df.columns else 0)
    col3.metric("Zone de Vente la Plus Sensible", explode_column(df_filtered, "zone_geographique_de_vente")["zone_geographique_de_vente"].mode()[0].title() if not explode_column(df_filtered, "zone_geographique_de_vente").empty else "N/A")
    col4.metric("Concentration Risque Fournisseur (Top 5)", concentration_risque, help="Pourcentage des rappels provenant des 5 marques les plus problématiques.")

    # --- GRAPHIQUES DISTRIBUTEUR ---
    st.markdown("### Évaluation du Risque Fournisseur et Exposition")
    col_gauche, col_droite = st.columns(2)

    with col_gauche:
        st.subheader("1. Risque Fournisseur : Top 10 Marques par Catégorie")
        col_name = "nom_marque_du_produit"
        if col_name in df_filtered.columns:
            brand_category_counts = df_filtered.groupby(["nom_marque_du_produit", "categorie_de_produit"]).size().reset_index(name='Nombre_de_Rappels')
            top_10_brands = brand_category_counts.sort_values(by="Nombre_de_Rappels", ascending=False).head(10)
            
            fig_brands = px.bar(top_10_brands, x="Nombre_de_Rappels", y="nom_marque_du_produit", orientation='h', 
                                title="Top 10 Marques associées aux rappels (dans la catégorie sélectionnée)",
                                color='categorie_de_produit', color_discrete_sequence=px.colors.qualitative.Bold)
            fig_brands.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="Marque")
            st.plotly_chart(fig_brands, use_container_width=True)
        else:
            st.info("Aucune donnée de marque/fournisseur exploitable.")

    with col_droite:
        st.subheader("2. Analyse de la Réactivité : Délai Moyen de Commercialisation avant Rappel")
        
        if "date_debut_commercialisation" in df_filtered.columns and "distributeurs" in df_filtered.columns:
            
            # 1. Joindre le distributeur aux données de dates
            df_reponse = df_filtered.dropna(subset=["date_publication", "date_debut_commercialisation", "distributeurs"]).copy()
            df_reponse = df_reponse.assign(distributeurs=df_reponse['distributeurs'].str.split(';')).explode('distributeurs')
            df_reponse['distributeurs'] = df_reponse['distributeurs'].str.strip()
            df_reponse = df_reponse[df_reponse['distributeurs'] != '']
            
            # 2. Calculer le délai et filtrer les erreurs de saisie
            df_reponse["Délai_Jours"] = (df_reponse["date_publication"] - df_reponse["date_debut_commercialisation"]).dt.days
            df_reponse = df_reponse[df_reponse["Délai_Jours"] >= 0]
            
            # 3. Calculer la moyenne par Distributeur
            avg_delay_distrib = df_reponse.groupby("distributeurs")["Délai_Jours"].mean().reset_index(name="Délai_Moyen_Jours")
            
            # 4. Afficher le top 10 des distributeurs avec le DÉLAI le plus LONG (le moins réactif)
            top_10_distrib = avg_delay_distrib.sort_values(by="Délai_Moyen_Jours", ascending=False).head(10)
            
            if not top_10_distrib.empty:
                # --- AMÉLIORATION DE LA VISUALISATION ---
                fig_delay = px.bar(top_10_distrib, x="Délai_Moyen_Jours", y="distributeurs", orientation='h',
                                   title="Top 10 : Distributeurs avec le Délai de Rappel le plus Long (Risque Élevé)",
                                   color='Délai_Moyen_Jours', # La couleur reflète l'intensité du délai
                                   color_continuous_scale=px.colors.sequential.YlOrRd, # Échelle de couleur Risque (Jaune -> Rouge)
                                   text_auto='.1f') # Afficher les valeurs numériques (arrondies) sur les barres
                
                fig_delay.update_layout(
                    yaxis={'categoryorder':'total ascending', 'tickfont': {'size': 12}}, # Améliorer la lisibilité des labels Y
                    xaxis_title="Délai Moyen (Jours) de Présence sur le Marché",
                    yaxis_title="Distributeur",
                    coloraxis_colorbar=dict(title="Jours")
                )
                
                st.plotly_chart(fig_delay, use_container_width=True)
            else:
                st.info("Données de réactivité incomplètes ou non disponibles pour la période filtrée.")
        else:
            st.info("Colonnes de date de commercialisation et/ou distributeurs manquantes dans le fichier CSV.")


# ----------------------------------------------------------------------
# TAB 3: RISQUE & CONFORMITÉ (SERVICES PRO)
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
    col4.metric("Volatilité Mensuelle (
