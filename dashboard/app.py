import streamlit as st
import requests
from datetime import date, timedelta

st.set_page_config(page_title="CloudSentinel AI", page_icon="🛡️", layout="wide")
st.title("🛡️ CloudSentinel AI Dashboard")

# Date Range Picker
col1, col2 = st.columns(2)
with col1:
  start_date = st.date_input("Start Date", value=date.today() - timedelta(days=7))
with col2:
  end_date = st.date_input("End Date", value=date.today())

# Fetch Data Button
if st.button("Analyze Costs"):
  with st.spinner("The Sentinel is thinking..."):
    try:
      response = requests.get(
        "http://api:8000/analyze",
        params={
          "start_date": str(start_date),
          "end_date": str(end_date)
      },
      timeout=30  # Fail gracefully after 30 seconds instead of hanging indefinitely
    )
      if response.ok:
        data = response.json()
        st.success("Analysis Complete!")
        st.json(data["analysis"])
      else:
        st.error(f"API Error: {response.status_code}")
    except requests.exceptions.Timeout:
      st.error("The API request timed out. Please try again later.")
    except requests.exceptions.RequestException as e:
      st.error(f"Connection Error: {e}")