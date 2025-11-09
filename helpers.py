from pathlib import Path
import pandas as pd
import requests
import json

def get_data_dir() -> Path:
    """Gibt den absoluten Pfad zum Datenordner zurück."""
    return (Path(__file__).parent / "data_webscraped").resolve()

def list_cities(data_dir: Path) -> list:
    """Gibt eine sortierte Liste der Städte (Unterordner) zurück."""
    return sorted([p.name for p in data_dir.iterdir() if p.is_dir()]) if data_dir.exists() else []

def load_and_clean_listings(listings_file: Path) -> pd.DataFrame | None:
    """Lädt listings.csv und bereinigt sie."""
    if not listings_file.exists():
        print(f"Datei nicht gefunden: {listings_file}")
        return None
    df = pd.read_csv(listings_file)
    used_columns = [
        "neighbourhood_group", "neighbourhood",
        "latitude", "longitude",
        "room_type", "price", "minimum_nights"
    ]
    df = df[[col for col in used_columns if col in df.columns]].copy()
    df_clean = df[~df['price'].isna()].copy()
    ng_col, n_col = "neighbourhood_group", "neighbourhood"
    df_clean[ng_col] = df_clean[ng_col].fillna(df_clean[n_col])
    
    return df_clean.reset_index(drop=True)

def load_and_clean_neighbourhoods(city_folder: Path) -> tuple[pd.DataFrame | None, dict | None]:
    """Lädt neighbourhoods.geojson und wandelt sie in ein DataFrame um."""
    geo_file = city_folder / "neighbourhoods.geojson"
    if not geo_file.exists():
        return None, None
    with open(geo_file, encoding="utf-8") as f:
        gj = json.load(f)
    df = pd.json_normalize(gj.get("features", []))
    ng_col, n_col = "properties.neighbourhood_group", "properties.neighbourhood"
    df_clean = df[~(df.get(ng_col).isna() & df.get(n_col).isna())].copy()
    df_clean[ng_col] = df_clean[ng_col].fillna(df_clean[n_col])
    return df_clean.reset_index(drop=True), gj

def compute_overview(df: pd.DataFrame) -> pd.DataFrame:
    """Preisstatistiken per Nacht."""
    return pd.DataFrame({
        "min_price": [df["price"].min()],
        "max_price": [df["price"].max()],
        "avg_price": [df["price"].mean()]
    })

def compute_room_type_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Berechnet Preisstatistiken nach Zimmertyp."""
    return df.groupby("room_type").agg(
        min_price=("price", "min"),
        max_price=("price", "max"),
        avg_price=("price", "mean"),
        count=("room_type", "count")
    ).reset_index()

def convert_prices_to_euro(df: pd.DataFrame, price_column: str = "price") -> pd.DataFrame:
    """Wandelt die Preisspalte eines DataFrames von USD in Euro um."""
    df_converted = df.copy()
    response = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR")
    data = response.json()
    usd_to_eur = data["rates"]["EUR"]
    df_converted[price_column] = (df_converted[price_column] * usd_to_eur).round(2)
    return df_converted

def de_format(x, decimals=2):
    """
    Formatiert eine Zahl ins deutsche Format: 
    1234567.89 -> 1.234.567,89
    """
    return f"{x:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")