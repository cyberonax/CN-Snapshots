import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

BASE_URL = "https://cybernations.lyricalz.com/nation/{nation_id}"

COLUMNS = [
    "Alliance", "Alliance Rank", "Gov", "Team", "Tech", "Infra", "Land", "Mode",
    "NS", "Defcon", "Soldiers", "Tanks", "Cruise", "Nukes",
    "Off. Casualties", "Def. Casualties", "Votes", "Resource1", "Resource2"
]

@st.cache_data(show_spinner=False)
def fetch_history_page(nation_id: str, page: int = 1) -> BeautifulSoup:
    """Fetch a single page of the nation history (raises on HTTP errors)."""
    url = BASE_URL.format(nation_id=nation_id)
    params = {"page": page} if page > 1 else {}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def parse_table(soup: BeautifulSoup) -> pd.DataFrame:
    table = soup.find("table", {"class": "table-striped"})
    if not table:
        return pd.DataFrame()
    headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
    rows = [[td.get_text(strip=True) for td in tr.find_all("td")]
            for tr in table.find("tbody").find_all("tr")]
    return pd.DataFrame(rows, columns=headers)

def find_snapshot(df: pd.DataFrame, target_date: datetime) -> pd.Series | None:
    df["Last Updated"] = pd.to_datetime(df["Last Updated"], format="%Y-%m-%d %H:%M:%S")
    matches = df[df["Last Updated"].dt.date == target_date.date()]
    return matches.iloc[0] if not matches.empty else None

def get_snapshot(nation_id: str, snapshot_date: datetime) -> dict:
    page = 1
    while True:
        try:
            soup = fetch_history_page(nation_id, page)
        except requests.exceptions.HTTPError:
            break
        df = parse_table(soup)
        if df.empty:
            break
        row = find_snapshot(df, snapshot_date)
        if row is not None:
            return {col: row[col] for col in COLUMNS}
        page += 1
    return {col: None for col in COLUMNS}

def main():
    st.title("Cyber Nations | Nation Snapshot Comparator")

    st.sidebar.header("Snapshot Dates")
    date1 = st.sidebar.date_input("Date 1")
    date2 = st.sidebar.date_input("Date 2")

    st.markdown("**Enter one Nation ID per line:**")
    nation_input = st.text_area("", placeholder="e.g.\n527097\n561490", height=150)

    if st.button("Fetch & Compare"):
        with st.spinner("Loading data..."):
            raw_ids = [line.strip() for line in nation_input.splitlines() if line.strip()]
            valid_ids, invalid_ids = [], []
            for nid in raw_ids:
                if nid.isdigit():
                    valid_ids.append(nid)
                else:
                    invalid_ids.append(nid)

            if invalid_ids:
                st.warning(f"Ignoring invalid IDs (must be numeric): {', '.join(invalid_ids)}")

            if not valid_ids:
                st.error("No valid nation IDs to fetch.")
                return

            results = []
            for nid in valid_ids:
                # Fetch first page to get ruler name from <title>
                page1 = fetch_history_page(nid, 1)
                title_text = page1.title.get_text(strip=True) if page1.title else ""
                ruler_name = title_text.replace("Nation data for ", "").split(" |")[0]

                # Get snapshots across all pages until found
                snap1 = get_snapshot(nid, datetime.combine(date1, datetime.min.time()))
                snap2 = get_snapshot(nid, datetime.combine(date2, datetime.min.time()))

                row = {
                    "Nation ID": nid,
                    "Ruler Name": ruler_name,
                    "Date 1": date1.isoformat(),
                    **{f"{c} (D1)": snap1[c] for c in COLUMNS},
                    "Date 2": date2.isoformat(),
                    **{f"{c} (D2)": snap2[c] for c in COLUMNS}
                }
                results.append(row)

            df = pd.DataFrame(results)
            df = df.sort_values("Ruler Name").reset_index(drop=True)

            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", data=csv, file_name="cn_snapshots.csv")

if __name__ == "__main__":
    main()
