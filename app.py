import streamlit as st
import pandas as pd
import plotly.express as px
import os 
from datetime import datetime
import numpy as np

# --- 1. CONFIGURATION ET MISE EN PAGE GLOBALE ---
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
    """Charge les données à partir d'un fichier CSV local, standardise les noms de colonnes et gère les séparateurs."""
    
    if not os.path.exists(file_path):
        st.error(f"❌ Fichier non trouvé : '{file_path}'. Veuillez vous assurer que le fichier CSV téléchargé est placé dans le même dossier que l'application et porte ce nom.")
        return pd.DataFrame()
    
    df = pd.DataFrame()
    
    try:
        # Tente avec le point-virgule (le plus probable pour les exports FR), puis la virgule
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
        }
        
        rename_dict = {old_name: new_name for old_name, new_name in column_mapping.items() if old_name in df.columns and old_name != new_name}
        df = df.rename(columns=rename_dict)

        required_cols = ["categorie_de_produit", "nom_marque_du_produit", "motif_du_rappel", "distributeurs"]
        missing_cols = [c for c in required_cols if c not in df.columns]

        if missing_cols:
            st.error(f"⚠️ Alerte Colonnes : Le script ne trouve pas les colonnes nécessaires : **{', '.join(missing_cols)}**.")
            st.stop()
            
        # 1. Conversion de la date
        if "date_publication" in df.columns:
            df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce", utc=True)
            df = df.sort_values(by="date_publication", ascending=False) 

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


# --- 3. CHARGEMENT ET FILTRES GLOBALES ---
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

# Calcul du risque principal
df_risques_exploded = explode_column(df_filtered, "risques_encourus")
risque_principal = "N/A (Données manquantes)"
if not df_risques_exploded.empty and "risques_encourus" in df_risques_exploded.columns:
    risque_counts = df_risques_exploded["risques_encourus"].value_counts()
    if not risque_counts.empty:
        risque_major = next(iter(risque_counts.index), None)
        if risque_major:
            risque_principal = risque_major.title()

# Calcul du Taux de Risque Microbiologique
taux_microbien = 0.0
if "motif_du_rappel" in df_filtered.columns and total_rappels > 0:
    microbien_count = df_filtered[df_filtered["motif_du_rappel"].str.contains("microbiologique|salmonelle|listeria|ecoli", case=False, na=False)].shape[0]
    taux_microbien = (microbien_count / total_rappels * 100)
    taux_microbien_str = f"{taux_microbien:.1f}%"
else:
    taux_microbien_str = "N/A"

# Calcul du % de Rappels graves (Basé sur le mot-clé 'listeriose', 'salmonellose', 'e.coli', 'blessures')
risques_graves_keywords = "listeriose|salmonellose|e\.coli|blessures|allergene non declare"
df_risques_grave = explode_column(df_filtered, "risques_encourus")
pc_risques_graves = 0.0
if not df_risques_grave.empty and total_rappels > 0:
    count_graves = df_risques_grave[df_risques_grave["risques_encourus"].str.contains(risques_graves_keywords, case=False, na=False)].shape[0]
    pc_risques_graves = (count_graves / total_rappels * 100)
    pc_risques_graves_str = f"{pc_risques_graves:.1f}%"
else:
    pc_risques_graves_str = "N/A"


# --- 5. STRUCTURE DU TABLEAU DE BORD PAR ACTEUR (TABS) ---

tab1, tab2, tab3 = st.tabs(["🏭 Fabricants & Marques (Benchmarking)", "🛒 Distributeurs & Retailers (Canal)", "🔬 Risque & Conformité (Services Pro)"])


# ----------------------------------------------------------------------
# TAB 1: FABRICANTS & MARQUES
# ----------------------------------------------------------------------
with tab1:
    st.header("🎯 Intelligence Concurrentielle & Maîtrise du Risque Fournisseur")
    st.markdown("Analysez votre positionnement (Share of Recall) face à la concurrence et identifiez les causes racines (Motifs).")

    # --- KPI FABRICANT ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Rappels (Périmètre Filtré)", total_rappels)
    col2.metric("Marques Impactées", df_filtered["nom_marque_du_produit"].nunique() if "nom_marque_du_produit" in df.columns else 0)
    
    # Indicateur avancé: Diversité des Motifs (Mesure de la robustesse globale)
    motifs_uniques = df_filtered["motif_du_rappel"].nunique() if "motif_du_rappel" in df.columns else 0
    col3.metric("Diversité des Motifs de Rappel", motifs_uniques, help="Un nombre élevé suggère une dispersion des problèmes (moins de maîtrise qualité).")


    # --- GRAPHIQUES FABRICANT ---
    col_gauche, col_droite = st.columns(2)

    with col_gauche:
        st.subheader("1. Benchmark : Part de Rappel par Marque (SoR)")
        if "nom_marque_du_produit" in df_filtered.columns and total_rappels > 0:
            top_marques = df_filtered["nom_marque_du_produit"].value_counts(normalize=True).mul(100).reset_index().rename(columns={
                "nom_marque_du_produit": "Marque", 
                "proportion": "Part_de_Rappel_pourcent"
            })
            top_marques = top_marques.head(10)
            fig_sor = px.bar(top_marques, y="Marque", x="Part_de_Rappel_pourcent", orientation='h', title="Top 10 : Contribution (%) aux rappels du marché (catégorie et période sélectionnées)",
                             color='Part_de_Rappel_pourcent', color_continuous_scale=px.colors.sequential.Plotly3)
            fig_sor.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_sor, use_container_width=True)
        else:
            st.info("Aucune donnée pour le benchmarking des marques.")

    with col_droite:
        st.subheader("2. Causes Racines : Distribution des Motifs de Rappel")
        if "motif_du_rappel" in df_filtered.columns and total_rappels > 0:
            top_motifs = df_filtered["motif_du_rappel"].value_counts().reset_index().rename(columns={
                "motif_du_rappel": "Motif", 
                "count": "Nombre_de_Rappels"
            }).head(10)
            fig_motifs = px.pie(top_motifs, values="Nombre_de_Rappels", names="Motif", title="Fréquence des causes de défaillance")
            fig_motifs.update_traces(textinfo='percent+label')
            st.plotly_chart(fig_motifs, use_container_width=True)
        else:
            st.info("Aucun motif identifiable dans les données filtrées.")


# ----------------------------------------------------------------------
# TAB 2: DISTRIBUTEURS & RETAILERS
# ----------------------------------------------------------------------
with tab2:
    st.header("🛒 Analyse du Canal de Distribution & Risque Fournisseur")
    st.markdown("Évaluez l'exposition de votre réseau géographique et identifiez les marques/fournisseurs les plus problématiques dans votre canal.")

    # --- KPI DISTRIBUTEUR ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Rappels (Filtré)", total_rappels)
    
    # Nombre de Marques (Fournisseurs) Impactées
    marques_impactees = df_filtered["nom_marque_du_produit"].nunique() if "nom_marque_du_produit" in df.columns else 0
    col2.metric("Nombre de Marques Impactées", marques_impactees, help="Le nombre de marques distinctes impliquées dans les rappels sur le périmètre filtré.")
    
    # Risque par zone géographique
    df_zones = explode_column(df_filtered, "zone_geographique_de_vente")
    zone_sensible = "N/A"
    if not df_zones.empty:
        zone_sensible = df_zones["zone_geographique_de_vente"].value_counts().index[0].title()
    col3.metric("Zone de Vente la Plus Sensible", zone_sensible)


    # --- GRAPHIQUES DISTRIBUTEUR ---
    col_gauche, col_droite = st.columns(2)

    with col_gauche:
        st.subheader("1. Exposition Géographique : Top 10 des Zones de Vente")
        col_name = "zone_geographique_de_vente"
        if col_name in df_filtered.columns:
            df_exposed = explode_column(df_filtered, col_name)
            if not df_exposed.empty and col_name in df_exposed.columns:
                exposure_counts = df_exposed[col_name].value_counts().reset_index().rename(columns={
                    col_name: "Zone", 
                    "count": "Nombre_de_Rappels"
                }).head(10)
                
                fig_exposure = px.bar(exposure_counts, y="Zone", x="Nombre_de_Rappels", orientation='h', title="Fréquence de rappels par zone géographique de vente",
                                       color='Nombre_de_Rappels', color_continuous_scale=px.colors.sequential.Viridis)
                fig_exposure.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_exposure, use_container_width=True)
            else:
                st.info("Aucune donnée de zone géographique exploitable.")
        else:
            st.info("Colonne de zone géographique manquante.")

    with col_droite:
        st.subheader("2. Risque Fournisseur : Top 10 des Marques (Fournisseurs)")
        col_name = "nom_marque_du_produit"
        if col_name in df_filtered.columns:
            brand_counts = df_filtered[col_name].value_counts().reset_index().rename(columns={
                col_name: "Marque", 
                "count": "Nombre_de_Rappels"
            }).head(10)
            
            fig_brands = px.bar(brand_counts, x="Marque", y="Nombre_de_Rappels", title="Top 10 Marques associées aux rappels",
                                 color='Nombre_de_Rappels', color_continuous_scale=px.colors.sequential.Plasma)
            st.plotly_chart(fig_brands, use_container_width=True)
        else:
            st.info("Aucune donnée de marque/fournisseur exploitable.")


# ----------------------------------------------------------------------
# TAB 3: RISQUE & CONFORMITÉ (SERVICES PRO)
# ----------------------------------------------------------------------
with tab3:
    st.header("🔬 Évaluation de la Gravité et Tendance du Risque (Assurance & Conseil)")
    st.markdown("Évaluez l'exposition légale et assurantielle du secteur et suivez l'évolution des risques majeurs.")

    # --- KPI CONFORMITÉ ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Risque Principal (Focus)", risque_principal)
    col2.metric("% Rappels Microbiologiques", taux_microbien_str, help="Indicateur de la défaillance des plans HACCP et des contrôles sanitaires.")
    col3.metric("% Rappels à Risque Grave", pc_risques_graves_str, help="Pourcentage des rappels liés à des risques sérieux (Listeria, Salmonelle, Allergènes non déclarés).")

    
    # --- GRAPHIQUES CONFORMITÉ ---
    col_gauche, col_droite = st.columns(2)

    with col_gauche:
        st.subheader("1. Gravité : Distribution des Risques Encourus")
        if not df_risques_exploded.empty and "risques_encourus" in df_risques_exploded.columns:
            risque_counts_top = df_risques_exploded["risques_encourus"].value_counts().reset_index().rename(columns={
                "risques_encourus": "Risque", 
                "count": "Nombre_de_Rappels"
            }).head(10)
            fig_risques = px.bar(risque_counts_top, y="Risque", x="Nombre_de_Rappels", orientation='h', title="Fréquence des principaux dangers (Listeria, Corps étrangers, Allergènes...)",
                                 color='Nombre_de_Rappels', color_continuous_scale=px.colors.sequential.Reds)
            fig_risques.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_risques, use_container_width=True)
        else:
             st.info("Aucun risque identifiable dans les données filtrées.")

    with col_droite:
        st.subheader("2. Tendance : Évolution Mensuelle du Volume de Rappels")
        if "date_publication" in df_filtered.columns:
            df_month = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="rappels")
            if not df_month.empty:
                df_month["date_publication"] = df_month["date_publication"].dt.to_timestamp()
                fig_trend = px.line(df_month, x="date_publication", y="rappels", title="Volume de rappels par mois de publication",
                                    line_shape='spline', markers=True, color_discrete_sequence=['#0083B8'])
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("Aucune donnée pour générer la tendance temporelle.")
        else:
            st.info("Données de publication manquantes.")

st.markdown("---")

# --- 6. TABLEAU DE DONNÉES DÉTAILLÉ (NETTOYAGE DU MVP) ---
with st.expander("🔍 Voir le Registre Détaillé des Rappels (Filtré)"):
    display_cols = [c for c in ["reference_fiche", "date_publication", "categorie_de_produit", "nom_marque_du_produit", "motif_du_rappel", "risques_encourus", "distributeurs", "zone_geographique_de_vente", "liens_vers_la_fiche_rappel"] if c in df_filtered.columns]
    
    st.dataframe(df_filtered[display_cols].sort_values(by="date_publication", ascending=False).reset_index(drop=True), use_container_width=True)

    csv = df_filtered[display_cols].to_csv(index=False).encode('utf-8')
    st.download_button(label="💾 Télécharger les Données Filtrées (CSV)", data=csv, file_name="recall_analytics_export_filtered.csv", mime="text/csv")


st.caption("Prototype Recall Analytics — Données publiques (c) RappelConso.gouv.fr / Ministère de l'Économie")
