# app.py
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime

# --- Configuration générale ---
st.set_page_config(page_title="Recall Analytics (MVP)", layout="wide")
st.title("📊 Recall Analytics — Suivi des rappels produits en France")

st.markdown("""
Bienvenue sur **Recall Analytics**, un tableau de bord interactif qui analyse les rappels de produits publiés sur [RappelConso.gouv.fr](https://rappel.conso.gouv.fr).  
Ce prototype récupère automatiquement les dernières données publiques et permet d'explorer les rappels par **catégorie**, **marque**, et **période**.
""")

# --- Fonction de chargement des données ---
@st.cache_data(ttl=60*60)
def load_data():
    try:
        API_URL = "https://data.economie.gouv.fr/api/records/1.0/search/"
        params = {
            "dataset": "rappelconso",
            "rows": 1000,
            "sort": "-date_publication"
        }
        r = requests.get(API_URL, params=params, timeout=30)
        if r.status_code != 200:
            st.warning(f"⚠️ L'API RappelConso a renvoyé le code {r.status_code}. Réessaye plus tard.")
            return pd.DataFrame()
        records = r.json().get("records", [])
        if not records:
            st.warning("Aucune donnée disponible pour l'instant.")
            return pd.DataFrame()

        df = pd.json_normalize([rec.get("fields", {}) for rec in records])
        cols = [
            "numero_fiche", "date_publication", "categorie_produit",
            "sous_categorie_produit", "marque_produit", "enseigne_distributeur",
            "motif_rappel", "nature_juridique_rappel", "lien_vers_la_fiche_rappel"
        ]
        df = df[[c for c in cols if c in df.columns]]
        if "date_publication" in df.columns:
            df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
        return df

    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des données : {e}")
        return pd.DataFrame()

# --- Chargement initial ---
df = pd.DataFrame()
df = load_data()

if df is None or df.empty:
    st.warning("⚠️ Impossible de charger les données RappelConso pour le moment. Réessaie dans quelques minutes.")
    st.stop()

# --- Filtres latéraux ---
st.sidebar.header("Filtres")

categories = ["Toutes"]
marques = ["Toutes"]

if "categorie_produit" in df.columns:
    categories += sorted(df["categorie_produit"].dropna().unique().tolist())
if "marque_produit" in df.columns:
    marques += sorted(df["marque_produit"].dropna().unique().tolist())

periode = st.sidebar.selectbox("Période (mois)", ["12 derniers mois", "6 derniers mois", "3 derniers mois", "Toute la période"])
cat = st.sidebar.selectbox("Catégorie", categories)
marque = st.sidebar.selectbox("Marque", marques)

# --- Application des filtres ---
df_filtered = df.copy()

if cat != "Toutes" and "categorie_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["categorie_produit"] == cat]
if marque != "Toutes" and "marque_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["marque_produit"] == marque]

if "date_publication" in df_filtered.columns:
    now = pd.Timestamp(datetime.now())
    if periode == "12 derniers mois":
        cutoff = now - pd.DateOffset(months=12)
        df_filtered = df_filtered[df_filtered["date_publication"] >= cutoff]
    elif periode == "6 derniers mois":
        cutoff = now - pd.DateOffset(months=6)
        df_filtered = df_filtered[df_filtered["date_publication"] >= cutoff]
    elif periode == "3 derniers mois":
        cutoff = now - pd.DateOffset(months=3)
        df_filtered = df_filtered[df_filtered["date_publication"] >= cutoff]

# --- Indicateurs clés ---
col1, col2, col3 = st.columns(3)
col1.metric("Rappels total (filtré)", len(df_filtered))
if "date_publication" in df_filtered.columns and not df_filtered["date_publication"].isna().all():
    col2.metric("Dernière publication", str(df_filtered["date_publication"].max().date()))
else:
    col2.metric("Dernière publication", "N/A")
col3.metric("Catégories", df_filtered["categorie_produit"].nunique() if "categorie_produit" in df_filtered.columns else "N/A")

# --- Graphique d'évolution mensuelle ---
if "date_publication" in df_filtered.columns:
    df_month = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="rappels")
    df_month["date_publication"] = df_month["date_publication"].dt.to_timestamp()
    fig = px.bar(df_month, x="date_publication", y="rappels", title="📈 Évolution mensuelle des rappels")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Pas de dates disponibles pour afficher l'évolution temporelle.")

# --- Top marques ---
if "marque_produit" in df_filtered.columns and not df_filtered["marque_produit"].dropna().empty:
    top_marques = df_filtered["marque_produit"].value_counts().reset_index().rename(columns={"index":"marque", "marque_produit":"rappels"})
    top_marques = top_marques.head(10)
    fig2 = px.bar(top_marques, x="marque", y="rappels", title="🏷️ Top 10 des marques les plus rappelées")
    st.plotly_chart(fig2, use_container_width=True)

# --- Tableau détaillé ---
st.write("### 🔍 Détail des rappels filtrés")
display_cols = [c for c in ["numero_fiche","date_publication","categorie_produit","marque_produit","motif_rappel","lien_vers_la_fiche_rappel"] if c in df_filtered.columns]
st.dataframe(df_filtered[display_cols].sort_values(by="date_publication", ascending=False).reset_index(drop=True))

# --- Export CSV ---
csv = df_filtered[display_cols].to_csv(index=False)
st.download_button(label="💾 Télécharger les données filtrées (CSV)", data=csv, file_name="rappels_filtres.csv", mime="text/csv")

st.markdown("---")
st.caption("Prototype Recall Analytics — Données publiques © RappelConso.gouv.fr / Ministère de l'Économie et des Finances")
