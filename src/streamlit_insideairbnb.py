import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px
from pathlib import Path
import sys
import pandas as pd

current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from helpers import (
    get_data_dir, list_cities,
    load_and_clean_listings, load_and_clean_neighbourhoods,
    compute_overview, compute_room_type_stats, de_format, convert_prices_to_euro
)

data_dir = get_data_dir()
cities = list_cities(data_dir)

st.set_page_config(page_title="Städtevergleich", layout="wide")
st.sidebar.title("Städteauswahl")

placeholder = "Bitte wählen …"
selected_city_1 = st.sidebar.selectbox("Erste Stadt:", options=[placeholder]+cities, index=0, key="city_1")
use_second_city = st.sidebar.checkbox("Zweite Stadt auswählen", value=False)

selected_city_2 = None
if use_second_city:
    cities_2 = [c for c in cities if c != selected_city_1]
    previous = st.session_state.get("city_2", placeholder)
    index = 0 if previous not in cities_2 else cities_2.index(previous)+1
    selected_city_2 = st.sidebar.selectbox("Zweite Stadt:", options=[placeholder]+cities_2, index=index, key="city_2")

def load_city_data(city):
    if city == placeholder:
        return None, None, None, None
    folder = data_dir / city
    listings, msg = load_and_clean_listings(folder / "listings.csv")
    geo_df, geo_json = load_and_clean_neighbourhoods(folder)
    return listings, geo_df, geo_json, msg

city1_listings, city1_geo_df, city1_geojson, city1_msg = load_city_data(selected_city_1)
city2_listings, city2_geo_df, city2_geojson, city2_msg = load_city_data(selected_city_2) if selected_city_2 else (None, None, None, None)

use_euro = st.sidebar.checkbox("Preise in Euro anzeigen", value=True)
if use_euro:
    st.sidebar.info("Alle dargestellten Preise sind in EUR")
    if city1_listings is not None:
        city1_listings = convert_prices_to_euro(city1_listings)
    if city2_listings is not None:
        city2_listings = convert_prices_to_euro(city2_listings)
else :
    st.sidebar.info("Alle dargestellten Preise sind in USD")

tab_preise, tab_karte = st.tabs(["Preise", "Karte"])

with tab_preise:
    st.header("Preise")

    if city1_msg:
        st.warning(city1_msg)
    if city2_msg:
        st.warning(city2_msg)

    col1, col2 = st.columns(2)

    def filter_extreme_prices(df: pd.DataFrame, multiplier: float = 40) -> tuple[pd.DataFrame, float]:
        """Filtert extreme Ausreißer basierend auf IQR."""
        prices = df['price']
        Q1 = prices.quantile(0.25)
        Q3 = prices.quantile(0.75)
        IQR = Q3 - Q1
        upper_limit = Q3 + multiplier * IQR
        return df[df['price'] <= upper_limit].copy(), upper_limit

    def display_city_stats(listings, city_name):
        room_order = ["Entire home/apt", "Hotel room", "Private room", "Shared room"]
        overview = compute_overview(listings)
        room_stats = compute_room_type_stats(listings)
        st.subheader(city_name)
        if listings is not None:
            st.write(f"Bereinigter Datensatz: {listings.shape[0]} Unterkünfte, {listings.shape[1]} Kategorien")
        else:
            st.write("Keine Daten geladen.")
            
        st.markdown("### Überblick Preise/Nacht:")
        o = overview.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Niedrigster Wert", de_format(o['min_price']))
        c2.metric("Höchster Wert", de_format(o['max_price']))
        c3.metric("Durchschnitt", de_format(o['avg_price']))

        st.markdown("### a) Beschreibende Statistik – Preise nach Zimmertyp")
        desc = listings.groupby("room_type")["price"].describe().reset_index()
        number_cols = ['mean','std','min','25%','50%','75%','max']
        fmt = {col: de_format for col in number_cols}
        fmt['count'] = lambda x: f"{int(x):,}".replace(",", ".")
        st.dataframe(desc.style.format(fmt))

        filtered, upper_limit = filter_extreme_prices(listings)

        st.markdown("### b) Boxplot – Preisverteilung nach Zimmertyp")
        fig_box = px.box(
            filtered,
            x='room_type',
            y='price',
            color='room_type',
            category_orders={"room_type": room_order},
            labels={'room_type': 'Zimmertyp', 'price': 'Preis'},
            points='outliers'
        )
        st.plotly_chart(fig_box, use_container_width=True)

        st.markdown("### c) Häufigkeitsverteilung – Preise nach Zimmertyp")
        fig_hist = px.histogram(
            filtered,
            x="price",
            color="room_type",
            nbins=50,
            barmode="stack",
            category_orders={"room_type": room_order},
            labels={"room_type": "Zimmertyp", "price": "Preis", "count": "Anzahl"}
        )
        fig_hist.update_layout(
            xaxis_title="Preis",
            yaxis_title="Anzahl Unterkünfte",
            template="simple_white",
            bargap=0.05,
            legend_title="Zimmertyp",
            height=400
        )
        st.plotly_chart(fig_hist, use_container_width=True)
        st.caption(f"Hinweis: Extreme Ausreißer (Preise > {upper_limit:.2f}) wurden entfernt, "
                   "um die Darstellung der Preisverteilung zu verbessern.")

        return overview, room_stats

    with col1:
        if city1_listings is not None:
            display_city_stats(city1_listings, selected_city_1)
    with col2:
        if city2_listings is not None:
            display_city_stats(city2_listings, selected_city_2)

with tab_karte:
    st.header("Karte")

    show_heatmap = st.checkbox("Heatmap (Preise) anzeigen", value=False)

    def prepare_avg_tooltip(listings):
        """Tooltip-Text mit Kennzahlen pro Stadtteil vorbereiten"""
        if listings is None or listings.empty:
            return {}
        return {
            nb: (
                f"<b>{nb}</b><br>"
                f"Unterkünfte: {len(group)}<br>"
                f"⌀ Preis: {de_format(group['price'].mean())}<br>"
                f"⌀ Mindestnächte: {group['minimum_nights'].mean():.1f}<br>"
                f"Höchster Preis: {de_format(group['price'].max())}"
            )
            for nb, group in listings.groupby("neighbourhood")
        }

    def display_map(geojson, listings, city_name, color, geo_df):
        from folium.plugins import HeatMap
        m = folium.Map(tiles='OpenStreetMap')
        tooltips = prepare_avg_tooltip(listings)

        if tooltips:
            for feature in geojson["features"]:
                nb = feature["properties"].get("neighbourhood")
                if nb in tooltips:
                    feature["properties"]["tooltip"] = tooltips[nb]
                else:
                    feature["properties"]["tooltip"] = nb or "Unbekannt"
                    
            gj = folium.GeoJson(
                geojson,
                style_function=lambda x, c=color: {
                    "color": c,
                    "weight": 0.5,
                    "fillOpacity": 0.15
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["tooltip"],
                    aliases=[""],
                    sticky=True,
                    style="background-color: white; color: black; font-size: 13px; padding: 6px;"
                )
            ).add_to(m)
        else:
            gj = folium.GeoJson(
                geojson,
                style_function=lambda x, c=color: {
                    "color": c,
                    "weight": 0.5,
                    "fillOpacity": 0.15
                }
            ).add_to(m)
        m.fit_bounds(gj.get_bounds())

        if listings is not None and show_heatmap:
            heat_data = [
                [row['latitude'], row['longitude'], row['price']]
                for _, row in listings.iterrows()
                if not pd.isna(row['latitude']) and not pd.isna(row['longitude'])
            ]
            if heat_data:
                HeatMap(heat_data, radius=15, blur=15, max_zoom=12).add_to(m)

        st.subheader(city_name)
        if geo_df is not None:
            st.write(f"**GeoJSON als DataFrame:** {geo_df.shape[0]} Regionen, {geo_df.shape[1]} Kategorien")
        else:
            st.write("GeoJSON nicht geladen.")

        st_folium(m, width=700, height=400)
        
        if listings is not None and not listings.empty:
            count = len(listings)
            st.write(f"**Anzahl Unterkünfte {city_name}:** {count:,}".replace(",", "."))
            st.write(f"**⌀ Preis {city_name}:** {de_format(listings['price'].mean())}")
            st.write(f"**⌀ Mindestnächte {city_name}:** {listings['minimum_nights'].mean():.1f} Nächte")

            max_idx = listings['price'].idxmax()
            max_row = listings.loc[max_idx]
            max_price = max_row['price']
            max_region = max_row.get('neighbourhood')
            st.write(f"**Höchster Preis {city_name}:** {de_format(max_price)} ({max_region})")
        else:
            st.write("Keine Daten vorhanden.")

    col1, col2 = st.columns(2)
    with col1:
        if city1_geojson:
            display_map(city1_geojson, city1_listings, selected_city_1, "blue", city1_geo_df)
        else:
            st.write("Keine GeoJSON-Daten für die erste Stadt verfügbar.")
    with col2:
        if city2_geojson:
            display_map(city2_geojson, city2_listings, selected_city_2, "red", city2_geo_df)
        elif selected_city_2:
            st.write("Keine GeoJSON-Daten für die zweite Stadt verfügbar.")