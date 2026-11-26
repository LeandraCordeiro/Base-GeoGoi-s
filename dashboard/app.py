import os
import re
from io import StringIO
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

OWNER = "LeandraCordeiro"
REPO = "Base-GeoGoi-s"
BRANCH = "main"
BASE = f"https://github.com/{OWNER}/{REPO}"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
FOLDERS = {
    "01_geologia": "Geologia", "02_geofisica": "Geofísica",
    "03_geoquimica": "Geoquímica", "04_recursos_minerais": "Recursos minerais",
    "05_processos_minerarios": "Processos minerários", "06_infraestrutura": "Infraestrutura",
    "07_metadados": "Metadados", "08_analises": "Análises",
    "09_produtos": "Produtos", "10_documentacao": "Documentação",
    "11_acervo_metago": "Acervo METAGO",
}
DOC_TYPES = {
    "TES": "Tese", "TESE": "Tese", "DIS": "Dissertação", "ART": "Artigo",
    "MAP": "Mapa", "LEV": "Levantamento", "REL": "Relatório",
    "DAT": "Dados", "ANA": "Análise", "VET": "Vetor",
    "RAS": "Raster", "MET": "Metadados", "SCR": "Script", "PRO": "Produto",
}

st.set_page_config(page_title="GeoGoiás | Inventário geocientífico", page_icon="🗺️", layout="wide")
st.title("GeoGoiás | Inteligência Geocientífica")
st.caption("Inventário dinâmico dos arquivos do repositório público · Fonte: GitHub · Sem dados ilustrativos")

@st.cache_data(ttl=900, show_spinner=False)
def load_tree():
    url = f"{API}/git/trees/{BRANCH}?recursive=1"
    r = requests.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "GeoGoiasDashboard"}, timeout=25)
    r.raise_for_status()
    payload = r.json()
    if payload.get("truncated"):
        st.warning("A lista de arquivos retornada pelo GitHub foi truncada; indicadores podem estar incompletos.")
    return payload.get("tree", [])

@st.cache_data(ttl=900, show_spinner=False)
def load_catalog():
    raw_url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/07_metadados/catalogo_mestre.csv"
    try:
        response = requests.get(raw_url, timeout=20)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return pd.read_csv(StringIO(response.content.decode("utf-8-sig")), dtype=str).fillna("")
    except (requests.RequestException, ValueError, UnicodeDecodeError):
        return None

try:
    tree = load_tree()
except requests.RequestException as e:
    st.error("Não foi possível consultar o repositório pelo GitHub. Verifique a conexão e se o repositório está público.")
    st.caption(str(e))
    st.stop()

records = []
for item in tree:
    if item.get("type") != "blob":
        continue
    path = item.get("path", "")
    parts = path.split("/")
    directory = parts[0] if len(parts) > 1 else "raiz"
    filename = parts[-1]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "sem extensão"
    stem = filename.rsplit(".", 1)[0]
    tokens = stem.split("_")
    kind = DOC_TYPES.get(tokens[1].upper(), "Não classificado") if len(tokens) >= 3 and tokens[0].upper() == "GO" else "Não classificado"
    year_match = re.search(r"(?:19|20)\d{2}", stem)
    year = int(year_match.group(0)) if year_match else None
    records.append({
        "caminho": path, "arquivo": filename, "diretorio": directory,
        "categoria": FOLDERS.get(directory, "Outros"), "tipo": kind,
        "extensao": ext, "ano": year,
        "tamanho_mb": round((item.get("size") or 0) / 1048576, 2),
        "url": f"{BASE}/blob/{BRANCH}/{quote(path, safe='/')}",
    })

df = pd.DataFrame(records)
if df.empty:
    st.info("Ainda não há arquivos para inventariar.")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    categories = sorted(df["categoria"].unique().tolist())
    chosen_categories = st.multiselect("Área temática", categories, default=categories)
    extensions = sorted(df["extensao"].unique().tolist())
    chosen_extensions = st.multiselect("Formato", extensions, default=extensions)
    chosen_types = st.multiselect("Tipo de documento", sorted(df["tipo"].unique()), default=sorted(df["tipo"].unique()))
    search = st.text_input("Pesquisar arquivo ou caminho")
    st.link_button("Abrir repositório", BASE)
    st.caption("Atualização automática: cache de 15 minutos")

filtered = df[df["categoria"].isin(chosen_categories) & df["extensao"].isin(chosen_extensions) & df["tipo"].isin(chosen_types)].copy()
if search.strip():
    filtered = filtered[filtered["caminho"].str.contains(search.strip(), case=False, regex=False)]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Arquivos catalogados", f"{len(filtered):,}".replace(",", "."))
k2.metric("Pastas temáticas com arquivos", int(filtered[filtered["diretorio"].isin(FOLDERS)]["diretorio"].nunique()))
k3.metric("Documentos PDF", int((filtered["extensao"] == "pdf").sum()))
k4.metric("Volume dos arquivos", f"{filtered['tamanho_mb'].sum():,.1f} MB".replace(",", "X").replace(".", ",").replace("X", "."))

st.subheader("Distribuição dos arquivos")
c1, c2 = st.columns(2)
with c1:
    counts = filtered.groupby("categoria", as_index=False).size().rename(columns={"size": "arquivos"}).sort_values("arquivos", ascending=True)
    if not counts.empty:
        st.plotly_chart(px.bar(counts, x="arquivos", y="categoria", orientation="h", title="Arquivos por área temática"), use_container_width=True)
with c2:
    count_types = filtered.groupby("tipo", as_index=False).size().rename(columns={"size": "arquivos"})
    if not count_types.empty:
        st.plotly_chart(px.pie(count_types, names="tipo", values="arquivos", hole=0.5, title="Tipos de documento"), use_container_width=True)

with st.expander("Distribuição temporal", expanded=True):
    yearly = filtered.dropna(subset=["ano"]).groupby("ano", as_index=False).size().rename(columns={"size": "arquivos"})
    if yearly.empty:
        st.info("Não foram encontrados anos nos nomes padronizados dos arquivos.")
    else:
        yearly["ano"] = yearly["ano"].astype(int).astype(str)
        st.plotly_chart(px.bar(yearly, x="ano", y="arquivos", title="Arquivos por ano identificado no nome"), use_container_width=True)
        st.caption("Ano extraído do nome do arquivo, não validado contra o conteúdo do documento.")

st.subheader("Catálogo de arquivos")
st.dataframe(filtered[["arquivo", "categoria", "tipo", "ano", "extensao", "tamanho_mb", "caminho", "url"]], hide_index=True, use_container_width=True,
             column_config={"url": st.column_config.LinkColumn("Abrir arquivo", display_text="Ver no GitHub")})
st.download_button("Baixar inventário filtrado (CSV)", filtered.to_csv(index=False).encode("utf-8-sig"), "inventario_geogoias.csv", "text/csv")

st.subheader("Catálogo geocientífico enriquecido")
catalog = load_catalog()
if catalog is None:
    st.warning("O catálogo não foi carregado. Confira `07_metadados/catalogo_mestre.csv` no GitHub.")
else:
    catalog.columns = catalog.columns.str.strip()
    st.metric("Registros do catálogo de metadados", len(catalog))
    st.dataframe(catalog, hide_index=True, use_container_width=True)

    st.subheader("Minerais e áreas estudadas")
    st.caption("Os gráficos usam apenas campos preenchidos no catálogo. Menções extraídas automaticamente devem ser validadas antes de inclusão.")

    def contagem_multivalor(coluna):
        if coluna not in catalog.columns:
            return pd.DataFrame(columns=["item", "documentos"])
        series = catalog[coluna].fillna("").astype(str).str.split(";").explode().str.strip()
        series = series[series.ne("") & ~series.str.lower().isin(["não informado", "nao informado", "pendente", "nd"])]
        if series.empty:
            return pd.DataFrame(columns=["item", "documentos"])
        return series.value_counts().rename_axis("item").reset_index(name="documentos")

    col1, col2 = st.columns(2)
    with col1:
        minerais = contagem_multivalor("substancia")
        if minerais.empty:
            st.info("Sem minerais identificados no catálogo: preencha a coluna `substancia` após consultar os PDFs.")
        else:
            st.plotly_chart(px.bar(minerais, x="item", y="documentos", title="Documentos por mineral", labels={"item":"Mineral"}), use_container_width=True)
    with col2:
        areas = contagem_multivalor("municipio")
        if areas.empty:
            st.info("Sem áreas estudadas no catálogo: preencha a coluna `municipio` após consultar os PDFs.")
        else:
            st.plotly_chart(px.bar(areas, x="item", y="documentos", title="Documentos por município", labels={"item":"Município"}), use_container_width=True)

    if {"latitude", "longitude"}.issubset(catalog.columns):
        locations = catalog.copy()
        locations["latitude"] = pd.to_numeric(locations["latitude"], errors="coerce")
        locations["longitude"] = pd.to_numeric(locations["longitude"], errors="coerce")
        locations = locations.dropna(subset=["latitude", "longitude"])
        locations = locations[locations["latitude"].between(-90, 90) & locations["longitude"].between(-180, 180)]
        if not locations.empty:
            st.subheader("Localizações documentadas")
            st.map(locations.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
            st.caption("Somente coordenadas presentes no catálogo; não foram estimadas localizações.")

st.divider()
st.caption("GeoGoiás · Registros de documentos não equivalem a depósitos, reservas, cobertura territorial ou produção mineral.")
