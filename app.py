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

def clean_text(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s

def make_physical_address(row, prefix=""):
    street = clean_text(row.get(f"{prefix}street", ""))
    city = clean_text(row.get(f"{prefix}city", ""))
    state = clean_text(row.get(f"{prefix}state", ""))
    zip_code = clean_text(row.get(f"{prefix}zip", ""))

    parts = []
    if street:
        parts.append(street)

    city_state_zip = ", ".join([x for x in [city, state] if x])
    if zip_code:
        if city_state_zip:
            city_state_zip = f"{city_state_zip} {zip_code}"
        else:
            city_state_zip = zip_code

    if city_state_zip:
        parts.append(city_state_zip)

    physical = ", ".join(parts).strip(", ")
    return physical

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

    needed_df_cols = {"home_id"}
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
# Build physical address
# ================================
if all(c in df.columns for c in ["street", "city", "state", "zip"]):
    df["display_address"] = df.apply(lambda r: make_physical_address(r), axis=1)
else:
    df["display_address"] = df.get("full_address", "").fillna("").astype(str).str.strip()

df_nonempty = df[df["display_address"] != ""].copy()

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
addr = st.selectbox("Select an address", df_nonempty["display_address"])

sel_row = df_nonempty[df_nonempty["display_address"] == addr].iloc[0]
sel_id = int(sel_row["home_id"])

# ================================
# Show selected property
# ================================
st.subheader("Selected listing")

left, right = st.columns([2, 3])

with left:
    cols = [
        "display_address", "batch", "year_built", "sqft", "lot_size",
        "stories", "beds", "baths", "home_type", "parking",
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

matches = matches[matches["similarity_pct"] >= min_similarity]

match_details = matches.merge(
    df.add_prefix("m_"),
    left_on="home_j",
    right_on="m_home_id",
    how="left"
)

# Build matched physical address
if all(c in match_details.columns for c in ["m_street", "m_city", "m_state", "m_zip"]):
    match_details["m_display_address"] = match_details.apply(
        lambda r: make_physical_address(r, prefix="m_"), axis=1
    )
else:
    match_details["m_display_address"] = match_details.get("m_full_address", "").fillna("").astype(str).str.strip()

if batch_filter and "m_batch" in match_details.columns:
    match_details = match_details[match_details["m_batch"].isin(batch_filter)]

match_details = match_details.sort_values("similarity_pct", ascending=False).head(top_n)

# Display
cols = [
    "similarity_pct",
    "m_display_address",
    "m_batch",
    "m_year_built",
    "m_sqft",
    "m_lot_size",
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