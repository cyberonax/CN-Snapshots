import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

BASE_URL = "https://cybernations.lyricalz.com/nation/{nation_id}"

COLUMNS = [
    "Alliance", "Alliance Rank", "Gov", "Team", "Tech", "Infra", "Land", "Mode",
    "NS", "Defcon", "Soldiers", "Tanks", "Cruise", "Nukes",
    "Off. Casualties", "Def. Casualties", "Votes", "Resource1", "Resource2"
]

@st.cache_data(show_spinner=False)
def fetch_history_page(nation_id: str, page: int = 1) -> BeautifulSoup:
    """Fetch a single page of the nation history."""
    url = BASE_URL.format(nation_id=nation_id)
    params = {"page": page} if page > 1 else {}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def parse_table(soup: BeautifulSoup) -> pd.DataFrame:
    """Parse the history table into a DataFrame."""
    table = soup.find("table", {"class": "table-striped"})
    headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        rows.append(cols)
    return pd.DataFrame(rows, columns=headers)

def find_snapshot(df: pd.DataFrame, target_date: datetime) -> pd.Series | None:
    """Find the row closest to the given date (matching YYYY-MM-DD)."""
    # Convert "Last Updated" to datetime, then filter
    df["Last Updated"] = pd.to_datetime(df["Last Updated"], format="%Y-%m-%d %H:%M:%S")
    # exact-match by date
    matches = df[df["Last Updated"].dt.date == target_date.date()]
    if not matches.empty:
        return matches.iloc[0]
    return None

def get_snapshot(nation_id: str, snapshot_date: datetime, max_pages: int = 5) -> dict:
    """Loop through up to max_pages to find the snapshot row."""
    for page in range(1, max_pages+1):
        soup = fetch_history_page(nation_id, page)
        df = parse_table(soup)
        row = find_snapshot(df, snapshot_date)
        if row is not None:
            # extract only the fields we care about
            data = {col: row[col] for col in COLUMNS}
            return data
    return {col: None for col in COLUMNS}

def main():
    st.title("Cyber Nations: Nation Snapshot Comparator")

    st.sidebar.header("Snapshot Dates")
    date1 = st.sidebar.date_input("Date 1")
    date2 = st.sidebar.date_input("Date 2")

    st.markdown("**Enter one Nation ID per line:**")
    nation_input = st.text_area("", placeholder="e.g.\n527097\n561490", height=150)

    if st.button("Fetch & Compare"):
        nation_ids = [line.strip() for line in nation_input.splitlines() if line.strip()]
        if not nation_ids:
            st.error("Please enter at least one nation ID.")
            return

        results = []
        for nid in nation_ids:
            snap1 = get_snapshot(nid, datetime.combine(date1, datetime.min.time()))
            snap2 = get_snapshot(nid, datetime.combine(date2, datetime.min.time()))
            row = {"Nation ID": nid,
                   "Date 1": date1.isoformat(), **{f"{c} (D1)": snap1[c] for c in COLUMNS},
                   "Date 2": date2.isoformat(), **{f"{c} (D2)": snap2[c] for c in COLUMNS}}
            results.append(row)

        df = pd.DataFrame(results)
        st.dataframe(df)

        # Optionally allow CSV download
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="cn_snapshots.csv")

if __name__ == "__main__":
    main()
