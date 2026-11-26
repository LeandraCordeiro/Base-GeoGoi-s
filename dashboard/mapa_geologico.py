
import json
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium


def mostrar_mapa_geologico():
    st.subheader("Mapeamentos Geológicos do SGB — Goiás")

    caminho = (
        Path(__file__).resolve().parent.parent
        / "01_geologia"
        / "mapas_sgb"
        / "geologia_sgb_goias.geojson"
    )

    if not caminho.exists():
        st.warning(
            "Adicione o arquivo geologia_sgb_goias.geojson "
            "na pasta 01_geologia/mapas_sgb."
        )
        return

    with open(caminho, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    mapa = folium.Map(
        location=[-15.8, -49.3],
        zoom_start=6,
        tiles="CartoDB positron",
        control_scale=True,
    )

    feicoes = dados.get("features", [])

    campos = []
    if feicoes:
        propriedades = feicoes[0].get("properties") or {}
        campos = list(propriedades.keys())[:6]

    opcoes = {
        "name": "Geologia SGB",
        "style_function": lambda feature: {
            "fillColor": "#369AA8",
            "color": "#174E70",
            "weight": 0.6,
            "fillOpacity": 0.35,
        },
    }

    if campos:
        opcoes["tooltip"] = folium.GeoJsonTooltip(
            fields=campos,
            aliases=campos,
            localize=True,
        )

    folium.GeoJson(dados, **opcoes).add_to(mapa)

    folium.LayerControl().add_to(mapa)

    st_folium(
        mapa,
        width=None,
        height=650,
        returned_objects=[],
    )

    st.caption(
        "Fonte: SGB/CPRM. Visualização das camadas "
        "geológicas disponibilizadas na Base GeoGoiás."
    )
