"""Mapa das camadas vetoriais SGB na Base GeoGoiás: SHP, DBF em ZIP e SHP.XZ."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import lzma
import shutil
import zipfile
import requests

import folium
import geopandas as gpd
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent
PASTAS = [
    ROOT / "01_geologia/mapas_sgb",
    ROOT / "02_geofisica/mapas",
    ROOT / "03_geoquimica/mapas",
    ROOT / "04_recursos_minerais/mapas",
    ROOT / "05_processos_minerarios/mapas",
]
LIMITE_FEICOES = 1200
CORES = ["#1D6A96", "#C47D38", "#399178"]


def listar_camadas():
    camadas = {}
    for pasta in PASTAS:
        if not pasta.exists():
            continue
        for shp in pasta.rglob("*.shp"):
            camadas[str(shp.relative_to(ROOT))] = shp
        # Camadas com a geometria .shp.xz somente no ZIP (ex.: litologia).
        for pacote in pasta.rglob("*.zip"):
            try:
                with zipfile.ZipFile(pacote) as z:
                    for item in z.namelist():
                        if item.lower().endswith(".shp.xz"):
                            stem = Path(item).name[:-7]
                            virtual = pacote.parent / (stem + ".shp")
                            camadas[str(virtual.relative_to(ROOT))] = virtual
            except (zipfile.BadZipFile, OSError):
                pass
    return dict(sorted(camadas.items()))


def preparar_shapefile(shp, destino):
    stem = shp.stem
    componentes = (".shp", ".shx", ".dbf", ".prj", ".cpg")
    for ext in componentes:
        origem = shp.with_suffix(ext)
        if origem.exists():
            shutil.copy2(origem, destino / origem.name)

    for pacote in sorted(shp.parent.glob("*.zip")):
        if all((destino / (stem + ext)).exists() for ext in (".shp", ".shx", ".dbf")):
            break
        with zipfile.ZipFile(pacote) as z:
            for item in z.infolist():
                nome = Path(item.filename).name
                if nome.lower() not in {stem.lower() + ext for ext in componentes + (".shp.xz",)}:
                    continue
                if item.file_size > 350 * 1024 * 1024:
                    raise ValueError("Arquivo compactado maior que o limite de segurança.")
                if nome.lower().endswith(".shp.xz"):
                    saida = destino / (stem + ".shp")
                    if not saida.exists():
                        with z.open(item) as origem, lzma.LZMAFile(origem) as xz, open(saida, "wb") as f:
                            shutil.copyfileobj(xz, f)
                elif not (destino / nome).exists():
                    with z.open(item) as origem, open(destino / nome, "wb") as f:
                        shutil.copyfileobj(origem, f)

    faltam = [e for e in (".shp", ".shx", ".dbf") if not (destino / (stem + e)).exists()]
    if faltam:
        raise FileNotFoundError("Componentes ausentes: " + ", ".join(faltam))
    return destino / (stem + ".shp")


@st.cache_data(ttl=3600, show_spinner=False, max_entries=6)
def carregar_camada(caminho):
    shp = ROOT / caminho
    with TemporaryDirectory() as pasta:
        arquivo = preparar_shapefile(shp, Path(pasta))
        gdf = gpd.read_file(arquivo, engine="pyogrio")
    if gdf.crs is None:
        raise ValueError("Sistema de referência não identificado; verifique o .prj.")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].to_crs("EPSG:4326")
    total = len(gdf)
    # Envelope de consulta aproximado, NÃO é o limite cartográfico de Goiás.
    gdf = gdf.cx[-53.6:-45.3, -19.7:-12.1]
    no_envelope = len(gdf)
    gdf = gdf.head(LIMITE_FEICOES).copy()
    mask = gdf.geom_type.isin(["Polygon", "MultiPolygon", "LineString", "MultiLineString"])
    if mask.any():
        gdf.loc[mask, "geometry"] = gdf.loc[mask, "geometry"].simplify(
            0.005, preserve_topology=True
        )
    campos = [c for c in gdf.columns if c != "geometry"][:4]
    gdf = gdf[campos + ["geometry"]].copy()
    for coluna in campos:
        gdf[coluna] = gdf[coluna].astype(str).str.slice(0, 150)
    return json.loads(gdf.to_json()), campos, total, no_envelope, len(gdf)


@st.cache_data(ttl=86400, show_spinner=False)
def carregar_limite_goias():
    """Malha da UF Goiás (código IBGE 52) na API oficial do IBGE."""
    url = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/52"
    resposta = requests.get(
        url,
        params={"formato": "application/vnd.geo+json", "qualidade": "minima"},
        headers={"Accept": "application/vnd.geo+json", "User-Agent": "GeoGoiasDashboard/1.0"},
        timeout=20,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    if dados.get("type") not in (
        "FeatureCollection", "Feature", "Polygon", "MultiPolygon", "GeometryCollection"
    ):
        raise ValueError("A resposta do IBGE não contém uma geometria GeoJSON válida.")
    return dados


def mostrar_mapa_geologico():
    st.subheader("Mapas geocientíficos do SGB — Goiás")
    camadas = listar_camadas()
    if not camadas:
        st.warning("Nenhum SHP encontrado nas pastas de mapas da Base GeoGoiás.")
        return
    predefinido = []  # carregar somente após seleção do usuário
    selecao = st.multiselect(
        "Selecione até três camadas do SGB",
        list(camadas),
        default=predefinido,
        max_selections=3,
        key="camadas_sgb",
    )
    if not selecao:
        st.info("Exibindo o limite estadual. Selecione uma camada do SGB para sobrepor dados.")

    # OpenStreetMap substitui o CARTO Positron, que passou a exigir chave API.
    mapa = folium.Map(
        location=[-15.8, -49.3], zoom_start=6,
        tiles="OpenStreetMap", control_scale=True
    )
    try:
        limite = carregar_limite_goias()
        contorno = folium.GeoJson(
            limite,
            name="Limite estadual de Goiás — IBGE",
            style_function=lambda feature: {
                "color": "#B31E35", "weight": 3,
                "fillColor": "#F4C95D", "fillOpacity": 0.025,
                "dashArray": "7,4",
            },
            tooltip="Goiás — limite estadual (IBGE)",
        )
        contorno.add_to(mapa)
        mapa.fit_bounds(contorno.get_bounds(), padding=(14, 14))
    except Exception as erro_limite:
        st.warning(
            "O limite de Goiás não pôde ser consultado na API do IBGE "
            f"nesta execução: {erro_limite}"
        )
    resumo = []
    for i, caminho in enumerate(selecao):
        try:
            with st.spinner("Carregando " + Path(caminho).stem + "..."):
                dados, campos, total, envelope, exibidos = carregar_camada(caminho)
            if not dados["features"]:
                st.warning("Sem feições na área de consulta: " + caminho)
                continue
            cor = CORES[i % len(CORES)]
            parametros = {
                "name": Path(caminho).stem,
                "style_function": lambda f, c=cor: {
                    "color": c, "weight": 1.1, "fillColor": c,
                    "fillOpacity": 0.3, "radius": 4
                },
                "marker": folium.CircleMarker(
                    radius=3, color=cor, fill=True, fill_opacity=0.65
                ),
            }
            if campos:
                parametros["tooltip"] = folium.GeoJsonTooltip(
                    fields=campos, aliases=campos, sticky=False
                )
            folium.GeoJson(dados, **parametros).add_to(mapa)
            resumo.append({
                "camada": caminho, "total no arquivo": total,
                "no envelope": envelope, "exibidas": exibidos
            })
        except Exception as erro:
            st.error(f"Erro ao carregar {caminho}: {erro}")

    folium.LayerControl(collapsed=False).add_to(mapa)
    st_folium(
        mapa, height=620, width=None,
        returned_objects=[], key="mapa_sgb_geogoias"
    )
    if resumo:
        st.dataframe(resumo, hide_index=True, use_container_width=True)
    else:
        st.info("Nenhuma feição do SGB foi exibida; confira os arquivos e os avisos acima.")
    st.caption(
        "Limite estadual: IBGE (malhas geográficas, UF 52). "
        "Camadas temáticas: SGB/CPRM armazenadas na Base GeoGoiás. "
        "Máximo de 1.200 feições exibidas por camada; filtro geográfico "
        "aproximado por envelope, sem recorte exato ao polígono estadual. "
        "Cores ilustrativas, não simbologia geológica oficial."
    )
