import streamlit as st
import requests
import pandas as pd
import time

API_URL = "https://person-counter-api-2.onrender.com/api/person-count"
REFRESH_SECONDS = 3  # <-- CHANGED (VERY IMPORTANT)
TIMEOUT = 20  # <-- FIX FOR RENDER SLEEP

# ================= PAGE CONFIG =================
st.set_page_config(
    page_title="SLAF ACCESS CONTROL",
    layout="wide",
)

# ================= SESSION RESET STORAGE =================
if "offset_totals" not in st.session_state:
    st.session_state.offset_totals = {}

if "reset_message" not in st.session_state:
    st.session_state.reset_message = ""

# ================= TITLE =================
st.markdown(
    "<h1 style='text-align:center;'> SLAF 75<sup>th</sup> Anniversary Exhibition Access Monitoring System</h1>",
    unsafe_allow_html=True
)

# ================= TOP CONTROL BAR =================
col_reset, col_info = st.columns([1, 5])

with col_reset:
    if st.button("🔄 RESET COUNTER", use_container_width=True):
        try:
            response = requests.get(API_URL, timeout=TIMEOUT)

            if response.status_code == 200:
                data = response.json()

                if isinstance(data, list) and len(data) > 0:
                    for row in data:
                        st.session_state.offset_totals[row["sensor_id"]] = row["total"]
                    st.session_state.reset_message = "success"
                else:
                    st.session_state.reset_message = "no_data"
            else:
                st.session_state.reset_message = "api_error"

        except requests.exceptions.Timeout:
            st.session_state.reset_message = "timeout"
        except:
            st.session_state.reset_message = "api_error"

with col_info:
    st.caption("Frontend Reset Only | Database Values Remain Safe")

# ================= RESET STATUS DISPLAY =================
if st.session_state.reset_message == "success":
    st.success("Counter Reset Successfully")
    st.session_state.reset_message = ""
elif st.session_state.reset_message == "no_data":
    st.warning("No sensor data available to reset")
    st.session_state.reset_message = ""
elif st.session_state.reset_message == "timeout":
    st.warning("Server waking up (Render cold start)... Please wait")
    st.session_state.reset_message = ""
elif st.session_state.reset_message == "api_error":
    st.warning("API temporarily unreachable")
    st.session_state.reset_message = ""

st.divider()

# ================= FETCH API DATA (STABLE) =================
try:
    response = requests.get(API_URL, timeout=TIMEOUT)

    if response.status_code == 200:
        data = response.json()

        if data:
            df = pd.DataFrame(data)

            # Format time safely
            if "last_seen" in df.columns:
                df["last_seen"] = pd.to_datetime(
                    df["last_seen"], errors="coerce"
                ).dt.strftime("%H:%M:%S")

            # Apply Reset Offset
            for i, row in df.iterrows():
                sid = row["sensor_id"]

                if sid not in st.session_state.offset_totals:
                    st.session_state.offset_totals[sid] = row["total"]

                df.at[i, "display_total"] = max(
                    0, int(row["total"]) - int(st.session_state.offset_totals[sid])
                )

            # KPIs
            grand_total = int(df["display_total"].sum())
            total_gates = len(df)
            online_gates = len(df[df["status"] == "ONLINE"])
            offline_gates = total_gates - online_gates

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("👥 TOTAL PERSONNEL", grand_total)
            k2.metric("🚪 TOTAL GATES", total_gates)
            k3.metric("🟢 ACTIVE GATES", online_gates)
            k4.metric("🔴 OFFLINE GATES", offline_gates)

            st.divider()
            st.markdown("### 🎯 GATE LIVE STATUS")

            cols = st.columns(4)

            for idx, row in df.iterrows():
                col = cols[idx % 4]
                with col:
                    status_color = "🟢" if row["status"] == "ONLINE" else "🔴"

                    st.markdown(
                        f"""
                        <div style="
                            border:2px solid #00FF00;
                            border-radius:10px;
                            padding:12px;
                            text-align:center;
                            background-color:#0b1a0b;
                            margin-bottom:10px;
                        ">
                            <h4>🚪 Gate {row['sensor_id']}</h4>
                            <h2 style="color:#00FF00;">{int(row['display_total'])}</h2>
                            <p>Persons Entered</p>
                            <h5>{status_color} {row['status']}</h5>
                            <small>Last Seen: {row['last_seen']}</small>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
        else:
            st.warning("No sensor data available.")

    else:
        st.warning("API returned non-200 response")

except requests.exceptions.Timeout:
    st.warning("⚠️ Server is waking up (Render Free Tier Cold Start)")
except Exception:
    st.warning("⚠️ Unable to connect to API (Network/API Issue)")

# ================= AUTO REFRESH =================
time.sleep(REFRESH_SECONDS)
st.rerun()
