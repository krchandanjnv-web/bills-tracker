import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date
import hashlib
from google_sheets import GoogleSheetsDB

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="💰 Personal Bills Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Hide default streamlit elements */
#MainMenu, footer, header { visibility: hidden; }

/* Main background */
.main { background: #0f1117; }
.block-container { padding: 1.5rem 2rem; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1d2e 0%, #0f1117 100%);
    border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.95rem;
    color: #a0aec0;
    font-weight: 500;
}
[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] { gap: 0.2rem; }

/* KPI Cards */
.kpi-card {
    background: linear-gradient(135deg, #1a1d2e 0%, #16192a 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s;
}
.kpi-card:hover { transform: translateY(-2px); }
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}
.kpi-income::before { background: linear-gradient(90deg, #00b894, #00cec9); }
.kpi-expense::before { background: linear-gradient(90deg, #d63031, #e17055); }
.kpi-balance::before { background: linear-gradient(90deg, #6c5ce7, #a29bfe); }
.kpi-label {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #718096;
    margin-bottom: 0.5rem;
}
.kpi-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.1;
}
.kpi-income .kpi-value { color: #00b894; }
.kpi-expense .kpi-value { color: #ff6b6b; }
.kpi-balance .kpi-value { color: #a29bfe; }
.kpi-sub {
    font-size: 0.72rem;
    color: #4a5568;
    margin-top: 0.3rem;
}

/* Section Headers */
.section-header {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.1rem;
    font-weight: 600;
    color: #e2e8f0;
    margin: 1.5rem 0 1rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}

/* Sidebar brand */
.brand {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #00b894, #a29bfe);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.brand-sub { font-size: 0.75rem; color: #4a5568; margin-bottom: 1.5rem; }

/* Auth form */
.auth-container {
    max-width: 420px;
    margin: 3rem auto;
    background: linear-gradient(135deg, #1a1d2e 0%, #16192a 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 2.5rem;
}
.auth-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: #e2e8f0;
    text-align: center;
    margin-bottom: 0.3rem;
}
.auth-subtitle { text-align: center; color: #718096; font-size: 0.85rem; margin-bottom: 1.8rem; }

/* Table styling */
.styled-table {
    background: #1a1d2e;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.06);
    overflow: hidden;
}

/* Stmetric overrides */
[data-testid="stMetric"] { background: transparent !important; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ───────────────────────────────────────────────────────────────
INCOME_CATEGORIES  = ["Bhaiya", "Loan", "Cashback", "Salary", "MCM", "Redeem"]
EXPENSE_CATEGORIES = ["Shopping", "Utilities", "Ticket Booking", "Mess Bill",
                       "Loan Repayment", "Invest", "Entertainment", "Travel", "Other"]

INCOME_COLORS  = ["#00b894","#00cec9","#55efc4","#81ecec","#74b9ff","#a29bfe"]
EXPENSE_COLORS = ["#d63031","#e17055","#fdcb6e","#fd79a8","#e84393","#6c5ce7","#b2bec3","#0984e3","#00b894"]

# ─── Helpers ─────────────────────────────────────────────────────────────────
def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def fmt_inr(amount: float) -> str:
    """Format number as Indian Rupees"""
    if abs(amount) >= 1_00_000:
        return f"₹{amount/1_00_000:.1f}L"
    if abs(amount) >= 1_000:
        return f"₹{amount:,.0f}"
    return f"₹{amount:.0f}"

def get_current_month_data(df: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df[(df["Date"].dt.month == now.month) & (df["Date"].dt.year == now.year)]

# ─── Session State Init ───────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.page = "Dashboard"

# ─── DB Connection ────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return GoogleSheetsDB()

db = get_db()

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH PAGE
# ═══════════════════════════════════════════════════════════════════════════════
def show_auth():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center; margin-top:2rem; margin-bottom:2rem;">
            <div style="font-size:3rem; margin-bottom:0.5rem;">💰</div>
            <div style="font-family:'Space Grotesk',sans-serif; font-size:1.8rem;
                        font-weight:700; background:linear-gradient(135deg,#00b894,#a29bfe);
                        -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                Bills Tracker
            </div>
            <div style="color:#718096; font-size:0.85rem; margin-top:0.3rem;">
                Your personal finance dashboard
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_signup = st.tabs(["🔑 Login", "✨ Sign Up"])

        with tab_login:
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            username = st.text_input("Username", key="login_user", placeholder="Enter username")
            password = st.text_input("Password", type="password", key="login_pass", placeholder="Enter password")
            if st.button("Login →", use_container_width=True, type="primary"):
                if username and password:
                    result = db.verify_user(username, hash_password(password))
                    if result:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.rerun()
                    else:
                        st.error("❌ Invalid credentials. Please try again.")
                else:
                    st.warning("Please fill in all fields.")

        with tab_signup:
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            new_user = st.text_input("Choose Username", key="su_user", placeholder="Pick a username")
            new_email = st.text_input("Email (optional)", key="su_email", placeholder="your@email.com")
            new_pass = st.text_input("Password", type="password", key="su_pass", placeholder="Min 6 characters")
            new_pass2 = st.text_input("Confirm Password", type="password", key="su_pass2", placeholder="Repeat password")
            if st.button("Create Account →", use_container_width=True, type="primary"):
                if new_user and new_pass:
                    if new_pass != new_pass2:
                        st.error("Passwords don't match!")
                    elif len(new_pass) < 6:
                        st.warning("Password must be at least 6 characters.")
                    elif db.user_exists(new_user):
                        st.error("Username already taken.")
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
        <div style="background:rgba(255,255,255,0.04); border-radius:10px;
                    padding:0.6rem 1rem; margin-bottom:1.5rem; font-size:0.82rem; color:#a0aec0;">
            👤 Logged in as <b style="color:#e2e8f0">{st.session_state.username}</b>
        </div>
        """, unsafe_allow_html=True)

        page = st.radio(
            "Navigation",
            ["📊 Dashboard", "➕ Add Transaction", "📋 History"],
            label_visibility="collapsed"
        )

        st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)

        now = datetime.now()
        st.markdown(f"""
        <div style="font-size:0.72rem; color:#4a5568; text-align:center; padding:0.5rem;">
            📅 {now.strftime('%B %Y')}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()

    return page

# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def show_dashboard():
    df = db.get_user_data(st.session_state.username)

    st.markdown(f"""
    <div style="font-family:'Space Grotesk',sans-serif; font-size:1.6rem; font-weight:700;
                color:#e2e8f0; margin-bottom:0.2rem;">
        📊 Dashboard
    </div>
    <div style="color:#718096; font-size:0.85rem; margin-bottom:1.5rem;">
        {datetime.now().strftime('%B %Y')} · Personal Finance Overview
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.info("🌱 No transactions yet! Add your first transaction to see your dashboard.", icon="💡")
        return

    # Current month data
    month_df = get_current_month_data(df.copy())
    total_df = df.copy()
    total_df["Date"] = pd.to_datetime(total_df["Date"], errors="coerce")

    total_income  = month_df[month_df["Type"] == "Income"]["Amount"].sum()
    total_expense = month_df[month_df["Type"] == "Expense"]["Amount"].sum()
    net_balance   = total_income - total_expense

    # ── KPI Cards ───────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="kpi-card kpi-income">
            <div class="kpi-label">💚 Total Income</div>
            <div class="kpi-value">{fmt_inr(total_income)}</div>
            <div class="kpi-sub">This month</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="kpi-card kpi-expense">
            <div class="kpi-label">❤️ Total Expense</div>
            <div class="kpi-value">{fmt_inr(total_expense)}</div>
            <div class="kpi-sub">This month</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        balance_class = "kpi-balance"
        balance_color = "#a29bfe" if net_balance >= 0 else "#ff6b6b"
        st.markdown(f"""
        <div class="kpi-card {balance_class}">
            <div class="kpi-label">{'✨' if net_balance >= 0 else '⚠️'} Net Balance</div>
            <div class="kpi-value" style="color:{balance_color}">{fmt_inr(net_balance)}</div>
            <div class="kpi-sub">{'Surplus' if net_balance >= 0 else 'Deficit'} this month</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # ── Donut Charts ─────────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    income_df  = month_df[month_df["Type"] == "Income"].groupby("Category")["Amount"].sum()
    expense_df = month_df[month_df["Type"] == "Expense"].groupby("Category")["Amount"].sum()

    CHART_BG = "rgba(0,0,0,0)"

    with col_l:
        st.markdown('<div class="section-header">💚 Income Breakdown</div>', unsafe_allow_html=True)
        if not income_df.empty:
            fig = go.Figure(go.Pie(
                labels=income_df.index,
                values=income_df.values,
                hole=0.62,
                marker=dict(colors=INCOME_COLORS[:len(income_df)],
                            line=dict(color='#0f1117', width=2)),
                textinfo="label+percent",
                textfont=dict(size=11, color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"
            ))
            fig.update_layout(
                paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                margin=dict(l=10, r=10, t=10, b=10),
                height=280,
                showlegend=True,
                legend=dict(font=dict(color="#a0aec0", size=10), bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(
                    text=f"<b>{fmt_inr(total_income)}</b>",
                    x=0.5, y=0.5, font_size=15, font_color="#00b894",
                    showarrow=False
                )]
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No income entries this month.")

    with col_r:
        st.markdown('<div class="section-header">❤️ Expense Breakdown</div>', unsafe_allow_html=True)
        if not expense_df.empty:
            fig2 = go.Figure(go.Pie(
                labels=expense_df.index,
                values=expense_df.values,
                hole=0.62,
                marker=dict(colors=EXPENSE_COLORS[:len(expense_df)],
                            line=dict(color='#0f1117', width=2)),
                textinfo="label+percent",
                textfont=dict(size=11, color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"
            ))
            fig2.update_layout(
                paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                margin=dict(l=10, r=10, t=10, b=10),
                height=280,
                showlegend=True,
                legend=dict(font=dict(color="#a0aec0", size=10), bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(
                    text=f"<b>{fmt_inr(total_expense)}</b>",
                    x=0.5, y=0.5, font_size=15, font_color="#ff6b6b",
                    showarrow=False
                )]
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No expense entries this month.")

    # ── Monthly Trend Bar Chart ───────────────────────────────────────────────
    st.markdown('<div class="section-header">📈 Monthly Trend (Last 6 Months)</div>', unsafe_allow_html=True)
    total_df["Month"] = total_df["Date"].dt.to_period("M")
    recent_6 = total_df[total_df["Date"] >= pd.Timestamp.now() - pd.DateOffset(months=6)]
    if not recent_6.empty:
        monthly = recent_6.groupby(["Month", "Type"])["Amount"].sum().unstack(fill_value=0)
        months_str = [str(m) for m in monthly.index]
        fig3 = go.Figure()
        if "Income" in monthly.columns:
            fig3.add_trace(go.Bar(name="Income", x=months_str, y=monthly["Income"],
                                  marker_color="#00b894", opacity=0.85))
        if "Expense" in monthly.columns:
            fig3.add_trace(go.Bar(name="Expense", x=months_str, y=monthly["Expense"],
                                  marker_color="#ff6b6b", opacity=0.85))
        fig3.update_layout(
            barmode="group", paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
            height=250, margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(color="#718096", gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(color="#718096", gridcolor="rgba(255,255,255,0.04)"),
            legend=dict(font=dict(color="#a0aec0"), bgcolor="rgba(0,0,0,0)"),
            font=dict(color="#a0aec0")
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── Recent Transactions ───────────────────────────────────────────────────
    st.markdown('<div class="section-header">🧾 Recent Transactions (Last 10)</div>', unsafe_allow_html=True)
    recent = df.sort_values("Date", ascending=False).head(10).reset_index(drop=True)
    if not recent.empty:
        for idx, row in recent.iterrows():
            col_date, col_type, col_cat, col_amt, col_desc, col_del = st.columns([1.5, 1, 1.5, 1.2, 2.5, 0.7])
            t_color = "#00b894" if row["Type"] == "Income" else "#ff6b6b"
            t_icon  = "↑" if row["Type"] == "Income" else "↓"
            with col_date:
                st.markdown(f'<span style="color:#718096;font-size:0.82rem">{str(row["Date"])[:10]}</span>', unsafe_allow_html=True)
            with col_type:
                st.markdown(f'<span style="color:{t_color};font-weight:600;font-size:0.82rem">{t_icon} {row["Type"]}</span>', unsafe_allow_html=True)
            with col_cat:
                st.markdown(f'<span style="color:#a0aec0;font-size:0.82rem">🏷 {row["Category"]}</span>', unsafe_allow_html=True)
            with col_amt:
                st.markdown(f'<span style="color:{t_color};font-family:\'Space Grotesk\',sans-serif;font-weight:600">{fmt_inr(float(row["Amount"]))}</span>', unsafe_allow_html=True)
            with col_desc:
                st.markdown(f'<span style="color:#718096;font-size:0.8rem">{row.get("Description","")}</span>', unsafe_allow_html=True)
            with col_del:
                if st.button("🗑️", key=f"del_{idx}_{row.get('RowIndex', idx)}",
                             help="Delete this transaction"):
                    db.delete_row(st.session_state.username, row.get("RowIndex", -1))
                    st.rerun()
            st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.04);margin:0.2rem 0">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ADD TRANSACTION
# ═══════════════════════════════════════════════════════════════════════════════
def show_add_transaction():
    st.markdown("""
    <div style="font-family:'Space Grotesk',sans-serif; font-size:1.6rem; font-weight:700;
                color:#e2e8f0; margin-bottom:0.2rem;">➕ Add Transaction</div>
    <div style="color:#718096; font-size:0.85rem; margin-bottom:1.5rem;">
        Record a new income or expense entry
    </div>
    """, unsafe_allow_html=True)

    col_form, col_tip = st.columns([1.6, 1])

    with col_form:
        with st.container():
            entry_date = st.date_input("📅 Date", value=date.today())
            txn_type = st.selectbox("📂 Type", ["Income", "Expense"])
            categories = INCOME_CATEGORIES if txn_type == "Income" else EXPENSE_CATEGORIES
            category = st.selectbox("🏷 Category", categories)
            amount = st.number_input("💵 Amount (₹)", min_value=0.0, step=10.0, format="%.2f")
            description = st.text_input("📝 Description", placeholder="Optional note...")

            color = "#00b894" if txn_type == "Income" else "#ff6b6b"
            btn_label = f"{'💚' if txn_type == 'Income' else '❤️'} Add {txn_type}"

            if st.button(btn_label, type="primary", use_container_width=True):
                if amount <= 0:
                    st.warning("Please enter an amount greater than 0.")
                else:
                    db.add_transaction(
                        username=st.session_state.username,
                        date=str(entry_date),
                        txn_type=txn_type,
                        category=category,
                        amount=amount,
                        description=description
                    )
                    st.success(f"✅ {txn_type} of {fmt_inr(amount)} added successfully!")
                    st.balloons()

    with col_tip:
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1a1d2e,#16192a);
                    border:1px solid rgba(255,255,255,0.06); border-radius:16px;
                    padding:1.5rem; margin-top:0.5rem;">
            <div style="font-family:'Space Grotesk',sans-serif; font-weight:600;
                        color:#e2e8f0; margin-bottom:1rem;">💡 Quick Tips</div>
            <div style="font-size:0.82rem; color:#718096; line-height:1.8;">
                ✅ Be consistent with categories<br>
                ✅ Log entries daily for accuracy<br>
                ✅ Use description for reference<br>
                ✅ Track all small expenses too<br><br>
                <b style="color:#a0aec0">Income Categories:</b><br>
                <span style="color:#00b894">{'  ·  '.join(INCOME_CATEGORIES)}</span><br><br>
                <b style="color:#a0aec0">Expense Categories:</b><br>
                <span style="color:#ff6b6b">{'  ·  '.join(EXPENSE_CATEGORIES)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# HISTORY PAGE
# ═══════════════════════════════════════════════════════════════════════════════
def show_history():
    st.markdown("""
    <div style="font-family:'Space Grotesk',sans-serif; font-size:1.6rem; font-weight:700;
                color:#e2e8f0; margin-bottom:0.2rem;">📋 Transaction History</div>
    <div style="color:#718096; font-size:0.85rem; margin-bottom:1.5rem;">
        Full history with filters and delete
    </div>
    """, unsafe_allow_html=True)

    df = db.get_user_data(st.session_state.username)
    if df.empty:
        st.info("No transactions found.")
        return

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("Date", ascending=False).reset_index(drop=True)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        type_filter = st.selectbox("Filter by Type", ["All", "Income", "Expense"])
    with col2:
        cat_options = ["All"] + sorted(df["Category"].unique().tolist())
        cat_filter = st.selectbox("Filter by Category", cat_options)
    with col3:
        months = ["All"] + sorted(df["Date"].dt.to_period("M").astype(str).unique().tolist(), reverse=True)
        month_filter = st.selectbox("Filter by Month", months)

    filtered = df.copy()
    if type_filter != "All":
        filtered = filtered[filtered["Type"] == type_filter]
    if cat_filter != "All":
        filtered = filtered[filtered["Category"] == cat_filter]
    if month_filter != "All":
        filtered = filtered[filtered["Date"].dt.to_period("M").astype(str) == month_filter]

    st.markdown(f"""
    <div style="font-size:0.82rem; color:#718096; margin-bottom:0.8rem;">
        Showing <b style="color:#a0aec0">{len(filtered)}</b> transactions ·
        Total: <b style="color:#00b894">₹{filtered[filtered['Type']=='Income']['Amount'].sum():,.0f} income</b> /
        <b style="color:#ff6b6b">₹{filtered[filtered['Type']=='Expense']['Amount'].sum():,.0f} expense</b>
    </div>
    """, unsafe_allow_html=True)

    for idx, row in filtered.iterrows():
        t_color = "#00b894" if row["Type"] == "Income" else "#ff6b6b"
        t_icon  = "↑" if row["Type"] == "Income" else "↓"
        cols = st.columns([1.5, 1.1, 1.5, 1.2, 2.5, 0.7])
        with cols[0]:
            st.markdown(f'<span style="color:#718096;font-size:0.82rem">{str(row["Date"])[:10]}</span>', unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f'<span style="color:{t_color};font-weight:600;font-size:0.82rem">{t_icon} {row["Type"]}</span>', unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f'<span style="color:#a0aec0;font-size:0.82rem">🏷 {row["Category"]}</span>', unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f'<span style="color:{t_color};font-family:\'Space Grotesk\',sans-serif;font-weight:600">{fmt_inr(float(row["Amount"]))}</span>', unsafe_allow_html=True)
        with cols[4]:
            st.markdown(f'<span style="color:#718096;font-size:0.8rem">{row.get("Description","")}</span>', unsafe_allow_html=True)
        with cols[5]:
            if st.button("🗑️", key=f"hist_del_{idx}", help="Delete"):
                db.delete_row(st.session_state.username, row.get("RowIndex", -1))
                st.rerun()
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.04);margin:0.2rem 0">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    show_auth()
else:
    page = show_sidebar()
    if "Dashboard" in page:
        show_dashboard()
    elif "Add" in page:
        show_add_transaction()
    elif "History" in page:
        show_history()
