"""
google_sheets.py  –  Google Sheets backend for Bills Tracker
Fixed: uses gspread.service_account_from_dict() instead of deprecated gspread.authorize()
"""

import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

# ─── Column layouts ──────────────────────────────────────────────────────────
USERS_COLS = ["Username", "PasswordHash", "Email", "CreatedAt"]
DATA_COLS  = ["Username", "Date", "Type", "Category", "Amount", "Description"]


class GoogleSheetsDB:

    def __init__(self):
        self.client       = self._connect()
        self.spreadsheet  = self._open_spreadsheet()
        self._ensure_sheets()

    # ── Connection ─────────────────────────────────────────────────────────
    def _connect(self) -> gspread.Client:
        """
        Uses gspread.service_account_from_dict() — the correct modern API.
        """
        credentials_dict = dict(st.secrets["gcp_service_account"])
        credentials_dict["scopes"] = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        return gspread.service_account_from_dict(credentials_dict)

    def _open_spreadsheet(self) -> gspread.Spreadsheet:
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
    def _users_sheet(self):
        return self.spreadsheet.worksheet("Users")

    def _data_sheet(self):
        return self.spreadsheet.worksheet("Data")

    def _users_df(self):
        records = self._users_sheet().get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame(columns=USERS_COLS)

    def _data_df(self):
        records = self._data_sheet().get_all_records()
        if not records:
            return pd.DataFrame(columns=DATA_COLS)
        df = pd.DataFrame(records)
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
        df = self._data_df()
        if df.empty:
            return df
        user_df = df[df["Username"].str.lower() == username.lower()].copy()
        user_df["Amount"] = pd.to_numeric(user_df["Amount"], errors="coerce").fillna(0)
        return user_df.reset_index(drop=True)

    def add_transaction(self, username, date, txn_type, category, amount, description=""):
        self._data_sheet().append_row(
            [username, date, txn_type, category, amount, description]
        )

    def delete_row(self, username: str, row_index: int):
        if row_index < 2:
            return
        sheet = self._data_sheet()
        row_data = sheet.row_values(row_index)
        if row_data and row_data[0].lower() == username.lower():
            sheet.delete_rows(row_index)
