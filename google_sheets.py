"""
google_sheets.py  –  Google Sheets backend for Bills Tracker
Uses gspread + google-auth via a Service Account JSON key.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# ─── Scopes ──────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── Column layouts ──────────────────────────────────────────────────────────
USERS_COLS = ["Username", "PasswordHash", "Email", "CreatedAt"]
DATA_COLS  = ["Username", "Date", "Type", "Category", "Amount", "Description"]


class GoogleSheetsDB:
    """Thin wrapper around gspread for the Bills Tracker app."""

    def __init__(self):
        self.client = self._connect()
        self.spreadsheet = self._open_spreadsheet()
        self._ensure_sheets()

    # ── Connection ─────────────────────────────────────────────────────────
    def _connect(self) -> gspread.Client:
        """
        Reads credentials from st.secrets["gcp_service_account"].
        Add those secrets in Streamlit Cloud → Settings → Secrets.
        """
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES,
        )
        return gspread.authorize(creds)

    def _open_spreadsheet(self) -> gspread.Spreadsheet:
        """
        Opens the sheet by the URL stored in st.secrets["spreadsheet"]["url"].
        """
        url = st.secrets["spreadsheet"]["url"]
        return self.client.open_by_url(url)

    # ── Sheet bootstrapping ────────────────────────────────────────────────
    def _ensure_sheets(self):
        existing = [ws.title for ws in self.spreadsheet.worksheets()]

        if "Users" not in existing:
            ws = self.spreadsheet.add_worksheet("Users", rows=1000, cols=10)
            ws.append_row(USERS_COLS)
        else:
            ws = self.spreadsheet.worksheet("Users")
            if ws.row_values(1) != USERS_COLS:
                ws.insert_row(USERS_COLS, 1)

        if "Data" not in existing:
            ws = self.spreadsheet.add_worksheet("Data", rows=5000, cols=10)
            ws.append_row(DATA_COLS)
        else:
            ws = self.spreadsheet.worksheet("Data")
            if ws.row_values(1) != DATA_COLS:
                ws.insert_row(DATA_COLS, 1)

    # ── Helpers ────────────────────────────────────────────────────────────
    def _users_sheet(self) -> gspread.Worksheet:
        return self.spreadsheet.worksheet("Users")

    def _data_sheet(self) -> gspread.Worksheet:
        return self.spreadsheet.worksheet("Data")

    def _users_df(self) -> pd.DataFrame:
        records = self._users_sheet().get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame(columns=USERS_COLS)

    def _data_df(self) -> pd.DataFrame:
        records = self._data_sheet().get_all_records()
        if not records:
            return pd.DataFrame(columns=DATA_COLS)
        df = pd.DataFrame(records)
        # Attach 1-based row index (+1 for header row)
        df["RowIndex"] = range(2, len(df) + 2)
        return df

    # ── User management ────────────────────────────────────────────────────
    def user_exists(self, username: str) -> bool:
        df = self._users_df()
        if df.empty:
            return False
        return username.lower() in df["Username"].str.lower().values

    def add_user(self, username: str, password_hash: str, email: str = ""):
        self._users_sheet().append_row(
            [username, password_hash, email, datetime.now().isoformat()]
        )

    def verify_user(self, username: str, password_hash: str) -> bool:
        df = self._users_df()
        if df.empty:
            return False
        match = df[
            (df["Username"].str.lower() == username.lower()) &
            (df["PasswordHash"] == password_hash)
        ]
        return not match.empty

    # ── Transaction management ─────────────────────────────────────────────
    def get_user_data(self, username: str) -> pd.DataFrame:
        """Returns ALL transactions for the given user only."""
        df = self._data_df()
        if df.empty:
            return df
        user_df = df[df["Username"].str.lower() == username.lower()].copy()
        user_df["Amount"] = pd.to_numeric(user_df["Amount"], errors="coerce").fillna(0)
        return user_df.reset_index(drop=True)

    def add_transaction(
        self,
        username: str,
        date: str,
        txn_type: str,
        category: str,
        amount: float,
        description: str = "",
    ):
        self._data_sheet().append_row(
            [username, date, txn_type, category, amount, description]
        )

    def delete_row(self, username: str, row_index: int):
        """
        Deletes a specific row (1-based, including header) from the Data sheet.
        Verifies the row belongs to the requesting user before deletion.
        """
        if row_index < 2:
            return  # Never delete header
        sheet = self._data_sheet()
        row_data = sheet.row_values(row_index)
        # Safety check: ensure row belongs to the logged-in user
        if row_data and row_data[0].lower() == username.lower():
            sheet.delete_rows(row_index)
