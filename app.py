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

    return ", ".join(parts).strip(", ")

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
    selected_cols = [
        "display_address", "batch", "year_built", "sqft", "lot_size",
        "stories", "beds", "baths", "home_type", "parking",
        "pct_black_bg", "pct_white_bg"
    ]
    selected_cols = [c for c in selected_cols if c in df.columns]
    st.dataframe(sel_row[selected_cols].to_frame("value"))

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
    match_details["m_display_address"] = match_details.get(
        "m_full_address", ""
    ).fillna("").astype(str).str.strip()

if batch_filter and "m_batch" in match_details.columns:
    match_details = match_details[match_details["m_batch"].isin(batch_filter)]

match_details = match_details.sort_values("similarity_pct", ascending=False).head(top_n)

# ================================
# Display matches table
# ================================
display_cols = [
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

display_cols = [c for c in display_cols if c in match_details.columns]

table = match_details[display_cols].copy()

if "similarity_pct" in table.columns:
    table["similarity_pct"] = table["similarity_pct"].round(2)

if "m_redfin_url" in table.columns:
    table["m_redfin_url"] = table["m_redfin_url"].apply(clean_url)
    table["m_redfin_url"] = table["m_redfin_url"].apply(
        lambda x: f'<a href="{x}" target="_blank">Open Redfin</a>' if x else ""
    )

st.write(table.to_html(escape=False, index=False), unsafe_allow_html=True)

# ================================
# Download selected property + matches
# ================================

selected_download = pd.DataFrame([{
    "property_role": "Selected Property",
    "similarity_pct": 100.00,
    "display_address": sel_row.get("display_address", ""),
    "batch": sel_row.get("batch", ""),
    "year_built": sel_row.get("year_built", ""),
    "sqft": sel_row.get("sqft", ""),
    "lot_size": sel_row.get("lot_size", ""),
    "stories": sel_row.get("stories", ""),
    "beds": sel_row.get("beds", ""),
    "baths": sel_row.get("baths", ""),
    "home_type": sel_row.get("home_type", ""),
    "parking": sel_row.get("parking", ""),
    "pct_black_bg": sel_row.get("pct_black_bg", ""),
    "pct_white_bg": sel_row.get("pct_white_bg", ""),
    "redfin_url": clean_url(sel_row.get("redfin_url", "")),
}])

matched_rows = []

for _, r in match_details.iterrows():
    matched_rows.append({
        "property_role": "Matched Property",
        "similarity_pct": round(r.get("similarity_pct", 0), 2),
        "display_address": r.get("m_display_address", ""),
        "batch": r.get("m_batch", ""),
        "year_built": r.get("m_year_built", ""),
        "sqft": r.get("m_sqft", ""),
        "lot_size": r.get("m_lot_size", ""),
        "stories": r.get("m_stories", ""),
        "beds": r.get("m_beds", ""),
        "baths": r.get("m_baths", ""),
        "home_type": r.get("m_home_type", ""),
        "parking": r.get("m_parking", ""),
        "pct_black_bg": r.get("m_pct_black_bg", ""),
        "pct_white_bg": r.get("m_pct_white_bg", ""),
        "redfin_url": clean_url(r.get("m_redfin_url", "")),
    })

matched_download = pd.DataFrame(matched_rows)

download_table = pd.concat(
    [selected_download, matched_download],
    ignore_index=True
)

st.download_button(
    "Download matches",
    data=download_table.to_csv(index=False).encode("utf-8"),
    file_name=f"matches_for_selected_property_{sel_id}.csv",
    mime="text/csv"
)