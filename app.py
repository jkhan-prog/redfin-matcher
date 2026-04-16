import pandas as pd
import streamlit as st

ENRICHED = "enriched_pending.csv"
TOP = "top_matches.csv"

st.set_page_config(page_title="Redfin Pending Matcher", layout="wide")
st.title("Pending listings matcher (Redfin CSV → closest matches)")


def is_missing_value(x):
    if pd.isna(x):
        return True
    if isinstance(x, str):
        return x.strip().lower() in {"", "nan", "none", "null", "nat"}
    return False


def clean_url_value(x):
    if is_missing_value(x):
        return ""
    s = str(x).strip()
    return s if s.startswith("http") else ""


def find_url_column(df: pd.DataFrame):
    preferred = [
        "redfin_url",
        "url",
        "listing_url",
        "property_url",
        "details_url",
        "url_i",
        "url_j",
        "url_see_https_www_redfin_com_buy_a_home_comparative_market_analysis_for_info_on_pricing",
    ]

    for col in preferred:
        if col in df.columns:
            return col

    for col in df.columns:
        if "url" in str(col).lower():
            return col

    return None


@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_csv(ENRICHED)

    # Recreate home_id exactly the same way as the pipeline
    df = df.reset_index(drop=True).reset_index().rename(columns={"index": "home_id"})

    # Fix URL column
    url_col = find_url_column(df)
    if url_col is not None:
        df["redfin_url"] = df[url_col].apply(clean_url_value)
    else:
        df["redfin_url"] = ""

    top = pd.read_csv(TOP)

    needed_df_cols = {"home_id", "full_address"}
    needed_top_cols = {"home_i", "home_j", "similarity_pct"}

    if not needed_df_cols.issubset(set(df.columns)):
        raise ValueError(f"{ENRICHED} missing columns: {needed_df_cols - set(df.columns)}")
    if not needed_top_cols.issubset(set(top.columns)):
        raise ValueError(f"{TOP} missing columns: {needed_top_cols - set(top.columns)}")

    return df, top


try:
    df, top = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# Clean addresses for dropdown
df["full_address"] = df["full_address"].fillna("").astype(str).str.strip()
df_nonempty = df[df["full_address"] != ""].copy()

if df_nonempty.empty:
    st.warning("No non-empty full_address values found in enriched_pending.csv.")
    st.stop()

# Sidebar controls
st.sidebar.header("Controls")
batch_filter = st.sidebar.multiselect(
    "Filter matches by batch (optional)",
    options=sorted(df["batch"].dropna().unique().tolist()) if "batch" in df.columns else [],
    default=[]
)
min_similarity = st.sidebar.slider("Minimum similarity (%)", 0.0, 100.0, 0.0, 1.0)
top_n = st.sidebar.slider("Show top N matches", 1, 50, 10, 1)

# Address dropdown
addr = st.selectbox(
    "Select an address",
    options=df_nonempty["full_address"].tolist()
)

# Find selected row / id
sel_row = df_nonempty.loc[df_nonempty["full_address"] == addr].iloc[0]
sel_id = int(sel_row["home_id"])

# Selected listing details
st.subheader("Selected listing")
left, right = st.columns([2, 3])

with left:
    show_cols = [
        "full_address", "batch", "year_built", "sqft", "stories",
        "beds", "baths", "home_type", "parking",
        "bg_geoid", "pct_black_bg", "pct_white_bg"
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(sel_row[show_cols].to_frame("value"), use_container_width=True)

with right:
    url = clean_url_value(sel_row.get("redfin_url", ""))
    if url:
        st.markdown(f"**Redfin URL:** [Open Redfin listing]({url})")
    else:
        st.markdown("**Redfin URL:** (missing)")

st.subheader("Closest matches (sorted)")

# Pull matches for this home
matches = top[top["home_i"] == sel_id].copy()
if matches.empty:
    st.info("No matches found for this selection in top_matches.csv. (Did you generate top_matches.csv with the same enriched_pending.csv run?)")
    st.stop()

# Apply filters
matches = matches[matches["similarity_pct"] >= float(min_similarity)]

# Join match details
match_details = matches.merge(
    df.add_prefix("m_"),
    left_on="home_j",
    right_on="m_home_id",
    how="left"
)

# Optional batch filter
if batch_filter and "m_batch" in match_details.columns:
    match_details = match_details[match_details["m_batch"].isin(batch_filter)]

# Sort + limit
match_details = match_details.sort_values("similarity_pct", ascending=False).head(int(top_n))

# Pretty table
out_cols = [
    "similarity_pct",
    "m_full_address",
    "m_batch",
    "m_year_built",
    "m_sqft",
    "m_stories",
    "m_beds",
    "m_baths",
    "m_home_type",
    "m_pct_black_bg",
    "m_pct_white_bg",
    "m_redfin_url",
]
out_cols = [c for c in out_cols if c in match_details.columns]

table = match_details[out_cols].copy()
if "similarity_pct" in table.columns:
    table["similarity_pct"] = table["similarity_pct"].map(lambda x: round(float(x), 2))

table = table.replace({pd.NA: "", None: "", "None": "", "nan": ""})

if "m_redfin_url" in table.columns:
    table["m_redfin_url"] = table["m_redfin_url"].apply(clean_url_value)
    table["m_redfin_url"] = table["m_redfin_url"].apply(
        lambda x: f'<a href="{x}" target="_blank">Open Redfin</a>' if x else ""
    )

st.write(table.to_html(escape=False, index=False), unsafe_allow_html=True)

# Download CSV
download_table = match_details[out_cols].copy()
if "similarity_pct" in download_table.columns:
    download_table["similarity_pct"] = download_table["similarity_pct"].map(lambda x: round(float(x), 2))

st.download_button(
    "Download these matches as CSV",
    data=download_table.to_csv(index=False).encode("utf-8"),
    file_name=f"matches_for_{sel_id}.csv",
    mime="text/csv"
)