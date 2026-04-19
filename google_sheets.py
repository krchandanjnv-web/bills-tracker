"""
google_sheets.py  – Google Sheets backend for Bills Tracker
Sheets: Users | Data | Dues
"""

import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

USERS_COLS = ["Username", "PasswordHash", "Email", "CreatedAt"]
DATA_COLS  = ["Username", "Date", "Type", "Category", "Amount", "Description"]
DUES_COLS  = ["Username", "DueType", "Amount", "Description", "StartDate", "Status"]


class GoogleSheetsDB:

    def __init__(self):
        self.client      = self._connect()
        self.spreadsheet = self._open_spreadsheet()
        self._ensure_sheets()

    # ── Connection ─────────────────────────────────────────────────────────
    def _connect(self):
        creds = dict(st.secrets["gcp_service_account"])
        creds["scopes"] = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        return gspread.service_account_from_dict(creds)

    def _open_spreadsheet(self):
        url = st.secrets["spreadsheet"]["url"].strip()
        try:
            sheet_id = url.split("/spreadsheets/d/")[1].split("/")[0]
            return self.client.open_by_key(sheet_id)
        except Exception:
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

        if "Dues" not in existing:
            ws = self.spreadsheet.add_worksheet("Dues", rows=1000, cols=10)
            ws.append_row(DUES_COLS)
        else:
            ws = self.spreadsheet.worksheet("Dues")
            if ws.row_values(1) != DUES_COLS:
                ws.insert_row(DUES_COLS, 1)

    # ── Sheet accessors ────────────────────────────────────────────────────
    def _users_sheet(self):  return self.spreadsheet.worksheet("Users")
    def _data_sheet(self):   return self.spreadsheet.worksheet("Data")
    def _dues_sheet(self):   return self.spreadsheet.worksheet("Dues")

    def _users_df(self):
        r = self._users_sheet().get_all_records()
        return pd.DataFrame(r) if r else pd.DataFrame(columns=USERS_COLS)

    def _data_df(self):
        r = self._data_sheet().get_all_records()
        if not r:
            return pd.DataFrame(columns=DATA_COLS)
        df = pd.DataFrame(r)
        df["RowIndex"] = range(2, len(df) + 2)
        return df

    def _dues_df(self):
        r = self._dues_sheet().get_all_records()
        if not r:
            return pd.DataFrame(columns=DUES_COLS)
        df = pd.DataFrame(r)
        df["RowIndex"] = range(2, len(df) + 2)
        return df

    # ── User management ────────────────────────────────────────────────────
    def user_exists(self, username):
        df = self._users_df()
        if df.empty: return False
        return username.lower() in df["Username"].str.lower().values

    def add_user(self, username, password_hash, email=""):
        self._users_sheet().append_row(
            [username, password_hash, email, datetime.now().isoformat()])

    def verify_user(self, username, password_hash):
        df = self._users_df()
        if df.empty: return False
        return not df[(df["Username"].str.lower() == username.lower()) &
                      (df["PasswordHash"] == password_hash)].empty

    # ── Transaction management ─────────────────────────────────────────────
    def get_user_data(self, username):
        df = self._data_df()
        if df.empty: return df
        udf = df[df["Username"].str.lower() == username.lower()].copy()
        udf["Amount"] = pd.to_numeric(udf["Amount"], errors="coerce").fillna(0)
        return udf.reset_index(drop=True)

    def add_transaction(self, username, date, txn_type, category, amount, description=""):
        self._data_sheet().append_row(
            [username, date, txn_type, category, amount, description])

    def delete_row(self, username, row_index):
        if row_index < 2: return
        sheet = self._data_sheet()
        row_data = sheet.row_values(row_index)
        if row_data and row_data[0].lower() == username.lower():
            sheet.delete_rows(row_index)

    def update_row(self, username, row_index, date, txn_type, category, amount, description):
        if row_index < 2: return
        sheet = self._data_sheet()
        row_data = sheet.row_values(row_index)
        if row_data and row_data[0].lower() == username.lower():
            sheet.update(f"A{row_index}:F{row_index}",
                         [[username, date, txn_type, category, amount, description]])

    # ── Dues management ────────────────────────────────────────────────────
    def get_user_dues(self, username):
        df = self._dues_df()
        if df.empty: return df
        udf = df[df["Username"].str.lower() == username.lower()].copy()
        udf["Amount"] = pd.to_numeric(udf["Amount"], errors="coerce").fillna(0)
        return udf.reset_index(drop=True)

    def add_due(self, username, due_type, amount, description, start_date, status="Active"):
        self._dues_sheet().append_row(
            [username, due_type, amount, description, str(start_date), status])

    def update_due_status(self, username, row_index, new_status):
        if row_index < 2: return
        sheet = self._dues_sheet()
        row_data = sheet.row_values(row_index)
        if row_data and row_data[0].lower() == username.lower():
            sheet.update_cell(row_index, 6, new_status)

    def delete_due(self, username, row_index):
        if row_index < 2: return
        sheet = self._dues_sheet()
        row_data = sheet.row_values(row_index)
        if row_data and row_data[0].lower() == username.lower():
            sheet.delete_rows(row_index)
