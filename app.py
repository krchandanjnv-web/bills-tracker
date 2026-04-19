import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import hashlib, io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as rl_canvas
from google_sheets import GoogleSheetsDB

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="💰 Bills Tracker", page_icon="💰",
                   layout="wide", initial_sidebar_state="expanded")

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;}
#MainMenu,footer,header{visibility:hidden;}
.main{background:#0f1117;} .block-container{padding:1.5rem 2rem;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#1a1d2e 0%,#0f1117 100%);border-right:1px solid rgba(255,255,255,0.06);}
.kpi-card{background:linear-gradient(135deg,#1a1d2e 0%,#16192a 100%);border:1px solid rgba(255,255,255,0.08);
  border-radius:16px;padding:1.5rem;text-align:center;position:relative;overflow:hidden;transition:transform 0.2s;}
.kpi-card:hover{transform:translateY(-2px);}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.kpi-income::before{background:linear-gradient(90deg,#00b894,#00cec9);}
.kpi-expense::before{background:linear-gradient(90deg,#d63031,#e17055);}
.kpi-balance::before{background:linear-gradient(90deg,#6c5ce7,#a29bfe);}
.kpi-taken::before{background:linear-gradient(90deg,#ff6b6b,#fd79a8);}
.kpi-given::before{background:linear-gradient(90deg,#00b894,#55efc4);}
.kpi-label{font-size:0.78rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:#718096;margin-bottom:0.5rem;}
.kpi-value{font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:700;line-height:1.1;}
.kpi-income .kpi-value{color:#00b894;} .kpi-expense .kpi-value{color:#ff6b6b;} .kpi-balance .kpi-value{color:#a29bfe;}
.kpi-taken .kpi-value{color:#ff6b6b;}  .kpi-given .kpi-value{color:#00b894;}
.kpi-sub{font-size:0.72rem;color:#4a5568;margin-top:0.3rem;}
.section-header{font-family:'Space Grotesk',sans-serif;font-size:1.1rem;font-weight:600;color:#e2e8f0;
  margin:1.5rem 0 1rem 0;padding-bottom:0.5rem;border-bottom:1px solid rgba(255,255,255,0.06);}
.brand{font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:700;
  background:linear-gradient(135deg,#00b894,#a29bfe);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:0.2rem;}
.brand-sub{font-size:0.75rem;color:#4a5568;margin-bottom:1.5rem;}
.due-row-active{border-left:3px solid #fdcb6e;}
.due-row-settled{border-left:3px solid #00b894;opacity:0.6;}
[data-testid="stMetric"]{background:transparent !important;}
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
INCOME_CATEGORIES  = ["Bhaiya","Loan","Cashback","Salary","MCM","Redeem","➕ Custom"]
EXPENSE_CATEGORIES = ["Shopping","Utilities","Ticket Booking","Mess Bill",
                       "Loan Repayment","Invest","Entertainment","Travel","Other","➕ Custom"]
INCOME_COLORS  = ["#00b894","#00cec9","#55efc4","#81ecec","#74b9ff","#a29bfe","#fd79a8"]
EXPENSE_COLORS = ["#d63031","#e17055","#fdcb6e","#fd79a8","#e84393","#6c5ce7","#b2bec3","#0984e3","#00b894","#55efc4"]
DASH_FILTERS   = ["Last 7 Days","This Month","This Year","All Transactions"]
PDF_FOOTER     = "Bill Tracker By krchandan"

# ─── Helpers ─────────────────────────────────────────────────────────────────
def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def fmt_inr(a):
    if abs(a)>=1_00_000: return f"₹{a/1_00_000:.1f}L"
    if abs(a)>=1_000:    return f"₹{a:,.0f}"
    return f"₹{a:.0f}"

def apply_date_filter(df, label):
    df = df.copy(); df["Date"]=pd.to_datetime(df["Date"],errors="coerce")
    now=pd.Timestamp.now()
    if label=="Last 7 Days":  return df[df["Date"]>=now-timedelta(days=7)]
    if label=="This Month":   return df[(df["Date"].dt.month==now.month)&(df["Date"].dt.year==now.year)]
    if label=="This Year":    return df[df["Date"].dt.year==now.year]
    return df

def days_elapsed(start_str):
    try:
        s = pd.to_datetime(start_str).date()
        return (date.today()-s).days
    except: return 0

# ─── Session State ────────────────────────────────────────────────────────────
for k,v in {"logged_in":False,"username":"","dash_filter":"This Month","editing_row":None}.items():
    if k not in st.session_state: st.session_state[k]=v

# ─── DB ───────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db(): return GoogleSheetsDB()
db = get_db()

# ═══════════════════════════════════════════════════════════════════════════════
# PDF GENERATOR  (filtered + footer)
# ═══════════════════════════════════════════════════════════════════════════════
class FooterCanvas(rl_canvas.Canvas):
    """Adds a footer to every PDF page."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#718096"))
        page_num = self._saved_page_states.index(
            {k: v for k, v in self.__dict__.items() if k in self._saved_page_states[0]}
        ) + 1 if hasattr(self, '_saved_page_states') else 1
        self.drawString(15*mm, 8*mm, PDF_FOOTER)
        self.drawRightString(A4[0]-15*mm, 8*mm,
                             f"Generated: {datetime.now().strftime('%d %b %Y')}  |  Page {self._pageNumber} of {page_count}")
        self.setStrokeColor(colors.HexColor("#2d3748"))
        self.line(15*mm, 12*mm, A4[0]-15*mm, 12*mm)
        self.restoreState()


def generate_pdf(df: pd.DataFrame, username: str, filter_label: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=22*mm)

    title_s = ParagraphStyle("t", fontSize=17, fontName="Helvetica-Bold",
                              textColor=colors.HexColor("#00b894"), alignment=TA_CENTER, spaceAfter=3)
    sub_s   = ParagraphStyle("s", fontSize=8.5, fontName="Helvetica",
                              textColor=colors.HexColor("#718096"), alignment=TA_CENTER, spaceAfter=12)
    head_s  = ParagraphStyle("h", fontSize=10.5, fontName="Helvetica-Bold",
                              textColor=colors.HexColor("#e2e8f0"), spaceAfter=5)

    elements = []
    elements.append(Paragraph("Personal Bills Tracker — Transaction Report", title_s))
    filter_info = f"  |  Filter: {filter_label}" if filter_label else ""
    elements.append(Paragraph(
        f"User: {username}{filter_info}  |  Records: {len(df)}  |  {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        sub_s))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#2d3748"), spaceAfter=8))

    # ── Summary cards ─────────────────────────────────────────────────────
    total_inc = df[df["Type"]=="Income"]["Amount"].sum()
    total_exp = df[df["Type"]=="Expense"]["Amount"].sum()
    net       = total_inc - total_exp
    net_color = colors.HexColor("#6c5ce7") if net >= 0 else colors.HexColor("#d63031")

    summary = [
        ["Total Income", "Total Expense", "Net Balance"],
        [f"Rs {total_inc:,.2f}", f"Rs {total_exp:,.2f}", f"Rs {net:,.2f}"]
    ]
    sum_t = Table(summary, colWidths=[57*mm,57*mm,57*mm])
    sum_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1a1d2e")),
        ("TEXTCOLOR", (0,0),(-1,0),colors.HexColor("#a0aec0")),
        ("BACKGROUND",(0,1),(0,1), colors.HexColor("#00b894")),
        ("BACKGROUND",(1,1),(1,1), colors.HexColor("#d63031")),
        ("BACKGROUND",(2,1),(2,1), net_color),
        ("TEXTCOLOR", (0,1),(-1,1),colors.white),
        ("FONTNAME",  (0,0),(-1,-1),"Helvetica-Bold"),
        ("FONTSIZE",  (0,0),(-1,0), 8),
        ("FONTSIZE",  (0,1),(-1,1), 12),
        ("ALIGN",     (0,0),(-1,-1),"CENTER"),
        ("VALIGN",    (0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("GRID",      (0,0),(-1,-1),0.4,colors.HexColor("#2d3748")),
    ]))
    elements.append(sum_t)
    elements.append(Spacer(1,8*mm))
    elements.append(Paragraph("Transaction Details", head_s))

    # ── Transaction table ─────────────────────────────────────────────────
    hdr = ["Date","Type","Category","Amount (Rs)","Description"]
    rows = [hdr]
    for _, row in df.sort_values("Date", ascending=False).iterrows():
        rows.append([
            str(row["Date"])[:10],
            str(row["Type"]),
            str(row["Category"]),
            f"{float(row['Amount']):,.2f}",
            str(row.get("Description",""))[:50],
        ])

    col_w = [24*mm, 22*mm, 30*mm, 28*mm, 67*mm]
    txn_t = Table(rows, colWidths=col_w, repeatRows=1)

    row_styles = []
    for i, r in enumerate(rows[1:], 1):
        bg = colors.HexColor("#0b2015") if r[1]=="Income" else colors.HexColor("#1e0a0a")
        row_styles.append(("BACKGROUND",(0,i),(-1,i),bg))
        tc = colors.HexColor("#00b894") if r[1]=="Income" else colors.HexColor("#ff6b6b")
        row_styles.append(("TEXTCOLOR",(3,i),(3,i),tc))

    txn_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), colors.HexColor("#16192a")),
        ("TEXTCOLOR",  (0,0),(-1,0), colors.HexColor("#a0aec0")),
        ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0),(-1,0), 8),
        ("FONTNAME",   (0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",   (0,1),(-1,-1),7.5),
        ("TEXTCOLOR",  (0,1),(-1,-1),colors.HexColor("#e2e8f0")),
        ("ALIGN",      (3,0),(3,-1), "RIGHT"),
        ("ALIGN",      (0,0),(2,-1), "LEFT"),
        ("LEFTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING", (0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("GRID",       (0,0),(-1,-1),0.3,colors.HexColor("#2d3748")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#0b2015"),colors.HexColor("#1e0a0a")]),
    ]+row_styles))

    elements.append(txn_t)

    # Build with footer canvas
    doc.build(elements, canvasmaker=FooterCanvas)
    return buf.getvalue()

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════
def show_auth():
    _, col2, _ = st.columns([1,1.2,1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-top:2rem;margin-bottom:2rem;">
            <div style="font-size:3rem;margin-bottom:0.5rem;">💰</div>
            <div style="font-family:'Space Grotesk',sans-serif;font-size:1.8rem;font-weight:700;
                background:linear-gradient(135deg,#00b894,#a29bfe);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                Bills Tracker</div>
            <div style="color:#718096;font-size:0.85rem;margin-top:0.3rem;">Your personal finance dashboard</div>
        </div>""", unsafe_allow_html=True)

        t1, t2 = st.tabs(["🔑 Login","✨ Sign Up"])
        with t1:
            u = st.text_input("Username", key="lu")
            p = st.text_input("Password", type="password", key="lp")
            if st.button("Login →", use_container_width=True, type="primary"):
                if u and p:
                    if db.verify_user(u, hash_password(p)):
                        st.session_state.logged_in=True; st.session_state.username=u; st.rerun()
                    else: st.error("❌ Invalid credentials.")
                else: st.warning("Fill all fields.")
        with t2:
            nu=st.text_input("Username",key="su_u"); ne=st.text_input("Email (optional)",key="su_e")
            np=st.text_input("Password",type="password",key="su_p"); np2=st.text_input("Confirm",type="password",key="su_p2")
            if st.button("Create Account →", use_container_width=True, type="primary"):
                if nu and np:
                    if np!=np2: st.error("Passwords don't match!")
                    elif len(np)<6: st.warning("Min 6 chars.")
                    elif db.user_exists(nu): st.error("Username taken.")
                    else: db.add_user(nu,hash_password(np),ne); st.success("✅ Created! Please login.")
                else: st.warning("Username and password required.")

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
            👤 <b style="color:#e2e8f0">{st.session_state.username}</b></div>""",
        unsafe_allow_html=True)
        page = st.radio("Nav",
            ["📊 Dashboard","➕ Add Transaction","📋 History","📅 Due Tracker"],
            label_visibility="collapsed")
        st.markdown(f'<div style="font-size:0.72rem;color:#4a5568;text-align:center;padding:0.5rem;margin-top:2rem;">📅 {datetime.now().strftime("%B %Y")}</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in=False; st.session_state.username=""; st.rerun()
    return page

# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def show_dashboard():
    df_all = db.get_user_data(st.session_state.username)
    hcol,fcol = st.columns([3,1])
    with hcol:
        st.markdown("""<div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">📊 Dashboard</div>
        <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Personal Finance Overview</div>""", unsafe_allow_html=True)
    with fcol:
        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
        chosen = st.selectbox("",DASH_FILTERS, index=DASH_FILTERS.index(st.session_state.dash_filter),
                              key="dfs", label_visibility="collapsed")
        st.session_state.dash_filter = chosen

    if df_all.empty:
        st.info("🌱 No transactions yet!"); return

    df = apply_date_filter(df_all, chosen)
    if df.empty:
        st.info(f"No transactions for: **{chosen}**"); return

    ti = df[df["Type"]=="Income"]["Amount"].sum()
    te = df[df["Type"]=="Expense"]["Amount"].sum()
    nb = ti-te
    pl = {"Last 7 Days":"Last 7 days","This Month":datetime.now().strftime("%B %Y"),
          "This Year":str(datetime.now().year),"All Transactions":"All time"}[chosen]

    c1,c2,c3 = st.columns(3)
    with c1: st.markdown(f'<div class="kpi-card kpi-income"><div class="kpi-label">💚 Total Income</div><div class="kpi-value">{fmt_inr(ti)}</div><div class="kpi-sub">{pl}</div></div>',unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="kpi-card kpi-expense"><div class="kpi-label">❤️ Total Expense</div><div class="kpi-value">{fmt_inr(te)}</div><div class="kpi-sub">{pl}</div></div>',unsafe_allow_html=True)
    with c3:
        bc="#a29bfe" if nb>=0 else "#ff6b6b"; em="✨" if nb>=0 else "⚠️"
        st.markdown(f'<div class="kpi-card kpi-balance"><div class="kpi-label">{em} Net Balance</div><div class="kpi-value" style="color:{bc}">{fmt_inr(nb)}</div><div class="kpi-sub">{"Surplus" if nb>=0 else "Deficit"} · {pl}</div></div>',unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    CHART_BG="rgba(0,0,0,0)"
    cl,cr = st.columns(2)
    idf = df[df["Type"]=="Income"].groupby("Category")["Amount"].sum()
    edf = df[df["Type"]=="Expense"].groupby("Category")["Amount"].sum()

    with cl:
        st.markdown('<div class="section-header">💚 Income Breakdown</div>',unsafe_allow_html=True)
        if not idf.empty:
            fig=go.Figure(go.Pie(labels=idf.index,values=idf.values,hole=0.62,
                marker=dict(colors=INCOME_COLORS[:len(idf)],line=dict(color='#0f1117',width=2)),
                textinfo="label+percent",textfont=dict(size=11,color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"))
            fig.update_layout(paper_bgcolor=CHART_BG,plot_bgcolor=CHART_BG,
                margin=dict(l=10,r=10,t=10,b=10),height=280,showlegend=True,
                legend=dict(font=dict(color="#a0aec0",size=10),bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(text=f"<b>{fmt_inr(ti)}</b>",x=0.5,y=0.5,font_size=15,font_color="#00b894",showarrow=False)])
            st.plotly_chart(fig,use_container_width=True)
        else: st.info("No income for this period.")

    with cr:
        st.markdown('<div class="section-header">❤️ Expense Breakdown</div>',unsafe_allow_html=True)
        if not edf.empty:
            fig2=go.Figure(go.Pie(labels=edf.index,values=edf.values,hole=0.62,
                marker=dict(colors=EXPENSE_COLORS[:len(edf)],line=dict(color='#0f1117',width=2)),
                textinfo="label+percent",textfont=dict(size=11,color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"))
            fig2.update_layout(paper_bgcolor=CHART_BG,plot_bgcolor=CHART_BG,
                margin=dict(l=10,r=10,t=10,b=10),height=280,showlegend=True,
                legend=dict(font=dict(color="#a0aec0",size=10),bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(text=f"<b>{fmt_inr(te)}</b>",x=0.5,y=0.5,font_size=15,font_color="#ff6b6b",showarrow=False)])
            st.plotly_chart(fig2,use_container_width=True)
        else: st.info("No expenses for this period.")

    st.markdown('<div class="section-header">📈 Monthly Trend (Last 6 Months)</div>',unsafe_allow_html=True)
    dt=df_all.copy(); dt["Date"]=pd.to_datetime(dt["Date"],errors="coerce")
    r6=dt[dt["Date"]>=pd.Timestamp.now()-pd.DateOffset(months=6)].copy()
    if not r6.empty:
        r6["Month"]=r6["Date"].dt.to_period("M")
        mo=r6.groupby(["Month","Type"])["Amount"].sum().unstack(fill_value=0)
        ms=[str(m) for m in mo.index]
        fig3=go.Figure()
        if "Income"  in mo.columns: fig3.add_trace(go.Bar(name="Income", x=ms,y=mo["Income"], marker_color="#00b894",opacity=0.85))
        if "Expense" in mo.columns: fig3.add_trace(go.Bar(name="Expense",x=ms,y=mo["Expense"],marker_color="#ff6b6b",opacity=0.85))
        fig3.update_layout(barmode="group",paper_bgcolor=CHART_BG,plot_bgcolor=CHART_BG,height=250,
            margin=dict(l=10,r=10,t=10,b=10),
            xaxis=dict(color="#718096",gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(color="#718096",gridcolor="rgba(255,255,255,0.04)"),
            legend=dict(font=dict(color="#a0aec0"),bgcolor="rgba(0,0,0,0)"),font=dict(color="#a0aec0"))
        st.plotly_chart(fig3,use_container_width=True)

    st.markdown('<div class="section-header">🧾 Recent Transactions (Last 10)</div>',unsafe_allow_html=True)
    rec=df.sort_values("Date",ascending=False).head(10).reset_index(drop=True)
    for idx,row in rec.iterrows():
        tc="#00b894" if row["Type"]=="Income" else "#ff6b6b"
        ti2="↑" if row["Type"]=="Income" else "↓"
        c=st.columns([1.5,1,1.5,1.2,2.5,0.7])
        with c[0]: st.markdown(f'<span style="color:#718096;font-size:0.82rem">{str(row["Date"])[:10]}</span>',unsafe_allow_html=True)
        with c[1]: st.markdown(f'<span style="color:{tc};font-weight:600;font-size:0.82rem">{ti2} {row["Type"]}</span>',unsafe_allow_html=True)
        with c[2]: st.markdown(f'<span style="color:#a0aec0;font-size:0.82rem">🏷 {row["Category"]}</span>',unsafe_allow_html=True)
        with c[3]: st.markdown(f'<span style="color:{tc};font-family:\'Space Grotesk\',sans-serif;font-weight:600">{fmt_inr(float(row["Amount"]))}</span>',unsafe_allow_html=True)
        with c[4]: st.markdown(f'<span style="color:#718096;font-size:0.8rem">{row.get("Description","")}</span>',unsafe_allow_html=True)
        with c[5]:
            if st.button("🗑️",key=f"dd_{idx}",help="Delete"):
                db.delete_row(st.session_state.username,row.get("RowIndex",-1)); st.rerun()
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.04);margin:0.2rem 0">',unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ADD TRANSACTION
# ═══════════════════════════════════════════════════════════════════════════════
def show_add_transaction():
    st.markdown("""<div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">➕ Add Transaction</div>
    <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Record a new income or expense entry</div>""",unsafe_allow_html=True)
    cf,ct=st.columns([1.6,1])
    with cf:
        entry_date=st.date_input("📅 Date",value=date.today())
        txn_type  =st.selectbox("📂 Type",["Income","Expense"])
        cats      =INCOME_CATEGORIES if txn_type=="Income" else EXPENSE_CATEGORIES
        cat_sel   =st.selectbox("🏷 Category",cats,key="add_cat")
        if cat_sel=="➕ Custom":
            cc=st.text_input("✏️ Custom category",key="add_cc",placeholder="e.g. Freelance, Medical...")
            category=cc.strip() if cc.strip() else None
            if not category: st.caption("⚠️ Please enter a category name.")
        else: category=cat_sel
        amount     =st.number_input("💵 Amount (₹)",min_value=0.0,step=10.0,format="%.2f")
        description=st.text_input("📝 Description",placeholder="Optional note...")
        if st.button(f"{'💚' if txn_type=='Income' else '❤️'} Add {txn_type}",type="primary",use_container_width=True):
            if amount<=0: st.warning("Amount must be > 0.")
            elif not category: st.warning("Enter a category name.")
            else:
                db.add_transaction(st.session_state.username,str(entry_date),txn_type,category,amount,description)
                st.success(f"✅ {txn_type} of {fmt_inr(amount)} added!"); st.balloons()
    with ct:
        bi=[c for c in INCOME_CATEGORIES if c!="➕ Custom"]
        be=[c for c in EXPENSE_CATEGORIES if c!="➕ Custom"]
        st.markdown(f"""<div style="background:linear-gradient(135deg,#1a1d2e,#16192a);border:1px solid rgba(255,255,255,0.06);
            border-radius:16px;padding:1.5rem;margin-top:0.5rem;">
            <div style="font-family:'Space Grotesk',sans-serif;font-weight:600;color:#e2e8f0;margin-bottom:1rem;">💡 Quick Tips</div>
            <div style="font-size:0.82rem;color:#718096;line-height:1.8;">
            ✅ Be consistent with categories<br>✅ Log entries daily<br>✅ Use ➕ Custom for new categories<br><br>
            <b style="color:#a0aec0">Income:</b><br><span style="color:#00b894">{"  ·  ".join(bi)}</span><br><br>
            <b style="color:#a0aec0">Expense:</b><br><span style="color:#ff6b6b">{"  ·  ".join(be)}</span>
            </div></div>""",unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# HISTORY  (filtered PDF export)
# ═══════════════════════════════════════════════════════════════════════════════
def show_history():
    df = db.get_user_data(st.session_state.username)
    hc,bc=st.columns([3,1])
    with hc:
        st.markdown("""<div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">📋 Transaction History</div>
        <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Full history · filter, edit or delete</div>""",unsafe_allow_html=True)

    if df.empty:
        with bc: st.markdown("<div style='height:0.3rem'></div>",unsafe_allow_html=True)
        st.info("No transactions found."); return

    df["Date"]=pd.to_datetime(df["Date"],errors="coerce")
    df=df.sort_values("Date",ascending=False).reset_index(drop=True)

    # Filters
    f1,f2,f3=st.columns(3)
    with f1: tf=st.selectbox("Filter by Type",["All","Income","Expense"])
    with f2: cf2=st.selectbox("Filter by Category",["All"]+sorted(df["Category"].unique().tolist()))
    with f3:
        months=["All"]+sorted(df["Date"].dt.to_period("M").astype(str).unique().tolist(),reverse=True)
        mf=st.selectbox("Filter by Month",months)

    filtered=df.copy()
    if tf !="All": filtered=filtered[filtered["Type"]==tf]
    if cf2!="All": filtered=filtered[filtered["Category"]==cf2]
    if mf !="All": filtered=filtered[filtered["Date"].dt.to_period("M").astype(str)==mf]

    # Build filter label for PDF
    parts=[]
    if tf !="All": parts.append(tf)
    if cf2!="All": parts.append(cf2)
    if mf !="All": parts.append(mf)
    filter_label=" · ".join(parts) if parts else "All Transactions"

    # PDF button — exports ONLY the filtered rows
    with bc:
        st.markdown("<div style='height:0.3rem'></div>",unsafe_allow_html=True)
        if not filtered.empty:
            pdf_data=generate_pdf(filtered,st.session_state.username,filter_label)
            st.download_button(
                label="📥 Export PDF",
                data=pdf_data,
                file_name=f"bills_{st.session_state.username}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

    st.markdown(f"""<div style="font-size:0.82rem;color:#718096;margin-bottom:0.8rem;">
        Showing <b style="color:#a0aec0">{len(filtered)}</b> transactions ·
        <b style="color:#00b894">₹{filtered[filtered['Type']=='Income']['Amount'].sum():,.0f} income</b> /
        <b style="color:#ff6b6b">₹{filtered[filtered['Type']=='Expense']['Amount'].sum():,.0f} expense</b>
    </div>""",unsafe_allow_html=True)

    # Inline edit form
    if st.session_state.editing_row is not None:
        erow=st.session_state.editing_row
        st.markdown("""<div style="background:linear-gradient(135deg,#0d2818,#1a1d2e);
            border:1px solid rgba(0,184,148,0.4);border-radius:14px;padding:1rem 1.2rem 0.5rem 1.2rem;margin-bottom:1rem;">""",unsafe_allow_html=True)
        st.markdown('<div style="font-family:\'Space Grotesk\',sans-serif;font-weight:600;color:#00b894;margin-bottom:0.8rem;">✏️ Editing Transaction</div>',unsafe_allow_html=True)
        ec1,ec2,ec3=st.columns(3)
        with ec1: ed=st.date_input("Date",value=pd.to_datetime(erow["Date"]).date(),key="e_date")
        with ec2: et=st.selectbox("Type",["Income","Expense"],index=0 if erow["Type"]=="Income" else 1,key="e_type")
        with ec3:
            ecats=INCOME_CATEGORIES if et=="Income" else EXPENSE_CATEGORIES
            bcats=[c for c in ecats if c!="➕ Custom"]
            cc=erow["Category"]
            di=bcats.index(cc) if cc in bcats else len(ecats)-1
            ecs=st.selectbox("Category",ecats,index=di,key="e_cat")
            if ecs=="➕ Custom":
                ec_in=st.text_input("Custom",value=cc if cc not in bcats else "",key="e_cc")
                ecat=ec_in.strip() or cc
            else: ecat=ecs
        ec4,ec5=st.columns(2)
        with ec4: ea=st.number_input("Amount (₹)",value=float(erow["Amount"]),min_value=0.0,step=10.0,format="%.2f",key="e_amt")
        with ec5: edesc=st.text_input("Description",value=str(erow.get("Description","")),key="e_dsc")
        sa,sb=st.columns(2)
        with sa:
            if st.button("💾 Save",type="primary",use_container_width=True):
                if ea<=0: st.warning("Amount must be > 0")
                else:
                    db.update_row(st.session_state.username,int(erow["RowIndex"]),str(ed),et,ecat,ea,edesc)
                    st.session_state.editing_row=None; st.success("✅ Updated!"); st.rerun()
        with sb:
            if st.button("✖ Cancel",use_container_width=True):
                st.session_state.editing_row=None; st.rerun()
        st.markdown("</div>",unsafe_allow_html=True)

    # Transaction rows
    for idx,row in filtered.iterrows():
        tc="#00b894" if row["Type"]=="Income" else "#ff6b6b"
        ti="↑" if row["Type"]=="Income" else "↓"
        c=st.columns([1.4,1.1,1.5,1.2,2.2,0.55,0.55])
        with c[0]: st.markdown(f'<span style="color:#718096;font-size:0.82rem">{str(row["Date"])[:10]}</span>',unsafe_allow_html=True)
        with c[1]: st.markdown(f'<span style="color:{tc};font-weight:600;font-size:0.82rem">{ti} {row["Type"]}</span>',unsafe_allow_html=True)
        with c[2]: st.markdown(f'<span style="color:#a0aec0;font-size:0.82rem">🏷 {row["Category"]}</span>',unsafe_allow_html=True)
        with c[3]: st.markdown(f'<span style="color:{tc};font-family:\'Space Grotesk\',sans-serif;font-weight:600">{fmt_inr(float(row["Amount"]))}</span>',unsafe_allow_html=True)
        with c[4]: st.markdown(f'<span style="color:#718096;font-size:0.8rem">{row.get("Description","")}</span>',unsafe_allow_html=True)
        with c[5]:
            if st.button("✏️",key=f"e_{idx}",help="Edit"):
                st.session_state.editing_row=row.to_dict(); st.rerun()
        with c[6]:
            if st.button("🗑️",key=f"d_{idx}",help="Delete"):
                db.delete_row(st.session_state.username,row.get("RowIndex",-1))
                st.session_state.editing_row=None; st.rerun()
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.04);margin:0.2rem 0">',unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# DUE DATE TRACKER
# ═══════════════════════════════════════════════════════════════════════════════
def show_due_tracker():
    st.markdown("""<div style="font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:0.2rem;">📅 Due Date Tracker</div>
    <div style="color:#718096;font-size:0.85rem;margin-bottom:1.5rem;">Track money taken and given · mark as settled when done</div>""",unsafe_allow_html=True)

    dues_df = db.get_user_dues(st.session_state.username)

    # ── Summary Grid ─────────────────────────────────────────────────────────
    active = dues_df[dues_df["Status"]=="Active"] if not dues_df.empty else pd.DataFrame()
    total_taken = active[active["DueType"]=="Money Taken"]["Amount"].sum() if not active.empty else 0
    total_given = active[active["DueType"]=="Money Given"]["Amount"].sum() if not active.empty else 0
    net_due     = total_taken - total_given  # positive = you owe more than you're owed

    c1,c2,c3 = st.columns(3)
    with c1: st.markdown(f'<div class="kpi-card kpi-taken"><div class="kpi-label">🔴 Money Taken (You Owe)</div><div class="kpi-value">{fmt_inr(total_taken)}</div><div class="kpi-sub">Active dues only</div></div>',unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="kpi-card kpi-given"><div class="kpi-label">🟢 Money Given (Owed to You)</div><div class="kpi-value">{fmt_inr(total_given)}</div><div class="kpi-sub">Active dues only</div></div>',unsafe_allow_html=True)
    with c3:
        nc="#ff6b6b" if net_due>0 else "#00b894"
        nl="You Owe Net" if net_due>0 else "Net Receivable"
        st.markdown(f'<div class="kpi-card kpi-balance"><div class="kpi-label">⚖️ {nl}</div><div class="kpi-value" style="color:{nc}">{fmt_inr(abs(net_due))}</div><div class="kpi-sub">Taken minus Given</div></div>',unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # ── Add New Due ───────────────────────────────────────────────────────────
    with st.expander("➕ Add New Due Entry", expanded=dues_df.empty):
        d1,d2 = st.columns(2)
        with d1:
            due_type   = st.selectbox("💸 Type", ["Money Taken","Money Given"],
                                      help="Money Taken = you borrowed | Money Given = you lent")
            due_amount = st.number_input("💵 Amount (₹)", min_value=0.0, step=10.0, format="%.2f", key="due_amt")
        with d2:
            due_desc  = st.text_input("📝 Description / Person Name", placeholder="e.g. From Rahul, Laptop loan...")
            due_start = st.date_input("📅 Start Date", value=date.today(), key="due_start")
        if st.button("💾 Add Due Entry", type="primary", use_container_width=True):
            if due_amount<=0: st.warning("Amount must be > 0")
            elif not due_desc.strip(): st.warning("Please add a description or person name.")
            else:
                db.add_due(st.session_state.username, due_type, due_amount, due_desc.strip(), str(due_start))
                st.success(f"✅ Due entry added — {fmt_inr(due_amount)} ({due_type})"); st.rerun()

    # ── Due Entries List ──────────────────────────────────────────────────────
    if dues_df.empty:
        st.info("No due entries yet. Add your first entry above.")
        return

    dues_df["StartDate"] = pd.to_datetime(dues_df["StartDate"], errors="coerce")

    # Tabs: Active / Settled / All
    tab_active, tab_settled, tab_all = st.tabs(["🟡 Active", "✅ Settled", "📋 All"])

    def render_dues(ddf, show_settle=True):
        if ddf.empty:
            st.info("No entries here."); return
        for idx, row in ddf.iterrows():
            elapsed = days_elapsed(row["StartDate"])
            is_taken = row["DueType"] == "Money Taken"
            tc = "#ff6b6b" if is_taken else "#00b894"
            icon = "🔴" if is_taken else "🟢"
            settled = row["Status"] == "Settled"

            # Row card
            st.markdown(f"""
            <div style="background:{'rgba(255,107,107,0.06)' if is_taken else 'rgba(0,184,148,0.06)'};
                border:1px solid {'rgba(255,107,107,0.2)' if is_taken else 'rgba(0,184,148,0.2)'};
                border-radius:10px; padding:0.8rem 1rem; margin-bottom:0.5rem;
                {'opacity:0.55;' if settled else ''}">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">
                    <div>
                        <span style="color:{tc};font-weight:700;font-size:0.9rem;">{icon} {row['DueType']}</span>
                        <span style="color:#e2e8f0;font-family:'Space Grotesk',sans-serif;font-size:1.1rem;font-weight:700;margin-left:1rem;">{fmt_inr(float(row['Amount']))}</span>
                    </div>
                    <div style="color:#718096;font-size:0.8rem;">
                        📅 {str(row['StartDate'])[:10]} &nbsp;·&nbsp;
                        ⏱ <b style="color:{'#fdcb6e' if elapsed>30 else '#a0aec0'}">{elapsed} days</b> elapsed
                        &nbsp;·&nbsp; <span style="color:{'#00b894' if settled else '#fdcb6e'};font-weight:600;">{'✅ Settled' if settled else '🕐 Active'}</span>
                    </div>
                </div>
                <div style="color:#a0aec0;font-size:0.83rem;margin-top:0.4rem;">📝 {row.get('Description','')}</div>
            </div>""", unsafe_allow_html=True)

            # Action buttons
            ac1, ac2, ac3 = st.columns([2,1,1])
            with ac2:
                if show_settle and not settled:
                    if st.button("✅ Settle", key=f"settle_{idx}", use_container_width=True):
                        db.update_due_status(st.session_state.username, int(row["RowIndex"]), "Settled")
                        st.rerun()
                elif settled:
                    if st.button("🔄 Reopen", key=f"reopen_{idx}", use_container_width=True):
                        db.update_due_status(st.session_state.username, int(row["RowIndex"]), "Active")
                        st.rerun()
            with ac3:
                if st.button("🗑️ Delete", key=f"ddel_{idx}", use_container_width=True):
                    db.delete_due(st.session_state.username, int(row["RowIndex"]))
                    st.rerun()

    with tab_active:
        active_dues = dues_df[dues_df["Status"]=="Active"]
        st.markdown(f'<div style="color:#718096;font-size:0.82rem;margin-bottom:0.8rem;">{len(active_dues)} active due(s)</div>', unsafe_allow_html=True)
        render_dues(active_dues, show_settle=True)

    with tab_settled:
        settled_dues = dues_df[dues_df["Status"]=="Settled"]
        st.markdown(f'<div style="color:#718096;font-size:0.82rem;margin-bottom:0.8rem;">{len(settled_dues)} settled due(s)</div>', unsafe_allow_html=True)
        render_dues(settled_dues, show_settle=False)

    with tab_all:
        st.markdown(f'<div style="color:#718096;font-size:0.82rem;margin-bottom:0.8rem;">{len(dues_df)} total due(s)</div>', unsafe_allow_html=True)
        render_dues(dues_df, show_settle=True)

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
    elif "Due"       in page: show_due_tracker()
