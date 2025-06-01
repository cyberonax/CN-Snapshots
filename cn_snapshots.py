import streamlit as st
import requests
from requests.exceptions import ReadTimeout, HTTPError
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import zipfile
import io

st.set_page_config(layout="wide")

BASE_URL = "https://cybernations.lyricalz.com/nation/{nation_id}"

COLUMNS = [
    "Alliance", "Alliance Rank", "Gov", "Team", "Tech", "Infra", "Land", "Mode",
    "NS", "Defcon", "Soldiers", "Tanks", "Cruise", "Nukes",
    "Off. Casualties", "Def. Casualties", "Votes", "Resource1", "Resource2"
]

# -----------------------
# DOWNLOAD & DATA LOADING FUNCTIONS
# -----------------------
def download_and_extract_zip(url):
    """Download a zip file from the given URL and extract its first file as a DataFrame."""
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            file_list = z.namelist()
            if not file_list:
                return None
            file_name = file_list[0]
            with z.open(file_name) as file:
                # Adjust delimiter and encoding as needed
                df = pd.read_csv(file, delimiter="|", encoding="ISO-8859-1")
                return df
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def load_data():
    """Try downloading data using a list of dates and URL patterns without showing debug messages."""
    today = datetime.now()
    base_url = "https://www.cybernations.net/assets/CyberNations_SE_Nation_Stats_"
    dates_to_try = [today, today - timedelta(days=1), today + timedelta(days=1)]
    
    for dt in dates_to_try:
        # date_str is used for constructing the ZIP filename (e.g. "5312025")
        date_str = f"{dt.month}{dt.day}{dt.year}"
        url1 = base_url + date_str + "510001.zip"
        url2 = base_url + date_str + "510002.zip"
        
        df = download_and_extract_zip(url1)
        if df is None:
            df = download_and_extract_zip(url2)
        if df is not None:
            # display_date is used purely for formatting the success message (e.g. "5/31/2025")
            display_date = f"{dt.month}/{dt.day}/{dt.year}"
            st.success(f"Alliance data loaded successfully from date: {display_date}")
            return df

    return None

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

def get_snapshot(nation_id: str, snapshot_date: datetime, max_pages: int = 20) -> dict:
    """Attempt to find the snapshot by iterating pages up to max_pages."""
    for page in range(1, max_pages + 1):
        try:
            soup = fetch_history_page(nation_id, page)
        except (HTTPError, ReadTimeout):
            # stop on HTTP or timeout errors
            break
        df = parse_table(soup)
        if df.empty:
            break
        row = find_snapshot(df, snapshot_date)
        if row is not None:
            return {col: row[col] for col in COLUMNS}
    # not found within max_pages
    return {col: None for col in COLUMNS}

def main():
    st.title("Cyber Nations | Nation Snapshot Comparator")
    
    # -----------------------
    # Load current alliance data and set up dropdown
    # -----------------------
    with st.spinner("Loading alliance data..."):
        df_alliances = load_data()
    if df_alliances is None or "Alliance" not in df_alliances.columns or "Nation ID" not in df_alliances.columns:
        st.sidebar.error("Failed to load alliance data. Dropdown will default to Freehold of The Wolves.")
        alliances = ["Freehold of The Wolves"]
        default_index = 0
        member_ids = []
    else:
        # Get list of unique alliances
        alliances = sorted(df_alliances["Alliance"].dropna().unique())
        # Determine default index for "Freehold of The Wolves"
        default_index = alliances.index("Freehold of The Wolves") if "Freehold of The Wolves" in alliances else 0
        # Initial member IDs for default alliance
        default_alliance = alliances[default_index]
        member_ids = df_alliances[df_alliances["Alliance"] == default_alliance]["Nation ID"].astype(str).tolist()

    st.sidebar.header("Alliance Selection")
    selected_alliance = st.sidebar.selectbox(
        "Select Alliance",
        alliances,
        index=default_index
    )
    # Update member IDs when a different alliance is selected
    if df_alliances is not None and "Alliance" in df_alliances.columns and "Nation ID" in df_alliances.columns:
        member_ids = df_alliances[df_alliances["Alliance"] == selected_alliance]["Nation ID"].astype(str).tolist()
    default_input = "\n".join(member_ids)

    # -----------------------
    # Snapshot date inputs
    # -----------------------
    st.sidebar.header("Snapshot Dates")
    date1 = st.sidebar.date_input("Date 1")
    date2 = st.sidebar.date_input("Date 2")

    st.markdown("**Enter one Nation ID per line:**")
    nation_input = st.text_area(
        "",
        value=default_input,
        height=150
    )

    if st.button("Fetch & Compare"):
        with st.spinner("Loading data (this may take a moment for older snapshots)..."):
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

            # -----------------------
            # Build the snapshots table
            # -----------------------
            results = []
            for nid in valid_ids:
                # Fetch first page to get ruler name from <title>
                try:
                    page1 = fetch_history_page(nid, 1)
                    title_text = page1.title.get_text(strip=True) if page1.title else ""
                    ruler_name = title_text.replace("Nation data for ", "").split(" |")[0]
                except (HTTPError, ReadTimeout):
                    ruler_name = None

                # Get snapshots across pages
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

            df_snapshots = pd.DataFrame(results)
            df_snapshots = df_snapshots.sort_values("Ruler Name").reset_index(drop=True)

            # -----------------------
            # Build the differences table
            # -----------------------
            diff_rows = []
            for _, row in df_snapshots.iterrows():
                nid = row["Nation ID"]
                ruler = row["Ruler Name"]
                # Helper to safely convert to int (or 0 if None/empty)
                def to_int(val):
                    try:
                        return int(val)
                    except Exception:
                        return 0

                # Compute differences for each metric
                tech_d1 = to_int(row["Tech (D1)"])
                tech_d2 = to_int(row["Tech (D2)"])
                infra_d1 = to_int(row["Infra (D1)"])
                infra_d2 = to_int(row["Infra (D2)"])
                land_d1 = to_int(row["Land (D1)"])
                land_d2 = to_int(row["Land (D2)"])
                ns_d1 = to_int(row["NS (D1)"])
                ns_d2 = to_int(row["NS (D2)"])
                nukes_d1 = to_int(row["Nukes (D1)"])
                nukes_d2 = to_int(row["Nukes (D2)"])
                offc_d1 = to_int(row["Off. Casualties (D1)"])
                offc_d2 = to_int(row["Off. Casualties (D2)"])
                defc_d1 = to_int(row["Def. Casualties (D1)"])
                defc_d2 = to_int(row["Def. Casualties (D2)"])

                # Calculate net changes
                tech_diff = tech_d2 - tech_d1
                infra_diff = infra_d2 - infra_d1
                land_diff = land_d2 - land_d1
                ns_diff = ns_d2 - ns_d1
                nukes_diff = nukes_d2 - nukes_d1
                offc_diff = offc_d2 - offc_d1
                defc_diff = defc_d2 - defc_d1

                diff_rows.append({
                    "Nation ID": nid,
                    "Ruler Name": ruler,
                    "Date 1": row["Date 1"],
                    "Date 2": row["Date 2"],
                    "Net Tech Gain": tech_diff if tech_diff > 0 else 0,
                    "Net Tech Loss": tech_diff if tech_diff < 0 else 0,
                    "Net Infra Gain": infra_diff if infra_diff > 0 else 0,
                    "Net Infra Loss": infra_diff if infra_diff < 0 else 0,
                    "Net Land Gain": land_diff if land_diff > 0 else 0,
                    "Net Land Loss": land_diff if land_diff < 0 else 0,
                    "Net NS Gain": ns_diff if ns_diff > 0 else 0,
                    "Net NS Loss": ns_diff if ns_diff < 0 else 0,
                    "Net Nukes Gain": nukes_diff if nukes_diff > 0 else 0,
                    "Net Nukes Loss": nukes_diff if nukes_diff < 0 else 0,
                    "Net Off. Casualties": offc_diff,
                    "Net Def. Casualties": defc_diff
                })

            df_diffs = pd.DataFrame(diff_rows).sort_values("Ruler Name").reset_index(drop=True)

            # -----------------------
            # Show tables in separate collapsible sections
            # -----------------------
            with st.expander("Snapshot Comparison"):
                st.dataframe(df_snapshots, use_container_width=True)

            with st.expander("Net Changes (Date 2 minus Date 1)"):
                st.dataframe(df_diffs, use_container_width=True)

            # -----------------------
            # Download as XLSX with two sheets (using openpyxl)
            # -----------------------
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_snapshots.to_excel(writer, sheet_name="Snapshots", index=False)
                df_diffs.to_excel(writer, sheet_name="Differences", index=False)
                writer.save()
            processed_data = output.getvalue()

            st.download_button(
                label="Download XLSX",
                data=processed_data,
                file_name="cn_snapshots_and_diffs.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main()
