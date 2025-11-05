import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Recall Analytics (RappelConso)", layout="wide")
st.title("📊 Recall Analytics — Rappels produits en France")

st.markdown("""
Bienvenue sur **Recall Analytics**, un tableau de bord interactif qui analyse les rappels de produits publiés sur [RappelConso.gouv.fr](https://rappel.conso.gouv.fr).  
Ce prototype utilise la **nouvelle API publique officielle** (v2.1) de [data.economie.gouv.fr](https://data.economie.gouv.fr).
""")

# --- Fonction de chargement depuis l’API (Tente limit=100 en cas d'échec initial) ---
@st.cache_data(ttl=3600)
def load_data(limit=10000): # Limite par défaut
    # URL de base du endpoint /records
    base_url = (
        f"https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
        f"rappelconso-v2-gtin-espaces/records"
    )
    
    # 1. Tentative avec le limit par défaut (10000)
    params = {"limit": limit}

    r = None
    try:
        r = requests.get(base_url, params=params, timeout=30)
        
        # 2. Si la première tentative échoue avec 400, tente une limite plus faible (100)
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

        # Mapping des noms de champs réels de l'API vers les noms utilisés dans le code Streamlit
        column_mapping = {
            "numero_fiche": "reference_fiche",
            "libelle": "nom_du_produit",
            "marque_produit": "nom_marque_du_produit",
            "categorie_produit": "categorie_de_produit",
            "motif_rappel": "motif_du_rappel",
            "lien_vers_la_fiche_rappel": "liens_vers_la_fiche_rappel",
            "date_publication": "date_publication",
            "distributeurs": "distributeurs",
            "zone_geographique_de_vente": "zone_geographique_de_vente"
        }
        
        df = df.rename(columns=column_mapping)

        # Sélection des colonnes nécessaires
        cols_finales = [
            "reference_fiche", "date_publication", "nom_du_produit",
            "nom_marque_du_produit", "categorie_de_produit",
            "motif_du_rappel", "distributeurs",
            "liens_vers_la_fiche_rappel", "zone_geographique_de_vente"
        ]
        df = df[[c for c in cols_finales if c in df.columns]]

        if "date_publication" in df.columns:
            # Conversion en datetime UTC-aware
            df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce", utc=True)
            # Tri local car le tri API a été supprimé
            df = df.sort_values(by="date_publication", ascending=False) 

        return df

    except Exception as e:
        # Affiche l'URL qui a causé l'erreur
        error_url = r.url if r is not None else base_url
        error_status = r.status_code if r is not None else "N/A"
        error_reason = r.reason if r is not None else "N/A"
        st.error(f"❌ Erreur lors du chargement des données depuis l’API ({error_status} - {error_reason}) : {error_url}")
        st.error(f"Message d'erreur complet : {e}")
        return pd.DataFrame()


# --- Chargement des données ---
df = load_data()

if df.empty:
    st.warning("⚠️ Impossible de charger les données depuis l’API RappelConso. Réessaie plus tard.")
    st.stop()

# --- Filtres ---
st.sidebar.header("Filtres")
categories = ["Toutes"] + sorted(df["categorie_de_produit"].dropna().unique().tolist()) if "categorie_de_produit" in df.columns else ["Toutes"]
marques = ["Toutes"] + sorted(df["nom_marque_du_produit"].dropna().unique().tolist()) if "nom_marque_du_produit" in df.columns else ["Toutes"]
periode = st.sidebar.selectbox("Période", ["12 derniers mois", "6 derniers mois", "3 derniers mois", "Toute la période"])
cat = st.sidebar.selectbox("Catégorie", categories)
marque = st.sidebar.selectbox("Marque", marques)

df_filtered = df.copy()
if cat != "Toutes" and "categorie_de_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["categorie_de_produit"] == cat]
if marque != "Toutes" and "nom_marque_du_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["nom_marque_du_produit"] == marque]

if "date_publication" in df_filtered.columns:
    # CORRECTION DU TYPE ERROR: Utiliser pd.Timestamp.now(tz='UTC') pour un objet timezone-aware (UTC)
    now = pd.Timestamp.now(tz='UTC') 
    
    if periode == "12 derniers mois":
        df_filtered = df_filtered[df_filtered["date_publication"] >= now - pd.DateOffset(months=12)]
    elif periode == "6 derniers mois":
        df_filtered = df_filtered[df_filtered["date_publication"] >= now - pd.DateOffset(months=6)]
    elif periode == "3 derniers mois":
        df_filtered = df_filtered[df_filtered["date_publication"] >= now - pd.DateOffset(months=3)]

# --- Indicateurs clés ---
col1, col2, col3 = st.columns(3)
col1.metric("Rappels total (filtré)", len(df_filtered))
if "date_publication" in df_filtered.columns and not df_filtered["date_publication"].isna().all():
    col2.metric("Dernière publication", str(df_filtered["date_publication"].max().date()))
else:
    col2.metric("Dernière publication", "N/A")
col3.metric("Catégories", df_filtered["categorie_de_produit"].nunique() if "categorie_de_produit" in df_filtered.columns else "N/A")

# --- Graphiques ---
if "date_publication" in df_filtered.columns:
    df_month = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="rappels")
    df_month["date_publication"] = df_month["date_publication"].dt.to_timestamp()
    fig = px.bar(df_month, x="date_publication", y="rappels", title="📈 Évolution mensuelle des rappels")
    st.plotly_chart(fig, use_container_width=True)

if "nom_marque_du_produit" in df_filtered.columns and not df_filtered["nom_marque_du_produit"].dropna().empty:
    top_marques = df_filtered["nom_marque_du_produit"].value_counts().reset_index().rename(columns={"index": "marque", "nom_marque_du_produit": "rappels"})
    top_marques = top_marques.head(10)
    fig2 = px.bar(top_marques, x="marque", y="rappels", title="🏷️ Top 10 des marques les plus rappelées")
    st.plotly_chart(fig2, use_container_width=True)

# --- Tableau ---
st.write("### 🔍 Détail des rappels filtrés")
display_cols = [c for c in ["reference_fiche", "date_publication", "categorie_de_produit", "nom_marque_du_produit", "motif_du_rappel", "liens_vers_la_fiche_rappel"] if c in df_filtered.columns]
st.dataframe(df_filtered[display_cols].sort_values(by="date_publication", ascending=False).reset_index(drop=True))

csv = df_filtered[display_cols].to_csv(index=False)
st.download_button(label="💾 Télécharger (CSV)", data=csv, file_name="rappels_filtres.csv", mime="text/csv")

st.markdown("---")
st.caption("Prototype Recall Analytics — Données publiques © RappelConso.gouv.fr / Ministère de l'Économie")
