# ================================
# Download
# ================================

# Selected property row
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
    "pct_black_bg": sel_row.get("pct_black_bg", ""),
    "pct_white_bg": sel_row.get("pct_white_bg", ""),
    "redfin_url": clean_url(sel_row.get("redfin_url", "")),
}])

# Matched properties
matched_download = pd.DataFrame()

for _, r in match_details.iterrows():
    matched_download = pd.concat([
        matched_download,
        pd.DataFrame([{
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
            "pct_black_bg": r.get("m_pct_black_bg", ""),
            "pct_white_bg": r.get("m_pct_white_bg", ""),
            "redfin_url": clean_url(r.get("m_redfin_url", "")),
        }])
    ], ignore_index=True)

# Combine selected property + matches
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