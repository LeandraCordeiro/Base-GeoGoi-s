import os
import re
from io import StringIO
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

@st.cache_data(ttl=900, show_spinner=False)
def load_repo_csv(rel_path):
    raw_url = (
        f"https://raw.githubusercontent.com/"
        f"{OWNER}/{REPO}/{BRANCH}/{rel_path}"
    )

    try:
        response = requests.get(raw_url, timeout=20)

        if response.status_code == 404:
            return None

        response.raise_for_status()

        return pd.read_csv(
            StringIO(response.content.decode("utf-8-sig")),
            dtype=str
        ).fillna("")

    except Exception:
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


# ===============================================================
# Extração automática: menções verificáveis nos documentos PDF
# ===============================================================
import fitz  # PyMuPDF

# Vocabulários iniciais editáveis. Novos termos podem ser incluídos.
MINERAIS = {
    "Nióbio": [r"\bnióbio\b", r"\bniobio\b"],
    "Fosfato": [r"\bfosfat(?:o|os|ada|adas|ado|ados)\b", r"\bapatita\b"],
    "Terras raras": [r"\bterras? raras?\b", r"\belementos? de terras? raras?\b", r"\bETR\b", r"\bREE\b"],
    "Níquel": [r"\bníquel\b", r"\bniquel\b"],
    "Ouro": [r"\bouros?\b", r"\baurífer[oa]s?\b", r"\baurifer[oa]s?\b"],
    "Vermiculita": [r"\bvermiculitas?\b"],
    "Cobre": [r"\bcobres?\b", r"\bcuprífer[oa]s?\b"],
    "Cobalto": [r"\bcobaltos?\b"],
    "Estanho": [r"\bestanhos?\b"],
    "Lítio": [r"\blítio\b", r"\blitio\b"],
    "Grafita": [r"\bgrafitas?\b", r"\bgrafites?\b"],
}
MUNICIPIOS = {
    "Mara Rosa": [r"\bmara rosa\b"],
    "Crixás": [r"\bcrixás\b", r"\bcrixas\b"],
    "Catalão": [r"\bcatalão\b", r"\bcatalao\b"],
    "Ouvidor": [r"\bouvidor\b"],
    "Niquelândia": [r"\bniquelândia\b", r"\bniquelandia\b"],
    "Barro Alto": [r"\bbarro alto\b"],
    "Minaçu": [r"\bminaçu\b", r"\bminacu\b"],
    "Pilar de Goiás": [r"\bpilar de goiás\b", r"\bpilar de goias\b"],
    "Alto Horizonte": [r"\balto horizonte\b"],
    "Alto Paraíso de Goiás": [r"\balto paraíso de goiás\b", r"\balto paraiso de goias\b"],
    "Formosa": [r"\bformosa\b"],
    "Goiânia": [r"\bgoiânia\b", r"\bgoiania\b"],
    "Orizona": [r"\borizona\b"],
    "Nova Crixás": [r"\bnova crixás\b", r"\bnova crixas\b"],
    "Faina": [r"\bfaina\b"],
    "Guarinos": [r"\bguarinos\b"],
    "Bom Jardim de Goiás": [r"\bbom jardim de goiás\b", r"\bbom jardim de goias\b"],
}
UNIDADES = {
    "Faixa Brasília": [r"\bfaixa brasília\b", r"\bfaixa brasilia\b"],
    "Arco Magmático de Goiás": [r"\barco magmático de goiás\b", r"\barco magmatico de goias\b"],
    "Maciço de Goiás": [r"\bmaciço de goiás\b", r"\bmacico de goias\b"],
    "Complexo de Niquelândia": [r"\bcomplexo de niquelândia\b", r"\bcomplexo de niquelandia\b"],
    "Complexo de Barro Alto": [r"\bcomplexo de barro alto\b"],
    "Bacia do Paraná": [r"\bbacia do paraná\b", r"\bbacia do parana\b"],
}

@st.cache_data(ttl=86400, show_spinner=False)
def extrair_pdf(caminho, sha, limite_paginas=500):
    """Retorna menções textuais. SHA invalida cache quando PDF muda no GitHub."""
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{quote(caminho, safe='/')}"
    resp = requests.get(url, timeout=90, headers={"User-Agent": "GeoGoiasDashboard"})
    resp.raise_for_status()
    if len(resp.content) > 25 * 1024 * 1024:
        raise ValueError("PDF acima do limite de 25 MB desta versão")
    rows = []
    with fitz.open(stream=resp.content, filetype="pdf") as documento:
        total = len(documento)
        paginas_texto = 0
        for ipagina in range(min(total, limite_paginas)):
            texto = re.sub(r"\s+", " ", documento[ipagina].get_text("text")).strip()
            if not texto:
                continue
            paginas_texto += 1
            for classe, vocabulario in [("Mineral", MINERAIS), ("Município (menção)", MUNICIPIOS), ("Unidade geológica", UNIDADES)]:
                for termo, padroes in vocabulario.items():
                    ocorrencias = []
                    for padrao in padroes:
                        ocorrencias.extend(re.finditer(padrao, texto, flags=re.IGNORECASE))
                    ocorrencias = sorted(ocorrencias, key=lambda m: m.start())
                    if ocorrencias:
                        m = ocorrencias[0]
                        trecho = texto[max(0,m.start()-100):min(len(texto),m.end()+130)].strip()
                        rows.append({"caminho": caminho, "classe": classe, "termo": termo,
                                     "pagina_pdf": ipagina + 1, "mencoes_pagina": len(ocorrencias),
                                     "trecho": trecho, "status": "Menção automática — validar"})
    return rows, paginas_texto, total

st.subheader("Extração automática de conteúdo dos PDFs")
st.caption("Busca textual automática em PDFs do GitHub, com páginas e trechos de evidência. Menções não são comprovação de depósito, nem necessariamente área-objeto do estudo.")
colauto, colmax = st.columns([2,1])
with colauto:
    auto_extracao = st.toggle("Analisar PDFs automaticamente", value=True, help="Na primeira execução o aplicativo precisa baixar e ler os PDFs. Resultados de arquivos inalterados são mantidos em cache por 24 horas.")
with colmax:
    limite_pdfs = st.number_input("Máximo de PDFs por execução", min_value=1, max_value=100, value=15, step=1)

arquivos_pdf = [e for e in tree if e.get("type") == "blob" and e.get("path", "").lower().endswith(".pdf") and (e.get("size") or 0) <= 25 * 1024 * 1024]
arquivos_pdf = sorted(arquivos_pdf, key=lambda e: e["path"])
if auto_extracao:
    alvos = arquivos_pdf[:int(limite_pdfs)]
    candidatas, falhas, sem_texto = [], [], []
    barra = st.progress(0, text="Analisando PDFs do repositório...")
    for n, e in enumerate(alvos, start=1):
        try:
            rows, paginas_com_texto, total_paginas = extrair_pdf(e["path"], e.get("sha", ""))
            candidatas.extend(rows)
            if paginas_com_texto == 0:
                sem_texto.append(e["path"])
        except Exception as exc:
            falhas.append((e["path"], str(exc)[:150]))
        barra.progress(n / max(1,len(alvos)), text=f"PDFs analisados: {n}/{len(alvos)}")
    barra.empty()
    st.metric("PDFs analisados automaticamente", len(alvos) - len(falhas))
    if len(arquivos_pdf) > len(alvos):
        st.info(f"Foram analisados os primeiros {len(alvos)} de {len(arquivos_pdf)} PDFs. Aumente o limite para cobrir mais arquivos.")
    if sem_texto:
        st.warning(f"{len(sem_texto)} PDFs não apresentaram texto extraível. Podem exigir OCR; não foram inferidos resultados.")
    if falhas:
        st.warning(f"{len(falhas)} PDFs não puderam ser analisados.")
        with st.expander("Ver arquivos com erro"):
            st.dataframe(pd.DataFrame(falhas, columns=["Arquivo", "Motivo"]), hide_index=True)
    if candidatas:
        df_candidatos = pd.DataFrame(candidatas)
        st.success(f"{len(df_candidatos)} combinações de termo e página encontradas, pendentes de validação.")
        c_m, c_a = st.columns(2)
        with c_m:
            dm = df_candidatos[df_candidatos["classe"] == "Mineral"].drop_duplicates(["caminho", "termo"])
            if not dm.empty:
                cont = dm.groupby("termo").size().reset_index(name="documentos_com_mencao")
                st.plotly_chart(px.bar(cont, x="termo", y="documentos_com_mencao", title="Minerais mencionados nos PDFs (não validados)"), use_container_width=True)
        with c_a:
            da = df_candidatos[df_candidatos["classe"] == "Município (menção)"].drop_duplicates(["caminho", "termo"])
            if not da.empty:
                cont = da.groupby("termo").size().reset_index(name="documentos_com_mencao")
                st.plotly_chart(px.bar(cont, x="termo", y="documentos_com_mencao", title="Municípios mencionados nos PDFs (não validados)"), use_container_width=True)
        filtro_classe = st.multiselect("Filtrar evidências", sorted(df_candidatos["classe"].unique()), default=sorted(df_candidatos["classe"].unique()))
        st.dataframe(df_candidatos[df_candidatos["classe"].isin(filtro_classe)], hide_index=True, use_container_width=True)
        st.download_button("Baixar candidatos e evidências (CSV)", data=df_candidatos.to_csv(index=False).encode("utf-8-sig"), file_name="candidatos_geogoias.csv", mime="text/csv")
        st.caption("A coluna pagina_pdf é a página física do arquivo PDF; pode diferir da numeração impressa. O aplicativo não altera automaticamente o catalogo_mestre.csv no GitHub.")
    else:
        st.info("Nenhuma menção reconhecida. Verifique se os documentos contêm texto selecionável ou amplie os vocabulários de busca.")
else:
    st.info("Ative a extração para analisar os documentos. O inventário e o catálogo continuam disponíveis acima.")

st.divider()
st.caption("GeoGoiás · Registros de documentos não equivalem a depósitos, reservas, cobertura territorial ou produção mineral.")


# ==========================================
# MAPA INTERATIVO GEOGOIAS
# ==========================================

st.subheader("Mapa interativo de Goiás")

areas_df = load_repo_csv(
    "07_metadados/areas_estudadas.csv"
)

ocorr_df = load_repo_csv(
    "07_metadados/ocorrencias_minerais.csv"
)

if areas_df is None and ocorr_df is None:
    st.info(
        "Adicione os arquivos areas_estudadas.csv e "
        "ocorrencias_minerais.csv na pasta 07_metadados."
    )

else:
    fig_mapa = go.Figure()

    if areas_df is not None and not areas_df.empty:
        areas_df["latitude"] = pd.to_numeric(
            areas_df["latitude"], errors="coerce"
        )
        areas_df["longitude"] = pd.to_numeric(
            areas_df["longitude"], errors="coerce"
        )
        areas_df["n_estudos"] = pd.to_numeric(
            areas_df["n_estudos"], errors="coerce"
        )

        areas_validas = areas_df.dropna(
            subset=["latitude", "longitude", "n_estudos"]
        )

        if not areas_validas.empty:
            fig_mapa.add_trace(
                    go.Scattermap(
                    lat=areas_validas["latitude"],
                    lon=areas_validas["longitude"],
                    mode="markers",
                    name="Áreas estudadas",
                    marker=dict(
                        size=areas_validas["n_estudos"].clip(
                            lower=1, upper=20
                        ) * 2 + 8,
                        color="#176A9D",
                        opacity=0.75,
                    ),
                    text=areas_validas["municipio"],
                    customdata=areas_validas[["n_estudos"]].values,
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "Estudos cadastrados: %{customdata[0]}"
                        "<extra></extra>"
                    ),
                )
            )

    if ocorr_df is not None and not ocorr_df.empty:
        ocorr_df["latitude"] = pd.to_numeric(
            ocorr_df["latitude"], errors="coerce"
        )
        ocorr_df["longitude"] = pd.to_numeric(
            ocorr_df["longitude"], errors="coerce"
        )

        ocorr_validas = ocorr_df.dropna(
            subset=["latitude", "longitude"]
        )

        for mineral in ocorr_validas["substancia"].unique():
            if not str(mineral).strip():
                continue

            dados = ocorr_validas[
                ocorr_validas["substancia"] == mineral
            ]

            fig_mapa.add_trace(
                go.Scattermap(
                    lat=dados["latitude"],
                    lon=dados["longitude"],
                    mode="markers",
                    name=str(mineral),
                    marker=dict(size=11, opacity=0.85),
                    text=dados["municipio"],
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        f"Mineral: {mineral}<extra></extra>"
                    ),
                )
            )

    fig_mapa.update_layout(
    map=dict(
        style="open-street-map",
        center=dict(lat=-15.8, lon=-49.3),
        zoom=5.5,
        ),
        height=600,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h"),
    )

    if fig_mapa.data:
        st.plotly_chart(
            fig_mapa,
            use_container_width=True
        )
    else:
        st.warning(
            "Os arquivos foram encontrados, mas ainda não "
            "contêm registros geográficos suficientes."
        )

    st.caption(
        "Pontos exibidos conforme coordenadas cadastradas. "
        "Coordenadas municipais aproximadas não representam "
        "a localização exata de depósitos minerais."
    )

from mapa_geologico import mostrar_mapa_geologico

st.divider()
mostrar_mapa_geologico()
