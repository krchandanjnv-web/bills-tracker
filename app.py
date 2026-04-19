import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import hashlib
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER
from google_sheets import GoogleSheetsDB

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="💰 Personal Bills Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.main { background: #0f1117; }
.block-container { padding: 1.5rem 2rem; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1d2e 0%, #0f1117 100%);
    border-right: 1px solid rgba(255,255,255,0.06);
}
.kpi-card {
    background: linear-gradient(135deg, #1a1d2e 0%, #16192a 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 1.5rem; text-align: center;
    position: relative; overflow: hidden; transition: transform 0.2s;
}
.kpi-card:hover { transform: translateY(-2px); }
.kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
.kpi-income::before  { background: linear-gradient(90deg, #00b894, #00cec9); }
.kpi-expense::before { background: linear-gradient(90deg, #d63031, #e17055); }
.kpi-balance::before { background: linear-gradient(90deg, #6c5ce7, #a29bfe); }
.kpi-label { font-size:0.78rem; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:#718096; margin-bottom:0.5rem; }
.kpi-value { font-family:'Space Grotesk',sans-serif; font-size:2rem; font-weight:700; line-height:1.1; }
.kpi-income .kpi-value  { color:#00b894; }
.kpi-expense .kpi-value { color:#ff6b6b; }
.kpi-balance .kpi-value { color:#a29bfe; }
.kpi-sub { font-size:0.72rem; color:#4a5568; margin-top:0.3rem; }
.section-header {
    font-family:'Space Grotesk',sans-serif; font-size:1.1rem; font-weight:600;
    color:#e2e8f0; margin:1.5rem 0 1rem 0; padding-bottom:0.5rem;
    border-bottom:1px solid rgba(255,255,255,0.06);
}
.brand {
    font-family:'Space Grotesk',sans-serif; font-size:1.4rem; font-weight:700;
    background:linear-gradient(135deg,#00b894,#a29bfe);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:0.2rem;
}
.brand-sub { font-size:0.75rem; color:#4a5568; margin-bottom:1.5rem; }
[data-testid="stMetric"] { background:transparent !important; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
INCOME_CATEGORIES  = ["Bhaiya", "Loan", "Cashback", "Salary", "MCM", "Redeem", "➕ Custom"]
EXPENSE_CATEGORIES = ["Shopping", "Utilities", "Ticket Booking", "Mess Bill",
                       "Loan Repayment", "Invest", "Entertainment", "Travel", "Other", "➕ Custom"]
INCOME_COLORS  = ["#00b894","#00cec9","#55efc4","#81ecec","#74b9ff","#a29bfe","#fd79a8"]
EXPENSE_COLORS = ["#d63031","#e17055","#fdcb6e","#fd79a8","#e84393","#6c5ce7","#b2bec3","#0984e3","#00b894","#55efc4"]
DASH_FILTERS   = ["Last 7 Days", "This Month", "This Year", "All Transactions"]

# ─── Helpers ─────────────────────────────────────────────────────────────────
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def fmt_inr(amount):
    if abs(amount) >= 1_00_000: return f"₹{amount/1_00_000:.1f}L"
    if abs(amount) >= 1_000:    return f"₹{amount:,.0f}"
    return f"₹{amount:.0f}"

def apply_date_filter(df, label):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    now = pd.Timestamp.now()
    if label == "Last 7 Days":      return df[df["Date"] >= now - timedelta(days=7)]
    elif label == "This Month":     return df[(df["Date"].dt.month == now.month) & (df["Date"].dt.year == now.year)]
    elif label == "This Year":      return df[df["Date"].dt.year == now.year]
    return df

# ─── Session State ────────────────────────────────────────────────────────────
for k, v in {"logged_in": False, "username": "", "dash_filter": "This Month", "editing_row": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── DB ───────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return GoogleSheetsDB()

db = get_db()

# ─── PDF Generator ────────────────────────────────────────────────────────────
def generate_pdf(df, username):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    elements = []

    title_style = ParagraphStyle("t", fontSize=18, fontName="Helvetica-Bold",
                                  textColor=colors.HexColor("#00b894"), alignment=TA_CENTER, spaceAfter=4)
    sub_style   = ParagraphStyle("s", fontSize=9,  fontName="Helvetica",
                                  textColor=colors.HexColor("#718096"), alignment=TA_CENTER, spaceAfter=16)
    head_style  = ParagraphStyle("h", fontSize=11, fontName="Helvetica-Bold",
                                  textColor=colors.HexColor("#e2e8f0"), spaceAfter=4)

    elements.append(Paragraph("Personal Bills Tracker - Transaction Report", title_style))
    elements.append(Paragraph(
        f"User: {username}  |  Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}  |  Total Records: {len(df)}",
        sub_style))

    # Summary
    total_income  = df[df["Type"]=="Income"]["Amount"].sum()
    total_expense = df[df["Type"]=="Expense"]["Amount"].sum()
    net           = total_income - total_expense
    summary = [
        ["Total Income", "Total Expense", "Net Balance"],
        [f"Rs {total_income:,.2f}", f"Rs {total_expense:,.2f}", f"Rs {net:,.2f}"]
    ]
    st_table = Table(summary, colWidths=[57*mm, 57*mm, 57*mm])
    st_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), colors.HexColor("#1a1d2e")),
        ("TEXTCOLOR",    (0,0),(-1,0), colors.HexColor("#a0aec0")),
        ("BACKGROUND",   (0,1),(0,1),  colors.HexColor("#00b894")),
        ("BACKGROUND",   (1,1),(1,1),  colors.HexColor("#d63031")),
        ("BACKGROUND",   (2,1),(2,1),  colors.HexColor("#6c5ce7") if net >= 0 else colors.HexColor("#d63031")),
        ("TEXTCOLOR",    (0,1),(-1,1), colors.white),
        ("FONTNAME",     (0,0),(-1,-1),"Helvetica-Bold"),
        ("FONTSIZE",     (0,0),(-1,0), 8),
        ("FONTSIZE",     (0,1),(-1,1), 13),
        ("ALIGN",        (0,0),(-1,-1),"CENTER"),
        ("VALIGN",       (0,0),(-1,-1),"MIDDLE"),
        ("GRID",         (0,0),(-1,-1), 0.5, colors.HexColor("#2d3748")),
        ("TOPPADDING",   (0,0),(-1,-1), 7),
        ("BOTTOMPADDING",(0,0),(-1,-1), 7),
    ]))
    elements.append(st_table)
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph("Transaction Details", head_style))

    # Transactions table
    headers = ["Date", "Type", "Category", "Amount (Rs)", "Description"]
    rows    = [headers]
    for _, row in df.sort_values("Date", ascending=False).iterrows():
        rows.append([
            str(row["Date"])[:10],
            str(row["Type"]),
            str(row["Category"]),
            f"{float(row['Amount']):,.2f}",
            str(row.get("Description",""))[:45],
        ])

    txn_table = Table(rows, colWidths=[25*mm, 22*mm, 32*mm, 28*mm, 64*mm], repeatRows=1)
    row_styles = []
    for i, row in enumerate(rows[1:], 1):
        bg = colors.HexColor("#0d2818") if row[1]=="Income" else colors.HexColor("#1f0a0a")
        row_styles.append(("BACKGROUND",(0,i),(-1,i), bg))
    txn_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  colors.HexColor("#1a1d2e")),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.HexColor("#a0aec0")),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),  8),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1),(-1,-1), 7.5),
        ("TEXTCOLOR",     (0,1),(-1,-1), colors.HexColor("#e2e8f0")),
        ("ALIGN",         (3,0),(3,-1),  "RIGHT"),
        ("ALIGN",         (0,0),(2,-1),  "LEFT"),
        ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor("#2d3748")),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
    ] + row_styles))
    elements.append(txn_table)
    doc.build(elements)
    return buf.getvalue()

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════
def show_auth():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-top:2rem;margin-bottom:2rem;">
            <div style="font-size:3rem;margin-bottom:0.5rem;">💰</div>
            <div style="font-family:'Space Grotesk',sans-serif;font-size:1.8rem;font-weight:700;
                        background:linear-gradient(135deg,#00b894,#a29bfe);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;">Bills Tracker</div>
            <div style="color:#718096;font-size:0.85rem;margin-top:0.3rem;">Your personal finance dashboard</div>
        </div>""", unsafe_allow_html=True)

        tab_login, tab_signup = st.tabs(["🔑 Login", "✨ Sign Up"])
        with tab_login:
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login →", use_container_width=True, type="primary"):
                if username and password:
                    if db.verify_user(username, hash_password(password)):
                        st.session_state.logged_in = True
                        st.session_state.username  = username
                        st.rerun()
                    else:
                        st.error("❌ Invalid credentials.")
                else:
                    st.warning("Please fill in all fields.")

        with tab_signup:
            new_user  = st.text_input("Username", key="su_user")
            new_email = st.text_input("Email (optional)", key="su_email")
            new_pass  = st.text_input("Password", type="password", key="su_pass")
            new_pass2 = st.text_input("Confirm Password", type="password", key="su_pass2")
            if st.button("Create Account →", use_container_width=True, type="primary"):
                if new_user and new_pass:
                    if new_pass != new_pass2:      st.error("Passwords don't match!")
                    elif len(new_pass) < 6:        st.warning("Min 6 characters.")
                    elif db.user_exists(new_user): st.error("Username already taken.")
                    else:
                        db.add_user(new_user, hash_password(new_pass), new_email)
                        st.success("✅ Account created! Please login.")
                else:
                    st.warning("Username and password are required.")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
def show_sidebar():
    with st.sidebar:
        st.markdown(f"""
        <div class="brand">💰 Bills Tracker</div>
        <div class="brand-sub">Personal Finance Dashboard</div>
        <div style="background:rgba(255,255,255,0.04);border-radius:10px;
                    padding:0.6rem 1rem;margin-bottom:1.5rem;font-size:0.82rem;color:#a0aec0;">
            👤 <b style="color:#e2e8f0">{st.session_state.username}</b>
        </div>""", unsafe_allow_html=True)
        page = st.radio("Nav", ["📊 Dashboard","➕ Add Transaction","📋 History"],
                        label_visibility="collapsed")
        st.markdown(f'<div style="font-size:0.72rem;color:#4a5568;text-align:center;padding:0.5rem;margin-top:2rem;">📅 {datetime.now().strftime("%B %Y")}</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username  = ""
            st.rerun()
    return page

# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def show_dashboard():
    df_all = db.get_user_data(st.session_state.username)

    # Header + filter dropdown top-right
    hcol, fcol = st.columns([3, 1])
    with hcol:
        st.markdown("""
        <div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">📊 Dashboard</div>
        <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Personal Finance Overview</div>
        """, unsafe_allow_html=True)
    with fcol:
        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
        chosen = st.selectbox("", DASH_FILTERS,
                              index=DASH_FILTERS.index(st.session_state.dash_filter),
                              key="dash_filter_sel", label_visibility="collapsed")
        st.session_state.dash_filter = chosen

    if df_all.empty:
        st.info("🌱 No transactions yet! Add your first transaction.", icon="💡")
        return

    df = apply_date_filter(df_all, chosen)
    if df.empty:
        st.info(f"No transactions found for: **{chosen}**")
        return

    total_income  = df[df["Type"]=="Income"]["Amount"].sum()
    total_expense = df[df["Type"]=="Expense"]["Amount"].sum()
    net_balance   = total_income - total_expense
    period_label  = {"Last 7 Days":"Last 7 days","This Month":datetime.now().strftime("%B %Y"),
                     "This Year":str(datetime.now().year),"All Transactions":"All time"}[chosen]

    # KPI Cards
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="kpi-card kpi-income"><div class="kpi-label">💚 Total Income</div><div class="kpi-value">{fmt_inr(total_income)}</div><div class="kpi-sub">{period_label}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="kpi-card kpi-expense"><div class="kpi-label">❤️ Total Expense</div><div class="kpi-value">{fmt_inr(total_expense)}</div><div class="kpi-sub">{period_label}</div></div>', unsafe_allow_html=True)
    with c3:
        bc = "#a29bfe" if net_balance >= 0 else "#ff6b6b"
        em = "✨" if net_balance >= 0 else "⚠️"
        st.markdown(f'<div class="kpi-card kpi-balance"><div class="kpi-label">{em} Net Balance</div><div class="kpi-value" style="color:{bc}">{fmt_inr(net_balance)}</div><div class="kpi-sub">{"Surplus" if net_balance>=0 else "Deficit"} · {period_label}</div></div>', unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # Donut charts
    CHART_BG  = "rgba(0,0,0,0)"
    col_l, col_r = st.columns(2)
    income_df  = df[df["Type"]=="Income"].groupby("Category")["Amount"].sum()
    expense_df = df[df["Type"]=="Expense"].groupby("Category")["Amount"].sum()

    with col_l:
        st.markdown('<div class="section-header">💚 Income Breakdown</div>', unsafe_allow_html=True)
        if not income_df.empty:
            fig = go.Figure(go.Pie(labels=income_df.index, values=income_df.values, hole=0.62,
                marker=dict(colors=INCOME_COLORS[:len(income_df)], line=dict(color='#0f1117',width=2)),
                textinfo="label+percent", textfont=dict(size=11,color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"))
            fig.update_layout(paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                margin=dict(l=10,r=10,t=10,b=10), height=280, showlegend=True,
                legend=dict(font=dict(color="#a0aec0",size=10),bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(text=f"<b>{fmt_inr(total_income)}</b>",x=0.5,y=0.5,font_size=15,font_color="#00b894",showarrow=False)])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No income for this period.")

    with col_r:
        st.markdown('<div class="section-header">❤️ Expense Breakdown</div>', unsafe_allow_html=True)
        if not expense_df.empty:
            fig2 = go.Figure(go.Pie(labels=expense_df.index, values=expense_df.values, hole=0.62,
                marker=dict(colors=EXPENSE_COLORS[:len(expense_df)], line=dict(color='#0f1117',width=2)),
                textinfo="label+percent", textfont=dict(size=11,color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"))
            fig2.update_layout(paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                margin=dict(l=10,r=10,t=10,b=10), height=280, showlegend=True,
                legend=dict(font=dict(color="#a0aec0",size=10),bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(text=f"<b>{fmt_inr(total_expense)}</b>",x=0.5,y=0.5,font_size=15,font_color="#ff6b6b",showarrow=False)])
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No expenses for this period.")

    # Monthly trend (always all-time last 6M regardless of filter)
    st.markdown('<div class="section-header">📈 Monthly Trend (Last 6 Months)</div>', unsafe_allow_html=True)
    df_t = df_all.copy()
    df_t["Date"] = pd.to_datetime(df_t["Date"], errors="coerce")
    recent_6 = df_t[df_t["Date"] >= pd.Timestamp.now() - pd.DateOffset(months=6)]
    if not recent_6.empty:
        recent_6 = recent_6.copy()
        recent_6["Month"] = recent_6["Date"].dt.to_period("M")
        monthly = recent_6.groupby(["Month","Type"])["Amount"].sum().unstack(fill_value=0)
        months_str = [str(m) for m in monthly.index]
        fig3 = go.Figure()
        if "Income"  in monthly.columns: fig3.add_trace(go.Bar(name="Income",  x=months_str, y=monthly["Income"],  marker_color="#00b894", opacity=0.85))
        if "Expense" in monthly.columns: fig3.add_trace(go.Bar(name="Expense", x=months_str, y=monthly["Expense"], marker_color="#ff6b6b", opacity=0.85))
        fig3.update_layout(barmode="group", paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
            height=250, margin=dict(l=10,r=10,t=10,b=10),
            xaxis=dict(color="#718096",gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(color="#718096",gridcolor="rgba(255,255,255,0.04)"),
            legend=dict(font=dict(color="#a0aec0"),bgcolor="rgba(0,0,0,0)"), font=dict(color="#a0aec0"))
        st.plotly_chart(fig3, use_container_width=True)

    # Recent transactions
    st.markdown('<div class="section-header">🧾 Recent Transactions (Last 10)</div>', unsafe_allow_html=True)
    recent = df.sort_values("Date", ascending=False).head(10).reset_index(drop=True)
    for idx, row in recent.iterrows():
        tc = "#00b894" if row["Type"]=="Income" else "#ff6b6b"
        ti = "↑" if row["Type"]=="Income" else "↓"
        c = st.columns([1.5,1,1.5,1.2,2.5,0.7])
        with c[0]: st.markdown(f'<span style="color:#718096;font-size:0.82rem">{str(row["Date"])[:10]}</span>', unsafe_allow_html=True)
        with c[1]: st.markdown(f'<span style="color:{tc};font-weight:600;font-size:0.82rem">{ti} {row["Type"]}</span>', unsafe_allow_html=True)
        with c[2]: st.markdown(f'<span style="color:#a0aec0;font-size:0.82rem">🏷 {row["Category"]}</span>', unsafe_allow_html=True)
        with c[3]: st.markdown(f'<span style="color:{tc};font-family:\'Space Grotesk\',sans-serif;font-weight:600">{fmt_inr(float(row["Amount"]))}</span>', unsafe_allow_html=True)
        with c[4]: st.markdown(f'<span style="color:#718096;font-size:0.8rem">{row.get("Description","")}</span>', unsafe_allow_html=True)
        with c[5]:
            if st.button("🗑️", key=f"dash_del_{idx}", help="Delete"):
                db.delete_row(st.session_state.username, row.get("RowIndex",-1))
                st.rerun()
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.04);margin:0.2rem 0">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ADD TRANSACTION
# ═══════════════════════════════════════════════════════════════════════════════
def show_add_transaction():
    st.markdown("""
    <div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">➕ Add Transaction</div>
    <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Record a new income or expense entry</div>
    """, unsafe_allow_html=True)

    col_form, col_tip = st.columns([1.6, 1])
    with col_form:
        entry_date = st.date_input("📅 Date", value=date.today())
        txn_type   = st.selectbox("📂 Type", ["Income", "Expense"])
        categories = INCOME_CATEGORIES if txn_type == "Income" else EXPENSE_CATEGORIES

        cat_sel = st.selectbox("🏷 Category", categories, key="add_cat_sel")
        if cat_sel == "➕ Custom":
            custom_cat = st.text_input("✏️ Type your custom category", key="add_custom",
                                        placeholder="e.g. Freelance, Medical, Rent...")
            category = custom_cat.strip() if custom_cat.strip() else None
            if not category:
                st.caption("⚠️ Please enter a category name above.")
        else:
            category = cat_sel

        amount      = st.number_input("💵 Amount (₹)", min_value=0.0, step=10.0, format="%.2f")
        description = st.text_input("📝 Description", placeholder="Optional note...")

        if st.button(f"{'💚' if txn_type=='Income' else '❤️'} Add {txn_type}", type="primary", use_container_width=True):
            if amount <= 0:
                st.warning("Please enter an amount greater than 0.")
            elif not category:
                st.warning("Please enter a category name.")
            else:
                db.add_transaction(st.session_state.username, str(entry_date), txn_type, category, amount, description)
                st.success(f"✅ {txn_type} of {fmt_inr(amount)} added!")
                st.balloons()

    with col_tip:
        base_i = [c for c in INCOME_CATEGORIES  if c != "➕ Custom"]
        base_e = [c for c in EXPENSE_CATEGORIES if c != "➕ Custom"]
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1a1d2e,#16192a);border:1px solid rgba(255,255,255,0.06);
                    border-radius:16px;padding:1.5rem;margin-top:0.5rem;">
            <div style="font-family:'Space Grotesk',sans-serif;font-weight:600;color:#e2e8f0;margin-bottom:1rem;">💡 Quick Tips</div>
            <div style="font-size:0.82rem;color:#718096;line-height:1.8;">
                ✅ Be consistent with categories<br>✅ Log entries daily for accuracy<br>
                ✅ Use description for reference<br>✅ Use ➕ Custom for unique categories<br><br>
                <b style="color:#a0aec0">Income:</b><br>
                <span style="color:#00b894">{"  ·  ".join(base_i)}</span><br><br>
                <b style="color:#a0aec0">Expense:</b><br>
                <span style="color:#ff6b6b">{"  ·  ".join(base_e)}</span>
            </div>
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# HISTORY
# ═══════════════════════════════════════════════════════════════════════════════
def show_history():
    df = db.get_user_data(st.session_state.username)

    # Header + PDF Export button (top-right)
    hcol, btn_col = st.columns([3, 1])
    with hcol:
        st.markdown("""
        <div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">📋 Transaction History</div>
        <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Full history · filter, edit or delete any entry</div>
        """, unsafe_allow_html=True)
    with btn_col:
        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
        if not df.empty:
            pdf_data = generate_pdf(df, st.session_state.username)
            st.download_button(
                label="📥 Export PDF",
                data=pdf_data,
                file_name=f"bills_{st.session_state.username}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

    if df.empty:
        st.info("No transactions found.")
        return

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("Date", ascending=False).reset_index(drop=True)

    # Filters
    f1, f2, f3 = st.columns(3)
    with f1: type_filter  = st.selectbox("Filter by Type",     ["All","Income","Expense"])
    with f2:
        cat_opts = ["All"] + sorted(df["Category"].unique().tolist())
        cat_filter = st.selectbox("Filter by Category", cat_opts)
    with f3:
        months = ["All"] + sorted(df["Date"].dt.to_period("M").astype(str).unique().tolist(), reverse=True)
        month_filter = st.selectbox("Filter by Month", months)

    filtered = df.copy()
    if type_filter  != "All": filtered = filtered[filtered["Type"]     == type_filter]
    if cat_filter   != "All": filtered = filtered[filtered["Category"] == cat_filter]
    if month_filter != "All": filtered = filtered[filtered["Date"].dt.to_period("M").astype(str) == month_filter]

    st.markdown(f"""
    <div style="font-size:0.82rem;color:#718096;margin-bottom:0.8rem;">
        Showing <b style="color:#a0aec0">{len(filtered)}</b> transactions ·
        <b style="color:#00b894">₹{filtered[filtered['Type']=='Income']['Amount'].sum():,.0f} income</b> /
        <b style="color:#ff6b6b">₹{filtered[filtered['Type']=='Expense']['Amount'].sum():,.0f} expense</b>
    </div>""", unsafe_allow_html=True)

    # ── Inline Edit Form ──────────────────────────────────────────────────────
    if st.session_state.editing_row is not None:
        erow = st.session_state.editing_row
        with st.container():
            st.markdown("""
            <div style="background:linear-gradient(135deg,#0d2818,#1a1d2e);
                        border:1px solid rgba(0,184,148,0.4);border-radius:14px;
                        padding:1rem 1.2rem 0.5rem 1.2rem;margin-bottom:1rem;">
            """, unsafe_allow_html=True)
            st.markdown('<div style="font-family:\'Space Grotesk\',sans-serif;font-weight:600;color:#00b894;margin-bottom:0.8rem;">✏️ Editing Transaction</div>', unsafe_allow_html=True)
            ec1, ec2, ec3 = st.columns(3)
            with ec1: e_date = st.date_input("Date", value=pd.to_datetime(erow["Date"]).date(), key="e_date")
            with ec2: e_type = st.selectbox("Type", ["Income","Expense"], index=0 if erow["Type"]=="Income" else 1, key="e_type")
            with ec3:
                ecats    = INCOME_CATEGORIES if e_type=="Income" else EXPENSE_CATEGORIES
                base_cats = [c for c in ecats if c != "➕ Custom"]
                cur_cat  = erow["Category"]
                def_idx  = base_cats.index(cur_cat) if cur_cat in base_cats else len(ecats)-1
                e_cat_sel = st.selectbox("Category", ecats, index=def_idx, key="e_cat_sel")
                if e_cat_sel == "➕ Custom":
                    e_cat = st.text_input("Custom category", value=cur_cat if cur_cat not in base_cats else "", key="e_custom")
                    e_cat = e_cat.strip() or cur_cat
                else:
                    e_cat = e_cat_sel

            ec4, ec5 = st.columns(2)
            with ec4: e_amount = st.number_input("Amount (₹)", value=float(erow["Amount"]), min_value=0.0, step=10.0, format="%.2f", key="e_amount")
            with ec5: e_desc   = st.text_input("Description", value=str(erow.get("Description","")), key="e_desc")

            sa, sb = st.columns(2)
            with sa:
                if st.button("💾 Save Changes", type="primary", use_container_width=True):
                    if e_amount <= 0:
                        st.warning("Amount must be > 0")
                    else:
                        db.update_row(st.session_state.username, int(erow["RowIndex"]),
                                      str(e_date), e_type, e_cat, e_amount, e_desc)
                        st.session_state.editing_row = None
                        st.success("✅ Updated!")
                        st.rerun()
            with sb:
                if st.button("✖ Cancel", use_container_width=True):
                    st.session_state.editing_row = None
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # ── Transaction rows ──────────────────────────────────────────────────────
    for idx, row in filtered.iterrows():
        tc = "#00b894" if row["Type"]=="Income" else "#ff6b6b"
        ti = "↑" if row["Type"]=="Income" else "↓"
        c  = st.columns([1.4, 1.1, 1.5, 1.2, 2.2, 0.55, 0.55])
        with c[0]: st.markdown(f'<span style="color:#718096;font-size:0.82rem">{str(row["Date"])[:10]}</span>', unsafe_allow_html=True)
        with c[1]: st.markdown(f'<span style="color:{tc};font-weight:600;font-size:0.82rem">{ti} {row["Type"]}</span>', unsafe_allow_html=True)
        with c[2]: st.markdown(f'<span style="color:#a0aec0;font-size:0.82rem">🏷 {row["Category"]}</span>', unsafe_allow_html=True)
        with c[3]: st.markdown(f'<span style="color:{tc};font-family:\'Space Grotesk\',sans-serif;font-weight:600">{fmt_inr(float(row["Amount"]))}</span>', unsafe_allow_html=True)
        with c[4]: st.markdown(f'<span style="color:#718096;font-size:0.8rem">{row.get("Description","")}</span>', unsafe_allow_html=True)
        with c[5]:
            if st.button("✏️", key=f"edit_{idx}", help="Edit this transaction"):
                st.session_state.editing_row = row.to_dict()
                st.rerun()
        with c[6]:
            if st.button("🗑️", key=f"del_{idx}", help="Delete this transaction"):
                db.delete_row(st.session_state.username, row.get("RowIndex",-1))
                st.session_state.editing_row = None
                st.rerun()
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.04);margin:0.2rem 0">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    show_auth()
else:
    page = show_sidebar()
    if   "Dashboard" in page: show_dashboard()
    elif "Add"       in page: show_add_transaction()
    elif "History"   in page: show_history()
