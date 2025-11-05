# app.py
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Recall Analytics (MVP)", layout="wide")
st.title("📊 Recall Analytics — Rappels produits (MVP)")

API_URL = "https://rappel.conso.gouv.fr/api/records/1.0/search/?dataset=rappelconso&q=&rows=1000"

@st.cache_data(ttl=60*60)  # cache 1 heure
def load_data():
    r = requests.get(API_URL, timeout=30)
    r.raise_for_status()
    records = r.json().get("records", [])
    if not records:
        return pd.DataFrame()
    df = pd.json_normalize([rec.get("fields", {}) for rec in records])
    # Quelques colonnes utiles (si présentes)
    cols = [
        "numero_fiche", "date_publication", "categorie_produit",
        "sous_categorie_produit", "marque_produit", "enseigne_distributeur",
        "motif_rappel", "nature_juridique_rappel", "lien_vers_la_fiche_rappel"
    ]
    # Garde les colonnes qui existent
    df = df[[c for c in cols if c in df.columns]]
    # Nettoyage des dates
    if "date_publication" in df.columns:
        df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
    return df

df = load_data()

if df.empty:
    st.warning("Aucune donnée trouvée pour l'instant. Réessaie dans quelques minutes.")
    st.stop()

# Sidebar - filtres
st.sidebar.header("Filtres")
categories = ["Toutes"] + sorted(df["categorie_produit"].dropna().unique().tolist()) if "categorie_produit" in df.columns else ["Toutes"]
marques = ["Toutes"] + sorted(df["marque_produit"].dropna().unique().tolist()) if "marque_produit" in df.columns else ["Toutes"]
periode = st.sidebar.selectbox("Période (mois)", ["12 derniers mois", "6 derniers mois", "3 derniers mois", "Toute la période"])

cat = st.sidebar.selectbox("Catégorie", categories)
marque = st.sidebar.selectbox("Marque", marques)

# Appliquer filtres
df_filtered = df.copy()
if cat != "Toutes" and "categorie_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["categorie_produit"] == cat]
if marque != "Toutes" and "marque_produit" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["marque_produit"] == marque]

# Filtre période
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

# KPIs
col1, col2, col3 = st.columns(3)
col1.metric("Rappels total (filtré)", len(df_filtered))
if "date_publication" in df_filtered.columns:
    col2.metric("Dernière publication", str(df_filtered["date_publication"].max().date()))
else:
    col2.metric("Dernière publication", "N/A")
col3.metric("Catégories", df_filtered["categorie_produit"].nunique() if "categorie_produit" in df_filtered.columns else "N/A")

# Graphique évolution mensuelle
if "date_publication" in df_filtered.columns:
    df_month = df_filtered.groupby(df_filtered["date_publication"].dt.to_period("M")).size().reset_index(name="rappels")
    df_month["date_publication"] = df_month["date_publication"].dt.to_timestamp()
    fig = px.bar(df_month, x="date_publication", y="rappels", title="Évolution mensuelle des rappels")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Pas de dates disponibles pour afficher l'évolution temporelle.")

# Top marques
if "marque_produit" in df_filtered.columns:
    top_marques = df_filtered["marque_produit"].value_counts().reset_index().rename(columns={"index":"marque", "marque_produit":"rappels"})
    top_marques = top_marques.head(10)
    fig2 = px.bar(top_marques, x="marque", y="rappels", title="Top 10 des marques les plus rappelées")
    st.plotly_chart(fig2, use_container_width=True)

# Table
st.write("### Détail des rappels (filtré)")
display_cols = [c for c in ["numero_fiche","date_publication","categorie_produit","marque_produit","motif_rappel","lien_vers_la_fiche_rappel"] if c in df_filtered.columns]
st.dataframe(df_filtered[display_cols].sort_values(by="date_publication", ascending=False).reset_index(drop=True))

# Export CSV
csv = df_filtered[display_cols].to_csv(index=False)
st.download_button(label="Télécharger CSV (filtré)", data=csv, file_name="rappels_filtres.csv", mime="text/csv")
