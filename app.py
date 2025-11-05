import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Recall Analytics (RappelConso) - B2B MVP", layout="wide")
st.title("🚀 Recall Analytics — Dashboard d'Intelligence Marché (MVP B2B)")

st.markdown("""
**Prototype de plateforme SaaS B2B** exploitant les données de RappelConso pour l'analyse des risques et le benchmarking concurrentiel. 
**Objectif :** Fournir des insights actionnables sur la fréquence, la gravité et l'exposition géographique des rappels.
""")

# --- FONCTION DE CHARGEMENT DE DONNÉES (Robuste contre l'API 400) ---
@st.cache_data(ttl=3600)
def load_data(limit=10000):
    """Charge les données de RappelConso avec un mécanisme de secours en cas de 400."""
    base_url = (
        f"https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
        f"rappelconso-v2-gtin-espaces/records"
    )
    
    params = {"limit": limit}
    r = None
    try:
        r = requests.get(base_url, params=params, timeout=30)
        
        if r.status_code == 400:
            st.warning(f"La requête avec limit={limit} a échoué (400). Tentative avec limit=100 pour vérifier la disponibilité.")
            params_safe = {"limit": 100}
            r = requests.get(base_url, params=params_safe, timeout=30)
            
        r.raise_for_status()
        
        data = r.json()
        records = data.get("results", [])
        if not records:
            st.warning("⚠️ Aucun enregistrement trouvé dans l'API RappelConso.")
            return pd.DataFrame()

        df = pd.json_normalize(records)

        # Mapping des noms de champs réels de l'API vers les noms Streamlit/B2B
        column_mapping = {
            "numero_fiche": "reference_fiche",
            "libelle": "nom_du_produit",
            "marque_produit": "nom_marque_du_produit",
            "categorie_produit": "categorie_de_produit",
            "motif_rappel": "motif_du_rappel",
            "risques_encourus": "risques_encourus",
            "lien_vers_la_fiche_rappel": "liens_vers_la_fiche_rappel",
            "date_publication": "date_publication",
            "distributeurs": "distributeurs",
            "zone_geographique_de_vente": "zone_geographique_de_vente"
        }
        
        df = df.rename(columns=column_mapping)

        cols_finales = list(column_mapping.values())
        df = df[[c for c in cols_finales if c in df.columns]]

        if "date_publication" in df.columns:
            df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce", utc=True)
            df = df.sort_values(by="date_publication", ascending=False) 

        # Nettoyage des chaînes de caractères dans les colonnes multi-valeurs
        for col in ["distributeurs", "zone_geographique_de_vente", "risques_encourus"]:
            if col in df.columns:
                 # Normalise les séparateurs et s'assure que c'est une chaîne
                df[col] = df[col].astype(str).str.lower().str.replace("|", ";", regex=False).str.replace(", ", ";", regex=False).str.strip()

        return df

    except Exception as e:
        error_url = r.url if r is not None else base_url
        error_status = r.status_code if r is not None else "N/A"
        st.error(f"❌ Erreur lors du chargement des données depuis l’API ({error_status}) : {error_url}")
        st.error(f"Message d'erreur complet : {e}")
        return pd.DataFrame()


# --- FONCTION UTILITAIRE POUR L'ANALYSE MULTI-VALEUR ---
def explode_column(df, column_name):
    """Divise une colonne de chaînes de caractères séparées par des points-virgules (;) en lignes distinctes."""
    if column_name in df.columns:
        return (
            df.assign(temp_col=df[column_name].str.split(";"))
            .explode("temp_col")
            .rename(columns={"temp_col": column_name})
            .dropna(subset=[column_name])
            .reset_index(drop=True)
        )
    # Retourne un DataFrame vide SANS colonne si elle manque.
    return pd.DataFrame()

# --- Chargement des données ---
df = load_data()

if df.empty:
    st.warning("⚠️ Impossible de charger les données depuis l’API RappelConso. Réessaie plus tard.")
    st.stop()

# --- FILTRES B2B EN SIDEBAR (LOGIQUE DÉFENSIVE MISE À JOUR) ---
st.sidebar.header("Filtres d'Intelligence Marché")
df_temp = df.copy()

# 1. Distributeurs (Explode needed - Correction finale de l'AttributeError)
distrib_col_name = "distributeurs"
distributeurs_list = ["Toutes"] # Initialisation sûre

if distrib_col_name in df_temp.columns:
    df_exploded_distrib = explode_column(df_temp, distrib_col_name)

    # VÉRIFICATION ROBUSTE : S'assurer que la colonne existe dans le résultat EXPLODED
    if distrib_col_name in df_exploded_distrib.columns and not df_exploded_distrib.empty:
        # LIGNE CRUCIALE CORRIGÉE : S'assurer du typage string avant les opérations .str,
        # puis filtrer les valeurs vides.
        valid_distrib = (
            df_exploded_distrib[distrib_col_name]
            .astype(str)
            .str.strip()
            .replace('', pd.NA, regex=False)
            .dropna()
            .unique()
            .tolist()
        )
        distributeurs_list = ["Toutes"] + sorted(valid_distrib)


# 2. Motifs (Simple column)
if "motif_du_rappel" in df_temp.columns:
    motifs_list = ["Toutes"] + sorted(df_temp["motif_du_rappel"].dropna().unique().tolist())
else:
    motifs_list = ["Toutes"]

# 3. Categories (Simple column)
if "categorie_de_produit" in df_temp.columns:
    categories = ["Toutes"] + sorted(df_temp["categorie_de_produit"].dropna().unique().tolist())
else:
    categories = ["Toutes"]

# 4. Marques (Simple column)
if "nom_marque_du_produit" in df_temp.columns:
    marques = ["Toutes"] + sorted(df_temp["nom_marque_du_produit"].dropna().unique().tolist())
else:
    marques = ["Toutes"]

# Widgets de filtres
periode = st.sidebar.selectbox("Période d'Analyse", ["12 derniers mois", "6 derniers mois", "3 derniers mois", "Toute la période"])
cat = st.sidebar.selectbox("Catégorie de Produit", categories)
marque = st.sidebar.selectbox("Marque (Benchmarking)", marques)
distrib = st.sidebar.selectbox("Distributeur (Analyse du Canal)", distributeurs_list)
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

# Filtre Distributeur
if distrib != "Toutes" and "distributeurs" in df_filtered.columns:
    # Utilise str.contains sur la colonne multi-valeurs de df_filtered
    df_filtered = df_filtered[df_filtered["distributeurs"].str.contains(distrib, case=False, na=False)]


# --- INDICATEURS CLÉS STRATÉGIQUES ---
total_rappels = len(df_filtered)

st.header("1. Aperçu Stratégique")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Rappels (Filtré)", total_rappels)
col2.metric("Marques Impactées", df_filtered["nom_marque_du_produit"].nunique() if "nom_marque_du_produit" in df.columns else 0)

# Analyse du Risque le plus Fréquent
df_risques_exploded = explode_column(df_filtered, "risques_encourus")
# Défense contre l'absence de colonnes après explode
if not df_risques_exploded.empty and "risques_encourus" in df_risques_exploded.columns:
    risque_major = df_risques_exploded["risques_encourus"].value_counts().index.get(0)
    col3.metric("Risque Principal", risque_major.title())
else:
    col3.metric("Risque Principal", "N/A")

# Taux de Risque Microbiologique
if "motif_du_rappel" in df_filtered.columns:
    microbien_count = df_filtered[df_filtered["motif_du_rappel"].str.contains("microbiologique|salmonelle|listeria|ecoli", case=False, na=False)].shape[0]
    taux_microbien = f"{(microbien_count / total_rappels * 100):.1f}%" if total_rappels > 0 else "0.0%"
else:
    taux_microbien = "N/A"
col4.metric("Taux de Risque Microbiologique", taux_microbien)

st.markdown("---")

# --- GRAPHIQUES B2B D'INTELLIGENCE MARCHÉ ---

st.header("2. Benchmarking et Analyse des Causes")

col_left, col_right = st.columns(2)

# Graphique 1: Part de Rappel par Marque (SoR - Share of Recall)
with col_left:
    st.subheader("Benchmark 🎯 : Part de Rappel par Marque (SoR - Share of Recall)")
    if "nom_marque_du_produit" in df_filtered.columns and total_rappels > 0:
        top_marques = df_filtered["nom_marque_du_produit"].value_counts(normalize=True).mul(100).reset_index().rename(columns={
            "nom_marque_du_produit": "Marque", 
            "proportion": "Part_de_Rappel_pourcent"
        })
        top_marques = top_marques.head(10)
        fig_sor = px.pie(top_marques, values="Part_de_Rappel_pourcent", names="Marque", title="Distribution des rappels (%) sur le périmètre filtré")
        fig_sor.update_traces(textinfo='percent+label')
        st.plotly_chart(fig_sor, use_container_width=True)
    else:
        st.info("Filtrez les données pour effectuer le benchmarking.")


# Graphique 2: Top 5 des Risques Encourus (Analyse de Gravité)
with col_right:
    st.subheader("Analyse de Risque 💀 : Top 5 des Risques Encourus")
    if not df_risques_exploded.empty and "risques_encourus" in df_risques_exploded.columns:
        top_risques = df_risques_exploded["risques_encourus"].value_counts().reset_index().rename(columns={
            "risques_encourus": "Risque", 
            "count": "Nombre_de_Rappels"
        }).head(5)
        fig_risques = px.bar(top_risques, x="Nombre_de_Rappels", y="Risque", orientation='h', title="Fréquence des principaux dangers (Listeria, E. Coli, Inertes...)")
        fig_risques.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_risques, use_container_width=True)
    else:
        st.info("Aucun risque identifié ou données de risque manquantes.")

st.markdown("---")

# --- GRAPHIQUES D'EXPOSITION (TEMPorel & Géographique/Canal) ---

st.header("3. Tendance et Exposition")
col_gauche, col_droite = st.columns(2)

# Graphique 3: Tendance Temporelle (Cycle de Vie du Rappel)
with col_gauche:
    st.subheader("Tendance Temporelle ⏳ : Volume mensuel de rappels")
    if "date_publication" in df_filtered.columns:
        df_month = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="rappels")
        df_month["date_publication"] = df_month["date_publication"].dt.to_timestamp()
        fig_trend = px.line(df_month, x="date_publication", y="rappels", title="Évolution du volume de rappels par mois de publication")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("Données de publication manquantes.")

# Graphique 4: Top 10 Distributeurs ou Régions (Analyse de l'Exposition)
with col_droite:
    st.subheader("Exposition 📍 : Canaux de Distribution / Régions les plus impactés")
    
    target_kpi = st.radio("Afficher le Top 10 par :", ("Distributeur", "Région"), key="target_kpi", horizontal=True)
    
    col_name = "distributeurs" if target_kpi == "Distributeur" else "zone_geographique_de_vente"
    title_text = f"Top 10 {target_kpi} par Nombre de Rappels"

    if col_name in df_filtered.columns:
        df_exposed = explode_column(df_filtered, col_name)
        
        # Filtre les entrées non valides
        df_exposed = df_exposed[~df_exposed[col_name].isin(['nan', ''])]
        
        if not df_exposed.empty and col_name in df_exposed.columns:
            top_exposure = df_exposed[col_name].value_counts().reset_index().rename(columns={
                col_name: "Cible", 
                "count": "Nombre_de_Rappels"
            }).head(10)
            
            fig_exposure = px.bar(top_exposure, y="Cible", x="Nombre_de_Rappels", orientation='h', title=title_text)
            fig_exposure.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_exposure, use_container_width=True)
        else:
            st.info(f"Aucune donnée de {target_kpi} dans les filtres sélectionnés.")
    else:
        st.info(f"Colonne {col_name} manquante dans les données.")

st.markdown("---")

# --- TABLEAU DE DONNÉES DÉTAILLÉ (Data Export) ---
st.header("4. Registre Détaillé des Rappels")
st.write("### 🔍 Détail des Rappels Filtrés (pour export et analyse des fiches)")
display_cols = [c for c in ["reference_fiche", "date_publication", "categorie_de_produit", "nom_marque_du_produit", "motif_du_rappel", "risques_encourus", "distributeurs", "zone_geographique_de_vente", "liens_vers_la_fiche_rappel"] if c in df_filtered.columns]
st.dataframe(df_filtered[display_cols].sort_values(by="date_publication", ascending=False).reset_index(drop=True), use_container_width=True)

csv = df_filtered[display_cols].to_csv(index=False)
st.download_button(label="💾 Télécharger les Données Filtrées (CSV)", data=csv, file_name="recall_analytics_export.csv", mime="text/csv")

st.markdown("---")
st.caption("Prototype Recall Analytics — Données publiques (c) RappelConso.gouv.fr / Ministère de l'Économie")
