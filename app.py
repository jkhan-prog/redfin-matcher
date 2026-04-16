import pandas as pd
import streamlit as st

st.set_page_config(page_title="Redfin Pending Matcher", layout="wide")
st.title("Pending listings matcher (Upload CSVs → get matches)")

# ================================
# Helpers
# ================================
def clean_url(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"", "nan", "none", "null"}:
        return ""
    return s

# ================================
# Upload files
# ================================
st.sidebar.header("Upload Files")

enriched_file = st.sidebar.file_uploader(
    "Upload enriched_pending.csv",
    type=["csv"]
)

top_file = st.sidebar.file_uploader(
    "Upload top_matches.csv",
    type=["csv"]
)

# ================================
# Load Data
# ================================
@st.cache_data(show_spinner=False)
def load_data(enriched_file, top_file):
    df = pd.read_csv(enriched_file)

    # Recreate home_id exactly like your pipeline
    df = df.reset_index(drop=True).reset_index().rename(columns={"index": "home_id"})

    top = pd.read_csv(top_file)

    # Validation
    needed_df_cols = {"home_id", "full_address"}
    needed_top_cols = {"home_i", "home_j", "similarity_pct"}

    if not needed_df_cols.issubset(df.columns):
        raise ValueError(f"Missing columns in enriched file: {needed_df_cols - set(df.columns)}")

    if not needed_top_cols.issubset(top.columns):
        raise ValueError(f"Missing columns in top file: {needed_top_cols - set(top.columns)}")

    return df, top

# Wait until both uploaded
if enriched_file is None or top_file is None:
    st.info("Upload both CSV files to continue.")
    st.stop()

try:
    df, top = load_data(enriched_file, top_file)
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.stop()

# ================================
# Clean addresses
# ================================
df["full_address"] = df["full_address"].fillna("").astype(str).str.strip()
df_nonempty = df[df["full_address"] != ""].copy()

if df_nonempty.empty:
    st.warning("No valid addresses found.")
    st.stop()

# ================================
# Sidebar filters
# ================================
st.sidebar.header("Controls")

batch_filter = st.sidebar.multiselect(
    "Filter by batch",
    options=sorted(df["batch"].dropna().unique().tolist()) if "batch" in df.columns else [],
    default=[]
)

min_similarity = st.sidebar.slider("Minimum similarity (%)", 0.0, 100.0, 0.0)
top_n = st.sidebar.slider("Top N matches", 1, 50, 10)

# ================================
# Select property
# ================================
addr = st.selectbox("Select an address", df_nonempty["full_address"])

sel_row = df_nonempty[df_nonempty["full_address"] == addr].iloc[0]
sel_id = int(sel_row["home_id"])

# ================================
# Show selected property
# ================================
st.subheader("Selected listing")

left, right = st.columns([2, 3])

with left:
    cols = [
        "full_address", "batch", "year_built", "sqft", "stories",
        "beds", "baths", "home_type", "parking",
        "pct_black_bg", "pct_white_bg"
    ]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(sel_row[cols].to_frame("value"))

with right:
    url = clean_url(sel_row.get("redfin_url", ""))
    if url:
        st.markdown(f"**Redfin URL:** [Open Redfin listing]({url})")
    else:
        st.markdown("**Redfin URL:** (missing)")

# ================================
# Matches
# ================================
st.subheader("Closest matches")

matches = top[top["home_i"] == sel_id].copy()

if matches.empty:
    st.warning("No matches found.")
    st.stop()

# Apply filters
matches = matches[matches["similarity_pct"] >= min_similarity]

match_details = matches.merge(
    df.add_prefix("m_"),
    left_on="home_j",
    right_on="m_home_id",
    how="left"
)

if batch_filter and "m_batch" in match_details.columns:
    match_details = match_details[match_details["m_batch"].isin(batch_filter)]

match_details = match_details.sort_values("similarity_pct", ascending=False).head(top_n)

# Display
cols = [
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
    "m_redfin_url"
]

cols = [c for c in cols if c in match_details.columns]

table = match_details[cols].copy()
table["similarity_pct"] = table["similarity_pct"].round(2)

# Make URL clickable
if "m_redfin_url" in table.columns:
    table["m_redfin_url"] = table["m_redfin_url"].apply(clean_url)
    table["m_redfin_url"] = table["m_redfin_url"].apply(
        lambda x: f'<a href="{x}" target="_blank">Open Redfin</a>' if x else ""
    )

st.write(table.to_html(escape=False, index=False), unsafe_allow_html=True)

# ================================
# Download
# ================================
download_table = match_details[cols].copy()
if "similarity_pct" in download_table.columns:
    download_table["similarity_pct"] = download_table["similarity_pct"].round(2)

st.download_button(
    "Download matches",
    data=download_table.to_csv(index=False).encode("utf-8"),
    file_name=f"matches_{sel_id}.csv"
)