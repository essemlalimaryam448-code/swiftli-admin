"""
Swiftli — Tableau de bord Admin (Streamlit) — v2.0 Full Control
================================================================
Synchronisé avec Firestore (users, demandes, trajets, reclamations)
+ photos KYC depuis Supabase Storage
"""

import math
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ─── Secrets ─────────────────────────────────────────────────────────────────
def _secret(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)

FIREBASE_API_KEY = "AIzaSyAxis8YbztfBsTWbDz4hNKJOvOsNETWlus"
FIREBASE_PROJECT = "swiftly-4ca00"
FIRESTORE_BASE   = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"
AUTH_URL         = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"

SUPABASE_URL = _secret("SUPABASE_URL", "https://xtywsvuxdydootflotmr.supabase.co").rstrip("/")
SUPABASE_KEY = _secret("SUPABASE_SERVICE_KEY")

# Liste d'emails autorisés à accéder au dashboard admin (séparés par virgule).
# Si vide, on vérifie le champ role="admin" dans Firestore.
ADMIN_EMAILS = [e.strip().lower() for e in _secret("ADMIN_EMAILS", "").split(",") if e.strip()]

# Face++ pour la vérification automatique de visage (CIN ↔ photo profil)
# Inscription gratuite : https://www.faceplusplus.com/  (30 000 appels/mois)
FACEPP_KEY    = _secret("FACEPP_API_KEY")
FACEPP_SECRET = _secret("FACEPP_API_SECRET")
FACE_MATCH_THRESHOLD = 70.0  # Score minimum pour considérer comme match (0-100)

# ─── Couleurs (thème BRUN / CAFÉ) ─────────────────────────────────────────────
# Les noms GREEN/GREEN_D sont conservés pour ne pas casser le reste du code,
# mais contiennent désormais des teintes brunes.
GREEN   = "#8D6E63"   # Brun moka (couleur primaire)
GREEN_D = "#4E342E"   # Brun espresso (couleur foncée)
AMBER   = "#C8860D"   # Or/caramel (accent)
RED     = "#B5482F"   # Brique (alertes)
BLUE    = "#795548"   # Brun terre (remplace le bleu)

# Palette brune harmonisée pour les graphiques
BROWN_PALETTE = ["#8D6E63", "#C8860D", "#A1745C", "#5D4037",
                 "#B5482F", "#4E342E", "#D7B89C", "#6F4E37"]


def _style_chart(fig, height: int = 320, show_legend: bool = True):
    """Applique un style café cohérent, transparent et lisible à un graphique Plotly."""
    fig.update_layout(
        height=height,
        margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, sans-serif", size=13, color="#4E342E"),
        showlegend=show_legend,
        legend=dict(
            orientation="v",
            font=dict(size=12, color="#5D4037"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="#4E342E",
            font=dict(color="white", size=13),
            bordercolor="#4E342E",
        ),
        transition={"duration": 500, "easing": "cubic-in-out"},
    )
    fig.update_xaxes(showgrid=False, zeroline=False,
                     tickfont=dict(color="#5D4037", size=12),
                     linecolor="#D7CCC8")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(141,110,99,0.15)",
                     zeroline=False, tickfont=dict(color="#5D4037", size=12))
    return fig

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Swiftli Admin", page_icon="📦", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown(f"""
<style>
  /* ─── Global page styling (thème BRUN crème) ─────────────── */
  .stApp {{
      background: linear-gradient(180deg, #FAF6F1 0%, #F5EFE8 100%);
  }}

  /* Force text colors visible on cream background */
  .stApp, .stApp p, .stApp span, .stApp div, .stApp label {{
      color: #3E2723 !important;
  }}

  /* Force headers brun espresso */
  .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {{
      color: #4E342E !important;
      font-weight: 800 !important;
  }}

  /* Subheader text */
  .stApp [data-testid="stMarkdownContainer"] p {{
      color: #5D4037 !important;
  }}

  /* Caption / small text */
  .stApp small {{
      color: #6D4C41 !important;
  }}

  /* Hide Streamlit branding for a cleaner look */
  #MainMenu {{ visibility: hidden; }}
  footer {{ visibility: hidden; }}
  .stDeployButton {{ display: none; }}

  /* ─── Sidebar premium ────────────────────────────────────── */
  [data-testid="stSidebar"] {{
      background: linear-gradient(165deg, {GREEN_D} 0%, #062e1e 100%);
      box-shadow: 4px 0 24px rgba(15, 110, 86, 0.15);
  }}
  [data-testid="stSidebar"] * {{ color: white !important; }}
  [data-testid="stSidebar"] [data-testid="stRadio"] label {{
      padding: 10px 14px;
      border-radius: 10px;
      transition: all 0.2s ease;
      margin: 2px 0;
  }}
  [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
      background: rgba(255, 255, 255, 0.1);
      transform: translateX(4px);
  }}
  [data-testid="stSidebar"] hr {{
      border-color: rgba(255, 255, 255, 0.15);
      margin: 16px 0;
  }}

  /* ─── KPI Metric cards premium ───────────────────────────── */
  [data-testid="metric-container"] {{
      background: white !important;
      border: 1px solid #E5E7EB;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 2px 12px rgba(15, 110, 86, 0.06);
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
  }}
  [data-testid="metric-container"]:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(15, 110, 86, 0.12);
      border-color: {GREEN};
  }}
  [data-testid="metric-container"]::before {{
      content: '';
      position: absolute;
      top: 0; left: 0;
      width: 4px;
      height: 100%;
      background: linear-gradient(180deg, {GREEN}, {GREEN_D});
  }}
  [data-testid="stMetricValue"], [data-testid="stMetricValue"] div {{
      font-size: 2rem !important;
      font-weight: 800 !important;
      color: {GREEN_D} !important;
  }}
  [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] div, [data-testid="stMetricLabel"] p {{
      font-size: 0.85rem !important;
      color: #5D4037 !important;
      font-weight: 700 !important;
      text-transform: uppercase;
      letter-spacing: 0.5px;
  }}
  [data-testid="stMetricDelta"] {{
      color: #059669 !important;
      font-weight: 700 !important;
  }}

  /* Hero cards : forcer le texte BLANC */
  div[style*="linear-gradient"] h1,
  div[style*="linear-gradient"] h2,
  div[style*="linear-gradient"] h3,
  div[style*="linear-gradient"] p,
  div[style*="linear-gradient"] span {{
      color: white !important;
  }}

  /* Sidebar : forcer texte BLANC partout (priorité max) */
  section[data-testid="stSidebar"] *,
  section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *,
  section[data-testid="stSidebar"] [role="radiogroup"] label,
  section[data-testid="stSidebar"] [role="radiogroup"] label *,
  section[data-testid="stSidebar"] [data-baseweb="radio"] *,
  section[data-testid="stSidebar"] [data-testid="stRadio"] * {{
      color: #FFFFFF !important;
      font-weight: 600 !important;
  }}
  section[data-testid="stSidebar"] [role="radiogroup"] label {{
      font-size: 0.95rem !important;
      padding: 12px 14px !important;
      border-radius: 10px !important;
      margin: 3px 0 !important;
  }}
  section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
      background: rgba(255,255,255,0.18) !important;
  }}
  section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
      background: rgba(255,255,255,0.22) !important;
  }}

  /* ─── Section titles premium ─────────────────────────────── */
  .section-title {{
      font-size: 1.4rem;
      font-weight: 800;
      color: {GREEN_D};
      margin-bottom: 1.2rem;
      padding-bottom: 10px;
      border-bottom: 3px solid {GREEN};
      display: inline-block;
      position: relative;
  }}
  .section-title::after {{
      content: '';
      position: absolute;
      bottom: -3px;
      left: 0;
      width: 30%;
      height: 3px;
      background: {AMBER};
      border-radius: 2px;
  }}

  /* ─── Badges modernes ────────────────────────────────────── */
  .badge-pending {{
      background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%);
      color: #92400E;
      padding: 4px 12px;
      border-radius: 99px;
      font-size: 0.8rem;
      font-weight: 700;
      box-shadow: 0 1px 3px rgba(146, 64, 14, 0.1);
  }}
  .badge-approved {{
      background: linear-gradient(135deg, #E8DDD3 0%, #D7CCC8 100%);
      color: #4E342E;
      padding: 4px 12px;
      border-radius: 99px;
      font-size: 0.8rem;
      font-weight: 700;
      box-shadow: 0 1px 3px rgba(6, 95, 70, 0.1);
  }}
  .badge-rejected {{
      background: linear-gradient(135deg, #FEE2E2 0%, #FCA5A5 100%);
      color: #991B1B;
      padding: 4px 12px;
      border-radius: 99px;
      font-size: 0.8rem;
      font-weight: 700;
      box-shadow: 0 1px 3px rgba(153, 27, 27, 0.1);
  }}

  /* ─── Boutons stylés ──────────────────────────────────────── */
  .stButton > button {{
      border-radius: 10px;
      font-weight: 600;
      padding: 0.6rem 1.2rem;
      transition: all 0.2s ease;
      border: 1px solid transparent;
  }}
  .stButton > button:hover {{
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(15, 110, 86, 0.15);
  }}
  .stButton > button[kind="primary"] {{
      background: linear-gradient(135deg, {GREEN} 0%, {GREEN_D} 100%);
      color: white;
      border: none;
  }}

  /* ─── Expander modernisé ──────────────────────────────────── */
  [data-testid="stExpander"] {{
      border: 1px solid #E5E7EB;
      border-radius: 14px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      margin-bottom: 12px;
      overflow: hidden;
      transition: all 0.2s ease;
  }}
  [data-testid="stExpander"]:hover {{
      box-shadow: 0 4px 12px rgba(15, 110, 86, 0.08);
      border-color: {GREEN};
  }}

  /* ─── Inputs ──────────────────────────────────────────────── */
  .stTextInput input, .stSelectbox select, .stTextArea textarea {{
      border-radius: 10px !important;
      border: 1.5px solid #E5E7EB !important;
      transition: all 0.2s ease;
      color: #3E2723 !important;
      background: white !important;
  }}
  .stTextInput input:focus, .stSelectbox select:focus, .stTextArea textarea:focus {{
      border-color: {GREEN} !important;
      box-shadow: 0 0 0 3px rgba(15, 110, 86, 0.1) !important;
  }}

  /* Selectbox dropdown */
  [data-baseweb="select"] > div {{
      background: white !important;
      color: #3E2723 !important;
  }}
  [data-baseweb="select"] * {{ color: #3E2723 !important; }}
  [data-baseweb="popover"] li {{ color: #3E2723 !important; }}

  /* Number input */
  .stNumberInput input {{
      color: #3E2723 !important;
      background: white !important;
  }}

  /* Labels au-dessus des inputs */
  .stTextInput label, .stSelectbox label, .stTextArea label,
  .stNumberInput label, .stRadio label, .stCheckbox label,
  .stFileUploader label {{
      color: #5D4037 !important;
      font-weight: 600 !important;
  }}

  /* Sidebar inputs : texte blanc */
  [data-testid="stSidebar"] .stTextInput input,
  [data-testid="stSidebar"] .stSelectbox select {{
      color: white !important;
      background: rgba(255,255,255,0.1) !important;
      border-color: rgba(255,255,255,0.2) !important;
  }}

  /* ─── DataFrames ─────────────────────────────────────────── */
  [data-testid="stDataFrame"] {{
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
      border: 1px solid #E5E7EB;
  }}

  /* ─── Alerts / Info boxes ────────────────────────────────── */
  .stAlert {{
      border-radius: 12px;
      border-left-width: 4px;
  }}

  /* ─── Tabs ───────────────────────────────────────────────── */
  .stTabs [data-baseweb="tab-list"] {{
      gap: 8px;
      background: white;
      padding: 6px;
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }}
  .stTabs [data-baseweb="tab"] {{
      border-radius: 8px;
      padding: 8px 16px;
      font-weight: 600;
  }}
  .stTabs [aria-selected="true"] {{
      background: linear-gradient(135deg, {GREEN} 0%, {GREEN_D} 100%);
      color: white !important;
  }}

  /* ─── Custom photo cards for KYC ─────────────────────────── */
  .kyc-photo-card {{
      background: white;
      border: 2px solid #E5E7EB;
      border-radius: 14px;
      padding: 8px;
      transition: all 0.2s ease;
      cursor: zoom-in;
  }}
  .kyc-photo-card:hover {{
      border-color: {GREEN};
      transform: scale(1.02);
      box-shadow: 0 8px 24px rgba(15, 110, 86, 0.15);
  }}

  /* ─── User card style ────────────────────────────────────── */
  .user-card {{
      background: white;
      border: 1px solid #E5E7EB;
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      transition: all 0.2s ease;
  }}
  .user-card:hover {{
      box-shadow: 0 4px 12px rgba(15, 110, 86, 0.08);
      border-color: {GREEN};
  }}

  /* ─── Stat hero ──────────────────────────────────────────── */
  .stat-hero {{
      background: linear-gradient(135deg, {GREEN} 0%, {GREEN_D} 100%);
      color: white;
      padding: 24px;
      border-radius: 16px;
      box-shadow: 0 8px 24px rgba(15, 110, 86, 0.2);
      margin-bottom: 20px;
  }}
  .stat-hero h2 {{
      color: white;
      font-size: 2rem;
      margin: 0;
      font-weight: 800;
  }}
  .stat-hero p {{
      color: rgba(255,255,255,0.9);
      margin: 4px 0 0 0;
      font-size: 0.95rem;
  }}

  /* ─── Cartes du Centre de décision ───────────────────────── */
  .decision-card {{
      border-radius: 16px;
      padding: 18px 20px;
      height: 130px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 4px 14px rgba(78, 52, 46, 0.10);
      transition: all 0.25s ease;
      overflow: hidden;
  }}
  .decision-card:hover {{
      transform: translateY(-3px);
      box-shadow: 0 8px 22px rgba(78, 52, 46, 0.18);
  }}
  .decision-card .dc-head {{
      display: flex;
      align-items: center;
      gap: 8px;
  }}
  .decision-card .dc-icon {{ font-size: 1.5rem; line-height: 1; }}
  .decision-card .dc-title {{
      font-weight: 800 !important;
      font-size: 0.92rem !important;
      letter-spacing: 0.2px;
  }}
  .decision-card .dc-value {{
      font-size: 2.4rem !important;
      font-weight: 900 !important;
      line-height: 1 !important;
      margin: 4px 0;
  }}
  .decision-card .dc-sub {{
      font-size: 0.78rem !important;
      font-weight: 600 !important;
      opacity: 0.85;
  }}
  /* Variantes de couleur — texte forcé pour passer outre le CSS global */
  .dc-warn {{ background: linear-gradient(135deg, #F3E2C7 0%, #E8C98F 100%); }}
  .dc-warn .dc-title, .dc-warn .dc-value, .dc-warn .dc-sub {{ color: #6D4C11 !important; }}
  .dc-danger {{ background: linear-gradient(135deg, #F3D4CC 0%, #E0A99B 100%); }}
  .dc-danger .dc-title, .dc-danger .dc-value, .dc-danger .dc-sub {{ color: #7B2D1A !important; }}
  .dc-ok {{ background: linear-gradient(135deg, #E3D7C9 0%, #CDBBA6 100%); }}
  .dc-ok .dc-title, .dc-ok .dc-value, .dc-ok .dc-sub {{ color: #4E342E !important; }}
  .dc-primary {{ background: linear-gradient(135deg, #8D6E63 0%, #4E342E 100%); }}
  .dc-primary .dc-title, .dc-primary .dc-value, .dc-primary .dc-sub {{ color: #FFFFFF !important; }}

  /* Titre de section interne */
  .inner-section-title {{
      font-size: 1.25rem !important;
      font-weight: 800 !important;
      color: #4E342E !important;
      margin: 6px 0 16px;
      display: flex;
      align-items: center;
      gap: 8px;
  }}
</style>
""", unsafe_allow_html=True)


# ─── Firebase REST helpers ────────────────────────────────────────────────────
def firebase_login(email: str, password: str) -> dict:
    r = requests.post(AUTH_URL, json={"email": email, "password": password,
                                      "returnSecureToken": True}, timeout=10)
    if r.status_code == 200:
        return r.json()
    raise ValueError(r.json().get("error", {}).get("message", "Erreur inconnue"))

def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def fs_get(collection: str, token: str) -> list:
    r = requests.get(f"{FIRESTORE_BASE}/{collection}", headers=_auth_headers(token), timeout=15)
    if r.status_code != 200:
        return []
    return [_parse_doc(d) for d in r.json().get("documents", [])]

def fs_patch(collection: str, doc_id: str, fields: dict, token: str):
    url = f"{FIRESTORE_BASE}/{collection}/{doc_id}"
    body = {"fields": {k: _to_fs(v) for k, v in fields.items()}}
    mask = "&".join(f"updateMask.fieldPaths={k}" for k in fields)
    requests.patch(f"{url}?{mask}", json=body, headers=_auth_headers(token), timeout=10)

def fs_delete(collection: str, doc_id: str, token: str):
    url = f"{FIRESTORE_BASE}/{collection}/{doc_id}"
    requests.delete(url, headers=_auth_headers(token), timeout=10)

def fs_add(collection: str, data: dict, token: str):
    body = {"fields": {k: _to_fs(v) for k, v in data.items()}}
    requests.post(f"{FIRESTORE_BASE}/{collection}", json=body,
                  headers=_auth_headers(token), timeout=10)

def _parse_doc(doc: dict) -> dict:
    name = doc.get("name", "")
    result = {"_id": name.split("/")[-1]}
    for key, val in doc.get("fields", {}).items():
        result[key] = _from_fs(val)
    return result

def _from_fs(val: dict):
    if "stringValue"    in val: return val["stringValue"]
    if "integerValue"   in val: return int(val["integerValue"])
    if "doubleValue"    in val: return float(val["doubleValue"])
    if "booleanValue"   in val: return val["booleanValue"]
    if "timestampValue" in val: return val["timestampValue"]
    if "nullValue"      in val: return None
    if "mapValue"       in val:
        return {k: _from_fs(v) for k, v in val["mapValue"].get("fields", {}).items()}
    if "arrayValue"     in val:
        return [_from_fs(v) for v in val["arrayValue"].get("values", [])]
    return str(val)

def _to_fs(v) -> dict:
    if isinstance(v, bool):  return {"booleanValue": v}
    if isinstance(v, int):   return {"integerValue": str(v)}
    if isinstance(v, float): return {"doubleValue": v}
    if v is None:            return {"nullValue": None}
    return {"stringValue": str(v)}

def _token() -> str:
    return st.session_state.get("id_token", "")


# ─── Supabase Storage ─────────────────────────────────────────────────────────
def _supa_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"}

@st.cache_data(ttl=3000, show_spinner=False)
def _signed_url(public_url: str) -> str:
    """Convertit une URL publique Supabase en URL signée valide 1h.
    Fonctionne même si le bucket est privé. Retourne l'URL originale si conversion échoue."""
    if not public_url or "supabase" not in public_url:
        return public_url
    if not SUPABASE_KEY:
        return public_url
    try:
        from urllib.parse import urlparse
        clean_url = public_url.split("?")[0]
        parsed = urlparse(clean_url)
        parts = parsed.path.strip("/").split("/")
        # Format: storage/v1/object/{public|sign}/{bucket}/{path}
        if len(parts) < 6 or parts[0] != "storage":
            return public_url
        bucket = parts[4]
        file_path = "/".join(parts[5:])

        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{file_path}",
            headers={"apikey": SUPABASE_KEY,
                     "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json={"expiresIn": 3600},
            timeout=8,
        )
        if r.status_code == 200:
            signed_path = r.json().get("signedURL", "")
            if signed_path:
                if signed_path.startswith("/"):
                    return f"{SUPABASE_URL}/storage/v1{signed_path}"
                return f"{SUPABASE_URL}/storage/v1/{signed_path}"
    except Exception:
        pass
    return public_url


def _photo(url: str | None, label: str):
    """Affiche une photo KYC — utilise URL signée pour garantir l'accès."""
    # Label avec style amélioré
    st.markdown(f"""
    <div style="
        font-weight: 700;
        color: {GREEN_D};
        font-size: 0.85rem;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    ">{label}</div>
    """, unsafe_allow_html=True)

    if not url:
        st.markdown(
            """<div style='
                background: linear-gradient(135deg, #F3F4F6 0%, #E5E7EB 100%);
                border: 2px dashed #D1D5DB;
                border-radius: 14px;
                height: 180px;
                display: flex; flex-direction: column;
                align-items: center; justify-content: center;
                color: #9CA3AF;
                font-size: 13px;
                font-weight: 600;
            '>
                <div style='font-size: 2rem; margin-bottom: 8px; opacity: 0.5;'>📷</div>
                Non fourni
            </div>""",
            unsafe_allow_html=True)
        return

    display_url = _signed_url(url)
    try:
        # Container avec style premium pour la photo
        st.markdown('<div class="kyc-photo-card">', unsafe_allow_html=True)
        st.image(display_url, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <a href='{display_url}' target='_blank' style='
            display: inline-block;
            margin-top: 8px;
            padding: 4px 10px;
            background: #F5EFE8;
            color: {GREEN_D};
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 600;
            text-decoration: none;
            border: 1px solid #E8DDD3;
            transition: all 0.2s ease;
        '>🔍 Plein écran</a>
        """, unsafe_allow_html=True)
    except Exception as e:
        st.error("⚠️ Photo inaccessible")
        st.markdown(f"[Voir le fichier directement]({display_url})")
        st.caption(f"_{str(e)[:80]}_")


# ─── Face++ : vérification de correspondance de visage ────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _face_compare(url1: str, url2: str) -> dict:
    """Compare 2 photos via Face++ et retourne {confidence, error}.
    confidence : 0-100 (>= FACE_MATCH_THRESHOLD = match probable)."""
    if not (url1 and url2):
        return {"confidence": None, "error": "URL manquante"}
    if not (FACEPP_KEY and FACEPP_SECRET):
        return {"confidence": None, "error": "Face++ non configuré"}
    try:
        # Convertit en URLs signées (accessibles publiquement par Face++)
        u1 = _signed_url(url1)
        u2 = _signed_url(url2)
        r = requests.post(
            "https://api-us.faceplusplus.com/facepp/v3/compare",
            data={
                "api_key":     FACEPP_KEY,
                "api_secret":  FACEPP_SECRET,
                "image_url1":  u1,
                "image_url2":  u2,
            },
            timeout=20,
        )
        data = r.json()
        if "error_message" in data:
            return {"confidence": None, "error": data["error_message"]}
        return {"confidence": float(data.get("confidence", 0)), "error": None}
    except Exception as e:
        return {"confidence": None, "error": str(e)[:120]}


def _face_match_badge(confidence: float | None, error: str | None) -> str:
    """Génère un badge HTML pour le score de correspondance."""
    if confidence is None:
        return (f"<div style='background:#F3F4F6;color:#6B7280;padding:8px 12px;"
                f"border-radius:8px;font-size:13px'>⚙️ Vérification visage : "
                f"<i>{error or 'non disponible'}</i></div>")
    if confidence >= FACE_MATCH_THRESHOLD:
        return (f"<div style='background:#E8DDD3;color:#4E342E;padding:10px 14px;"
                f"border-radius:8px;font-weight:600'>"
                f"✅ Visages correspondants — confiance {confidence:.1f}%</div>")
    return (f"<div style='background:#FEE2E2;color:#991B1B;padding:10px 14px;"
            f"border-radius:8px;font-weight:600'>"
            f"❌ Visages NON correspondants — confiance {confidence:.1f}% "
            f"(seuil: {FACE_MATCH_THRESHOLD}%)</div>")


# ─── Login ────────────────────────────────────────────────────────────────────
def login_page():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"""
        <div style="text-align:center;padding:60px 0 24px">
            <div style="
                width: 90px; height: 90px;
                margin: 0 auto 24px;
                background: linear-gradient(135deg, {GREEN} 0%, {GREEN_D} 100%);
                border-radius: 24px;
                display: flex; align-items: center; justify-content: center;
                font-size: 3.5rem;
                box-shadow: 0 12px 30px rgba(15, 110, 86, 0.3);
            ">📦</div>
            <h1 style="
                color: {GREEN_D};
                margin: 0;
                font-size: 2.5rem;
                font-weight: 900;
                letter-spacing: -1px;
            ">Swiftli Admin</h1>
            <p style="
                color: #6B7280;
                margin-top: 8px;
                font-size: 1rem;
            ">Tableau de bord administrateur — Sécurisé</p>
            <div style="
                display: inline-block;
                margin-top: 12px;
                padding: 4px 12px;
                background: linear-gradient(135deg, #E8DDD3 0%, #D7CCC8 100%);
                color: #4E342E;
                border-radius: 99px;
                font-size: 0.75rem;
                font-weight: 700;
                letter-spacing: 0.5px;
            ">🔒 ACCÈS RESTREINT</div>
        </div>""", unsafe_allow_html=True)
        with st.form("login"):
            email    = st.text_input("📧 Email", placeholder="votre@email.com")
            password = st.text_input("🔑 Mot de passe", type="password")
            ok       = st.form_submit_button("Se connecter", use_container_width=True, type="primary")
        if ok:
            if not email or not password:
                st.warning("Remplissez email et mot de passe.")
            else:
                try:
                    with st.spinner("Connexion..."):
                        data = firebase_login(email, password)

                    # Vérification du rôle admin
                    email_lower = email.strip().lower()
                    is_admin = False
                    if ADMIN_EMAILS:
                        # Mode 1 : whitelist d'emails dans .env
                        is_admin = email_lower in ADMIN_EMAILS
                    else:
                        # Mode 2 : vérification du champ role="admin" dans Firestore
                        try:
                            r = requests.get(
                                f"{FIRESTORE_BASE}/users/{data['localId']}",
                                headers={"Authorization": f"Bearer {data['idToken']}"},
                                timeout=8,
                            )
                            if r.status_code == 200:
                                role_field = r.json().get("fields", {}).get("role", {})
                                is_admin = role_field.get("stringValue") == "admin"
                        except Exception:
                            pass

                    if not is_admin:
                        st.error("❌ Accès refusé : votre compte n'a pas les droits administrateur.")
                        st.info(f"Contactez l'équipe Swiftli pour obtenir l'accès — votre email : `{email}`")
                        return

                    st.session_state.update({
                        "id_token": data["idToken"],
                        "local_id": data["localId"],
                        "user_email": email,
                    })
                    st.success("✅ Connecté en tant qu'administrateur !")
                    st.rerun()
                except ValueError as e:
                    msg = str(e)
                    if any(x in msg for x in ["EMAIL_NOT_FOUND","INVALID_PASSWORD","INVALID_LOGIN_CREDENTIALS"]):
                        st.error("❌ Email ou mot de passe incorrect.")
                    elif "TOO_MANY_ATTEMPTS" in msg:
                        st.error("⚠️ Trop de tentatives. Réessayez dans quelques minutes.")
                    else:
                        st.error(f"Erreur : {msg}")
                except Exception as e:
                    st.error(f"Connexion impossible : {e}")


# ─── Sidebar ──────────────────────────────────────────────────────────────────
def sidebar() -> str:
    with st.sidebar:
        user_email = st.session_state.get("user_email", "")
        initial = user_email[0].upper() if user_email else "A"
        st.markdown(f"""
        <div style="text-align:center;padding:24px 0 16px">
            <div style="
                width: 70px; height: 70px;
                margin: 0 auto 12px;
                background: linear-gradient(135deg, #fff 0%, #E8DDD3 100%);
                border-radius: 18px;
                display: flex; align-items: center; justify-content: center;
                font-size: 2.2rem;
                box-shadow: 0 8px 24px rgba(0,0,0,0.2);
            ">📦</div>
            <h2 style="margin:6px 0 2px;font-weight:900;font-size:1.4rem;letter-spacing:-0.5px">Swiftli</h2>
            <div style="
                display: inline-block;
                padding: 2px 10px;
                background: rgba(255,255,255,0.15);
                border-radius: 99px;
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.5px;
                margin-bottom: 12px;
            ">ADMIN DASHBOARD</div>
            <div style="
                display: flex; align-items: center; justify-content: center;
                gap: 8px; padding: 8px;
                background: rgba(0,0,0,0.15);
                border-radius: 10px;
                margin-top: 8px;
            ">
                <div style="
                    width: 28px; height: 28px;
                    background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
                    border-radius: 50%;
                    display: flex; align-items: center; justify-content: center;
                    color: white; font-weight: 800; font-size: 0.85rem;
                ">{initial}</div>
                <small style="opacity:.85;font-size:0.75rem">{user_email}</small>
            </div>
        </div>""", unsafe_allow_html=True)
        st.markdown("---")
        page = st.radio("Navigation", [
            "📊 Tableau de bord",
            "👥 Utilisateurs",
            "🆔 KYC",
            "📦 Demandes",
            "🛣️ Trajets",
            "⚠️ Litiges",
            "🔔 Notifications",
            "💰 Tarification",
        ], label_visibility="collapsed")
        st.markdown("---")
        st.markdown(f"""
        <div style="font-size:0.7rem;opacity:0.6;text-align:center;margin-bottom:8px">
            v2.1 • Mai 2026
        </div>
        """, unsafe_allow_html=True)
        if st.button("🚪 Déconnexion", use_container_width=True):
            for k in ["id_token", "local_id", "user_email"]:
                st.session_state.pop(k, None)
            st.rerun()
    return page


# ─── 1. Tableau de bord ───────────────────────────────────────────────────────
def tab_dashboard():
    # Hero section
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {GREEN} 0%, {GREEN_D} 100%);
        color: white;
        padding: 28px 32px;
        border-radius: 18px;
        box-shadow: 0 12px 30px rgba(15, 110, 86, 0.25);
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
    ">
        <div style="
            position: absolute; top: -50px; right: -50px;
            width: 200px; height: 200px;
            background: rgba(255,255,255,0.1);
            border-radius: 50%;
        "></div>
        <div style="position: relative; z-index: 1;">
            <div style="font-size: 0.85rem; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">
                Bonjour 👋
            </div>
            <h1 style="margin: 4px 0 6px; color: white; font-size: 2rem; font-weight: 800;">
                Tableau de bord Swiftli
            </h1>
            <p style="margin: 0; opacity: 0.9; font-size: 0.95rem;">
                Vue d'ensemble en temps réel · {datetime.now().strftime("%d %B %Y · %H:%M")}
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement des données..."):
        users    = fs_get("users",    _token())
        demandes = fs_get("demandes", _token())
        trajets  = fs_get("trajets",  _token())
        reclams  = fs_get("reclamations", _token())

    # ── KPIs ──────────────────────────────────────────────────────────────────
    ca = sum(float(d.get("prixPropose", 0)) for d in demandes
             if d.get("paiementStatut") == "payé")
    kyc_pending = sum(1 for u in users if u.get("kycStatut") == "en_verification")
    kyc_approuve = sum(1 for u in users if u.get("kycStatut") == "approuve")
    livrees = sum(1 for d in demandes if d.get("statut") == "livree")

    # Première rangée de KPIs : indicateurs principaux
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("👥 Utilisateurs", len(users),
              delta=f"{kyc_approuve} vérifiés", delta_color="normal")
    c2.metric("📦 Demandes", len(demandes),
              delta=f"{livrees} livrées", delta_color="normal")
    c3.metric("🛣️ Trajets actifs", sum(1 for t in trajets if t.get("statut") == "disponible"))
    c4.metric("💰 Chiffre d'affaires", f"{ca:,.0f} MAD")

    # Deuxième rangée : alertes opérationnelles
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("🆔 KYC en attente", kyc_pending,
              delta="action requise" if kyc_pending > 0 else "à jour",
              delta_color="inverse" if kyc_pending > 0 else "off")
    c6.metric("⚠️ Réclamations", len(reclams),
              delta="à traiter" if len(reclams) > 0 else "aucune",
              delta_color="inverse" if len(reclams) > 0 else "off")
    c7.metric("🚦 Litiges actifs",
              sum(1 for d in demandes if "litige" in d.get("statut", "")))
    c8.metric("📱 Trajets publiés aujourd'hui",
              sum(1 for t in trajets
                  if (t.get("createdAt") or "").startswith(datetime.now().strftime("%Y-%m-%d"))))

    st.markdown("---")
    col_g1, col_g2, col_g3 = st.columns(3)

    # Demandes par statut — DONUT animé avec total au centre
    with col_g1:
        st.subheader("📦 Demandes par statut")
        statuts: dict[str, int] = {}
        for d in demandes:
            s = d.get("statut", "inconnu")
            statuts[s] = statuts.get(s, 0) + 1
        if statuts:
            labels_fr = {
                "en_attente":"En attente","acceptée":"Acceptée",
                "en_cours":"En cours","livree":"Livrée",
                "annulee":"Annulée","litige":"Litige",
            }
            labels = [labels_fr.get(k, k) for k in statuts]
            values = list(statuts.values())
            total = sum(values)

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.62,
                marker=dict(
                    colors=BROWN_PALETTE,
                    line=dict(color="#FAF6F1", width=3),
                ),
                textinfo="percent",
                textfont=dict(size=13, color="white", family="Segoe UI"),
                hovertemplate="<b>%{label}</b><br>%{value} demandes<br>%{percent}<extra></extra>",
                pull=[0.04 if v == max(values) else 0 for v in values],
                sort=True,
                direction="clockwise",
                rotation=90,
            )])
            fig.add_annotation(
                text=f"<b>{total}</b><br><span style='font-size:12px;color:#8D6E63'>demandes</span>",
                font=dict(size=26, color="#4E342E", family="Segoe UI"),
                showarrow=False, x=0.5, y=0.5,
            )
            _style_chart(fig, height=340, show_legend=True)
            fig.update_layout(legend=dict(orientation="h", y=-0.1,
                                          x=0.5, xanchor="center"))
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune demande.")

    # KYC statuts — BARRES horizontales arrondies avec valeurs
    with col_g2:
        st.subheader("🆔 Statuts KYC")
        kyc_counts: dict[str, int] = {}
        for u in users:
            s = u.get("kycStatut", "non_soumis") or "non_soumis"
            kyc_counts[s] = kyc_counts.get(s, 0) + 1
        if kyc_counts:
            kyc_labels = {
                "non_soumis":"Non soumis","en_verification":"En attente",
                "approuve":"Approuvé","rejete":"Rejeté",
            }
            order = ["approuve", "en_verification", "non_soumis", "rejete"]
            color_map = {
                "approuve": "#8D6E63", "en_verification": "#C8860D",
                "non_soumis": "#D7B89C", "rejete": "#B5482F",
            }
            items = [(kyc_labels.get(k, k), kyc_counts.get(k, 0), color_map.get(k, "#8D6E63"))
                     for k in order if k in kyc_counts]
            # Ajoute les statuts non prévus
            for k, v in kyc_counts.items():
                if k not in order:
                    items.append((kyc_labels.get(k, k), v, "#6F4E37"))

            ynames = [i[0] for i in items]
            yvals  = [i[1] for i in items]
            ycols  = [i[2] for i in items]

            fig2 = go.Figure(data=[go.Bar(
                y=ynames,
                x=yvals,
                orientation="h",
                marker=dict(
                    color=ycols,
                    line=dict(width=0),
                    cornerradius=8,
                ),
                text=yvals,
                textposition="outside",
                textfont=dict(size=14, color="#4E342E", family="Segoe UI"),
                hovertemplate="<b>%{y}</b><br>%{x} utilisateur(s)<extra></extra>",
            )])
            _style_chart(fig2, height=340, show_legend=False)
            fig2.update_layout(
                bargap=0.4,
                xaxis=dict(showticklabels=False, showgrid=False),
            )
            st.plotly_chart(fig2, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucun utilisateur.")

    # Dernières inscriptions
    with col_g3:
        st.subheader("👥 Dernières inscriptions")
        if users:
            df_u = pd.DataFrame([{
                "Nom":   f"{u.get('prenom','')} {u.get('nom','')}".strip() or u.get("_id","")[:12],
                "Email": u.get("email",""),
                "KYC":   u.get("kycStatut","—"),
            } for u in users[-8:]])
            st.dataframe(df_u, use_container_width=True, hide_index=True)

    # ── PANNEAU D'ALERTES & ACTIONS RAPIDES ──────────────────────────────
    st.markdown("---")
    st.markdown('<div class="inner-section-title">🚨 Centre de décision</div>',
                unsafe_allow_html=True)

    nb_litiges = sum(1 for d in demandes if "litige" in d.get("statut", ""))
    taux_conv = (livrees / len(demandes) * 100) if demandes else 0

    # Carte 1 : KYC à valider
    if kyc_pending > 0:
        card1 = f"""
        <div class="decision-card dc-warn">
            <div class="dc-head">
                <span class="dc-icon">🟡</span>
                <span class="dc-title">KYC à valider</span>
            </div>
            <div class="dc-value">{kyc_pending}</div>
            <div class="dc-sub">⚡ Action requise — Onglet KYC</div>
        </div>"""
    else:
        card1 = """
        <div class="decision-card dc-ok">
            <div class="dc-head">
                <span class="dc-icon">✅</span>
                <span class="dc-title">KYC à jour</span>
            </div>
            <div class="dc-value">0</div>
            <div class="dc-sub">Aucune action requise</div>
        </div>"""

    # Carte 2 : Litiges & Réclamations
    if nb_litiges > 0 or len(reclams) > 0:
        card2 = f"""
        <div class="decision-card dc-danger">
            <div class="dc-head">
                <span class="dc-icon">🚨</span>
                <span class="dc-title">Litiges &amp; Réclamations</span>
            </div>
            <div class="dc-value">{nb_litiges + len(reclams)}</div>
            <div class="dc-sub">{nb_litiges} litige(s) · {len(reclams)} réclamation(s)</div>
        </div>"""
    else:
        card2 = """
        <div class="decision-card dc-ok">
            <div class="dc-head">
                <span class="dc-icon">🛡️</span>
                <span class="dc-title">Plateforme saine</span>
            </div>
            <div class="dc-value">0</div>
            <div class="dc-sub">Aucun litige ni réclamation</div>
        </div>"""

    # Carte 3 : Taux de livraison
    card3 = f"""
    <div class="decision-card dc-primary">
        <div class="dc-head">
            <span class="dc-icon">📈</span>
            <span class="dc-title">Taux de livraison</span>
        </div>
        <div class="dc-value">{taux_conv:.0f}%</div>
        <div class="dc-sub">{livrees}/{len(demandes)} demandes livrées</div>
    </div>"""

    ac1, ac2, ac3 = st.columns(3, gap="medium")
    with ac1: st.markdown(card1, unsafe_allow_html=True)
    with ac2: st.markdown(card2, unsafe_allow_html=True)
    with ac3: st.markdown(card3, unsafe_allow_html=True)

    # ── FEED D'ACTIVITÉ + TOP VOYAGEURS ──────────────────────────────────
    st.markdown("---")
    activity_col, top_col = st.columns([3, 2])

    with activity_col:
        st.markdown(f"""
        <div class="inner-section-title">📰 Activité récente</div>
        """, unsafe_allow_html=True)

        # Combine demandes + users pour feed
        events = []
        for u in users[-10:]:
            events.append({
                "icon": "👤",
                "title": f"Nouvel utilisateur : {u.get('prenom','')} {u.get('nom','')}".strip() or "Utilisateur inscrit",
                "subtitle": u.get("email", ""),
                "time": (u.get("createdAt") or "")[:16],
                "color": BLUE,
            })
        for d in demandes[-10:]:
            statut = d.get("statut", "")
            icon = "📦"
            color = AMBER
            if statut == "livree":
                icon = "✅"; color = GREEN
            elif statut == "litige":
                icon = "🚨"; color = RED
            events.append({
                "icon": icon,
                "title": f"{d.get('villeDepart','')} → {d.get('villeArrivee','')}",
                "subtitle": f"{d.get('expediteurNom','—')} · {d.get('prixPropose',0)} MAD · {statut}",
                "time": (d.get("createdAt") or "")[:16],
                "color": color,
            })

        # Tri par date desc
        events.sort(key=lambda e: e["time"], reverse=True)
        events = events[:12]

        if events:
            for evt in events:
                st.markdown(f"""
                <div style="
                    display:flex; align-items:flex-start; gap:12px;
                    padding:12px 14px; margin-bottom:8px;
                    background:white; border-radius:12px;
                    border:1px solid #E5E7EB;
                    transition:all 0.2s ease;
                ">
                    <div style="
                        width:36px; height:36px;
                        background:{evt['color']}22; color:{evt['color']};
                        border-radius:10px;
                        display:flex; align-items:center; justify-content:center;
                        font-size:1.1rem;
                        flex-shrink:0;
                    ">{evt['icon']}</div>
                    <div style="flex:1; min-width:0">
                        <div style="font-weight:600; color:#1F2937; font-size:0.9rem">{evt['title']}</div>
                        <div style="font-size:0.78rem; color:#6B7280; margin-top:2px">{evt['subtitle']}</div>
                    </div>
                    <div style="font-size:0.7rem; color:#9CA3AF; white-space:nowrap">{evt['time'][:10]}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aucune activité récente.")

    with top_col:
        st.markdown(f"""
        <div class="inner-section-title">🏆 Top voyageurs</div>
        """, unsafe_allow_html=True)

        # Calcul des voyageurs avec le plus de livraisons
        voy_count: dict[str, dict] = {}
        for d in demandes:
            if d.get("statut") in ("livree", "payée"):
                vid = d.get("voyageurId", "")
                if vid:
                    if vid not in voy_count:
                        voy_count[vid] = {"nom": d.get("voyageurNom", "Inconnu"), "count": 0, "ca": 0}
                    voy_count[vid]["count"] += 1
                    voy_count[vid]["ca"] += float(d.get("prixPropose", 0))

        top_voy = sorted(voy_count.values(), key=lambda v: v["count"], reverse=True)[:5]

        if top_voy:
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, v in enumerate(top_voy):
                medal = medals[i] if i < 3 else f"{i+1}."
                initial = v["nom"][0].upper() if v["nom"] else "?"
                bg_color = "#FFD700" if i == 0 else ("#C0C0C0" if i == 1 else ("#CD7F32" if i == 2 else "#E5E7EB"))
                st.markdown(f"""
                <div style="
                    display:flex; align-items:center; gap:10px;
                    padding:10px 12px; margin-bottom:8px;
                    background:white; border-radius:12px;
                    border:1px solid #E5E7EB;
                ">
                    <div style="font-size:1.3rem;flex-shrink:0">{medal}</div>
                    <div style="
                        width:36px; height:36px;
                        background:linear-gradient(135deg, {bg_color}, {bg_color}88);
                        border-radius:50%;
                        display:flex; align-items:center; justify-content:center;
                        font-weight:800; color:white;
                        flex-shrink:0;
                    ">{initial}</div>
                    <div style="flex:1; min-width:0">
                        <div style="font-weight:700; color:#1F2937; font-size:0.88rem">{v['nom']}</div>
                        <div style="font-size:0.75rem; color:#6B7280">
                            {v['count']} livraisons · {v['ca']:.0f} MAD
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aucun voyageur actif pour l'instant.")

        # Top routes
        st.markdown(f"""
        <div class="inner-section-title" style="margin-top:20px">🗺️ Top trajets</div>
        """, unsafe_allow_html=True)

        route_count: dict[str, int] = {}
        for d in demandes:
            if d.get("villeDepart") and d.get("villeArrivee"):
                k = f"{d['villeDepart']} → {d['villeArrivee']}"
                route_count[k] = route_count.get(k, 0) + 1

        top_routes = sorted(route_count.items(), key=lambda x: x[1], reverse=True)[:5]
        if top_routes:
            max_count = top_routes[0][1] if top_routes else 1
            for route, count in top_routes:
                pct = (count / max_count) * 100
                st.markdown(f"""
                <div style="
                    padding:10px 12px; margin-bottom:6px;
                    background:white; border-radius:10px;
                    border:1px solid #E5E7EB;
                ">
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                        <div style="font-weight:600; color:#1F2937; font-size:0.85rem">{route}</div>
                        <div style="font-weight:700; color:{GREEN_D}; font-size:0.85rem">{count}</div>
                    </div>
                    <div style="
                        background:#E5E7EB; height:6px; border-radius:3px; overflow:hidden;
                    ">
                        <div style="
                            background:linear-gradient(90deg, {GREEN} 0%, {GREEN_D} 100%);
                            height:100%; width:{pct}%; border-radius:3px;
                            transition: width 0.5s ease;
                        "></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aucun trajet pour l'instant.")


# ─── 2. Utilisateurs ──────────────────────────────────────────────────────────
def tab_users():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #795548 0%, #4E342E 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(24, 95, 165, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">👥 Gestion des utilisateurs</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Filtrer, rechercher et gérer tous les comptes Swiftli</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        users = fs_get("users", _token())

    if not users:
        st.info("Aucun utilisateur.")
        return

    # ── Mini stats en haut ──
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total", len(users))
    s2.metric("✅ Vérifiés", sum(1 for u in users if u.get("kycStatut") == "approuve"))
    s3.metric("🟡 En attente", sum(1 for u in users if u.get("kycStatut") == "en_verification"))
    s4.metric("⭐ Note moyenne",
              f"{(sum((u.get('note') or 0) for u in users) / max(1, sum(1 for u in users if u.get('note')))):.1f}/5"
              if any(u.get('note') for u in users) else "—")

    st.markdown("---")

    # ── Toolbar de filtres ──
    st.markdown(f"""
    <div style="font-size:1rem;font-weight:700;color:{GREEN_D};margin-bottom:10px">
        🔧 Filtres et recherche
    </div>
    """, unsafe_allow_html=True)

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 1])
    with col_f1:
        search = st.text_input("🔍 Rechercher", placeholder="Nom, email ou UID...")
    with col_f2:
        role_f = st.selectbox("Rôle", ["Tous", "user", "admin", "voyageur", "expediteur"])
    with col_f3:
        kyc_f = st.selectbox("KYC", ["Tous", "non_soumis", "en_verification", "approuve", "rejete"])
    with col_f4:
        view_mode = st.selectbox("Vue", ["📊 Tableau", "🃏 Cartes"])

    filtered = users
    if search:
        s = search.lower()
        filtered = [u for u in filtered if
                    s in u.get("email","").lower() or
                    s in f"{u.get('prenom','')} {u.get('nom','')}".lower() or
                    s in u.get("_id","").lower()]
    if role_f != "Tous":
        filtered = [u for u in filtered if u.get("role","user") == role_f]
    if kyc_f != "Tous":
        filtered = [u for u in filtered if u.get("kycStatut","non_soumis") == kyc_f]

    st.markdown(f"""
    <div style="
        padding:10px 14px; margin:10px 0;
        background:linear-gradient(135deg, #F5EFE8 0%, #E8DDD3 100%);
        border-left:4px solid {GREEN};
        border-radius:10px;
        color:{GREEN_D}; font-weight:600;
    ">
        📊 {len(filtered)} utilisateur(s) trouvé(s) sur {len(users)}
    </div>
    """, unsafe_allow_html=True)

    if view_mode == "🃏 Cartes":
        # Vue en cartes — 3 colonnes
        for i in range(0, len(filtered), 3):
            cols = st.columns(3)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(filtered):
                    break
                u = filtered[idx]
                with col:
                    nom = f"{u.get('prenom','')} {u.get('nom','')}".strip() or "Sans nom"
                    initial = nom[0].upper() if nom != "Sans nom" else "?"
                    kyc_st = u.get('kycStatut','non_soumis')
                    kyc_colors = {
                        "approuve": ("#E8DDD3", "#4E342E", "✅"),
                        "en_verification": ("#FEF3C7", "#92400E", "🟡"),
                        "rejete": ("#FEE2E2", "#991B1B", "🔴"),
                        "non_soumis": ("#F3F4F6", "#6B7280", "⚪"),
                    }
                    bg, color, icon = kyc_colors.get(kyc_st, kyc_colors["non_soumis"])
                    note = u.get('note', 0) or 0
                    st.markdown(f"""
                    <div style="
                        background:white;
                        border:1px solid #E5E7EB;
                        border-radius:14px;
                        padding:16px;
                        margin-bottom:12px;
                        box-shadow:0 1px 3px rgba(0,0,0,0.04);
                        transition:all 0.2s ease;
                    ">
                        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
                            <div style="
                                width:48px; height:48px;
                                background:linear-gradient(135deg, {GREEN} 0%, {GREEN_D} 100%);
                                border-radius:14px;
                                display:flex; align-items:center; justify-content:center;
                                color:white; font-weight:800; font-size:1.2rem;
                            ">{initial}</div>
                            <div style="flex:1; min-width:0">
                                <div style="font-weight:700;color:#1F2937;font-size:0.95rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{nom}</div>
                                <div style="font-size:0.75rem;color:#6B7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{u.get('email','—')}</div>
                            </div>
                        </div>
                        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
                            <span style="background:{bg};color:{color};padding:3px 8px;border-radius:99px;font-size:0.7rem;font-weight:700">{icon} {kyc_st}</span>
                            <span style="background:#EFF6FF;color:#1E40AF;padding:3px 8px;border-radius:99px;font-size:0.7rem;font-weight:700">{u.get('role','user')}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;font-size:0.8rem;color:#6B7280;padding-top:8px;border-top:1px solid #F3F4F6">
                            <span>⭐ {note}/5 ({u.get('nombreEvaluations',0)})</span>
                            <span>📞 {u.get('telephone','—')[:12] if u.get('telephone') else '—'}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    else:
        # Tableau (vue classique améliorée)
        df = pd.DataFrame([{
            "UID":         u["_id"][:12]+"...",
            "Prénom":      u.get("prenom",""),
            "Nom":         u.get("nom",""),
            "Email":       u.get("email",""),
            "Téléphone":   u.get("telephone",""),
            "Rôle":        u.get("role","user"),
            "KYC":         u.get("kycStatut","non_soumis"),
            "Note":        u.get("note",""),
            "Évals":       u.get("nombreEvaluations",0),
        } for u in filtered])
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    # Détail utilisateur
    st.markdown("---")
    st.subheader("🔍 Détail utilisateur")
    emails = [u.get("email", u["_id"]) for u in filtered]
    uid_map = {u.get("email", u["_id"]): u for u in filtered}

    selected = st.selectbox("Sélectionner un utilisateur", ["—"] + emails)
    if selected != "—":
        u = uid_map[selected]
        uid = u["_id"]

        col_info, col_actions = st.columns([2, 1])
        with col_info:
            st.markdown(f"""
            | Champ | Valeur |
            |---|---|
            | **UID** | `{uid}` |
            | **Nom complet** | {u.get('prenom','')} {u.get('nom','')} |
            | **Email** | {u.get('email','—')} |
            | **Téléphone** | {u.get('telephone','—')} |
            | **Rôle** | {u.get('role','user')} |
            | **KYC** | {u.get('kycStatut','non_soumis')} |
            | **Note** | {u.get('note','—')} / 5 |
            | **Évaluations** | {u.get('nombreEvaluations',0)} |
            """)

            # Photos KYC si disponibles
            if u.get("cinRectoUrl") or u.get("cinVersoUrl") or u.get("photoUrl"):
                st.markdown("**Photos :**")
                pc1, pc2, pc3 = st.columns(3)
                with pc1: _photo(u.get("photoUrl"),    "Photo profil")
                with pc2: _photo(u.get("cinRectoUrl"), "CIN Recto")
                with pc3: _photo(u.get("cinVersoUrl"), "CIN Verso")

        with col_actions:
            st.markdown("**Actions rapides**")
            roles_options = ["user", "admin", "voyageur", "expediteur"]
            current_role = u.get("role", "user") or "user"
            # Si le rôle actuel n'est pas dans la liste, l'ajouter dynamiquement
            if current_role not in roles_options:
                roles_options.append(current_role)
            new_role = st.selectbox("Changer rôle", roles_options,
                                    index=roles_options.index(current_role))
            if st.button("💾 Sauvegarder rôle", use_container_width=True):
                fs_patch("users", uid, {"role": new_role}, _token())
                st.success("✅ Rôle mis à jour !")
                st.rerun()

            st.markdown("---")
            kyc_options = ["non_soumis", "en_verification", "approuve", "rejete"]
            current_kyc = u.get("kycStatut", "non_soumis") or "non_soumis"
            if current_kyc not in kyc_options:
                kyc_options.append(current_kyc)
            new_kyc = st.selectbox("Changer statut KYC", kyc_options,
                                   index=kyc_options.index(current_kyc))
            if st.button("💾 Sauvegarder KYC", use_container_width=True):
                fs_patch("users", uid, {"kycStatut": new_kyc}, _token())
                st.success("✅ KYC mis à jour !")
                st.rerun()


# ─── 3. KYC ───────────────────────────────────────────────────────────────────
def tab_kyc():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #A1887F 0%, #6D4C41 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(239, 159, 39, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">🆔 Vérification d'identité (KYC)</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Examiner les documents, comparer photo profil ↔ CIN, approuver ou rejeter</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement depuis Firestore..."):
        users = fs_get("users", _token())

    # Séparer par statut KYC
    kyc_users = [u for u in users
                 if u.get("kycStatut") in ("en_verification","approuve","rejete")
                 or u.get("cinRectoUrl") or u.get("cinVersoUrl")]

    # Métriques avec progression
    total = len(kyc_users)
    pending = sum(1 for u in kyc_users if u.get("kycStatut")=="en_verification")
    approuve = sum(1 for u in kyc_users if u.get("kycStatut")=="approuve")
    rejete = sum(1 for u in kyc_users if u.get("kycStatut")=="rejete")
    taux_approbation = (approuve / max(1, approuve + rejete)) * 100

    m1,m2,m3,m4 = st.columns(4)
    m1.metric("📁 Total dossiers", total)
    m2.metric("🟡 En attente", pending,
              delta="action requise" if pending > 0 else None,
              delta_color="inverse" if pending > 0 else "off")
    m3.metric("🟢 Approuvés", approuve,
              delta=f"{taux_approbation:.0f}% d'approbation",
              delta_color="normal")
    m4.metric("🔴 Rejetés", rejete)

    st.markdown("---")

    # Filtre
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        filtre = st.selectbox("Filtrer", ["🟡 En attente", "Tous", "🟢 Approuvés", "🔴 Rejetés"])
    with col_f2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Rafraîchir", use_container_width=True):
            st.rerun()

    filtre_map = {
        "🟡 En attente": "en_verification",
        "🟢 Approuvés":  "approuve",
        "🔴 Rejetés":    "rejete",
        "Tous":          None,
    }
    filtre_val = filtre_map[filtre]
    dossiers = [u for u in kyc_users
                if filtre_val is None or u.get("kycStatut") == filtre_val]

    if not dossiers:
        st.success("✅ Aucun dossier pour ce filtre.")
        return

    st.info(f"**{len(dossiers)}** dossier(s)")

    for idx, u in enumerate(dossiers):
        uid    = u["_id"]
        prenom = u.get("prenom", "")
        nom    = u.get("nom", "")
        email  = u.get("email", "")
        statut = u.get("kycStatut", "—")
        soumis = (u.get("kycSoumisLe") or "")[:10]

        badge = {"en_verification":"🟡 En attente","approuve":"🟢 Approuvé",
                 "rejete":"🔴 Rejeté"}.get(statut, statut)

        with st.expander(
            f"👤 {prenom} {nom}  —  {email}  —  {badge}",
            expanded=(idx == 0 and statut == "en_verification")
        ):
            col_photos, col_actions = st.columns([3, 1])

            with col_photos:
                p1, p2, p3 = st.columns(3)
                with p1: _photo(u.get("photoUrl"),    "📷 Photo profil")
                with p2: _photo(u.get("cinRectoUrl"), "🪪 CIN Recto")
                with p3: _photo(u.get("cinVersoUrl"), "🪪 CIN Verso")

                # ── Vérification automatique du visage : photo profil vs CIN recto ──
                photo_url = u.get("photoUrl")
                cin_url   = u.get("cinRectoUrl")
                if photo_url and cin_url:
                    face_result = _face_compare(photo_url, cin_url)
                    st.markdown(
                        _face_match_badge(face_result["confidence"], face_result["error"]),
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("⚙️ Vérification visage : photo de profil ou CIN manquante")

            with col_actions:
                st.markdown(f"**UID :** `{uid[:14]}...`")
                st.markdown(f"**Email :** {email or '—'}")
                st.markdown(f"**Soumis :** {soumis or '—'}")
                st.markdown(f"**Statut :** {badge}")
                st.markdown("---")

                if statut == "en_verification":
                    # Bouton de rejet automatique si visages ne correspondent pas
                    if photo_url and cin_url:
                        face_result = _face_compare(photo_url, cin_url)
                        conf = face_result["confidence"]
                        if conf is not None and conf < FACE_MATCH_THRESHOLD:
                            if st.button("🚫 Rejet auto (visages différents)",
                                         key=f"autorej_{uid}_{idx}",
                                         use_container_width=True, type="primary"):
                                fs_patch("users", uid, {
                                    "kycStatut": "rejete",
                                    "kycMotifRejet": f"Photo de profil ne correspond pas à la CIN (score: {conf:.1f}%)",
                                    "kycTraiteLe": datetime.now(timezone.utc).isoformat(),
                                }, _token())
                                fs_add("notifications", {
                                    "userId": uid, "titre": "KYC Rejeté ❌",
                                    "corps": "Votre photo de profil ne correspond pas à votre CIN. Soumettez à nouveau.",
                                    "lu": False,
                                }, _token())
                                st.warning("❌ Auto-rejeté pour non-correspondance.")
                                st.rerun()

                    motif = st.text_area("Motif rejet", key=f"motif_{uid}", height=60,
                                         placeholder="Obligatoire si rejet")
                    ca, cr = st.columns(2)
                    with ca:
                        if st.button("✅ Approuver", key=f"app_{uid}_{idx}",
                                     use_container_width=True, type="primary"):
                            fs_patch("users", uid,
                                     {"kycStatut": "approuve", "kycTraiteLe": datetime.now(timezone.utc).isoformat()},
                                     _token())
                            # Notification Firestore
                            fs_add("notifications", {
                                "userId": uid, "titre": "KYC Approuvé ✅",
                                "corps": "Votre identité a été vérifiée avec succès.",
                                "lu": False,
                            }, _token())
                            st.success("✅ Approuvé !")
                            st.rerun()
                    with cr:
                        if st.button("❌ Rejeter", key=f"rej_{uid}_{idx}",
                                     use_container_width=True):
                            if not motif.strip():
                                st.error("Motif obligatoire.")
                            else:
                                fs_patch("users", uid, {
                                    "kycStatut": "rejete",
                                    "kycMotifRejet": motif.strip(),
                                    "kycTraiteLe": datetime.now(timezone.utc).isoformat(),
                                }, _token())
                                fs_add("notifications", {
                                    "userId": uid, "titre": "KYC Rejeté ❌",
                                    "corps": f"Motif : {motif.strip()}",
                                    "lu": False,
                                }, _token())
                                st.warning("❌ Rejeté.")
                                st.rerun()
                else:
                    st.info(badge)
                    if u.get("kycMotifRejet"):
                        st.markdown(f"_Motif : {u['kycMotifRejet']}_")
                    # Permettre de re-traiter
                    if st.button("↩️ Remettre en attente", key=f"reset_{uid}_{idx}",
                                 use_container_width=True):
                        fs_patch("users", uid, {"kycStatut": "en_verification"}, _token())
                        st.rerun()


# ─── 4. Demandes ─────────────────────────────────────────────────────────────
def tab_demandes():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #8D6E63 0%, #5D4037 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(139, 92, 246, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">📦 Gestion des demandes</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Suivre, modifier et résoudre toutes les demandes d'envoi</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        demandes = fs_get("demandes", _token())

    if not demandes:
        st.info("Aucune demande.")
        return

    # Métriques
    statuts_count: dict[str, int] = {}
    ca = 0.0
    for d in demandes:
        s = d.get("statut","inconnu")
        statuts_count[s] = statuts_count.get(s,0) + 1
        if d.get("paiementStatut") == "payé":
            ca += float(d.get("prixPropose",0))

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📦 Total", len(demandes))
    c2.metric("🟡 En attente", statuts_count.get("en_attente",0))
    c3.metric("🔵 En cours", statuts_count.get("en_cours",0))
    c4.metric("🟢 Livrées", statuts_count.get("livree",0))
    c5.metric("💰 CA encaissé", f"{ca:,.0f} MAD")

    st.markdown("---")

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        statut_f = st.selectbox("Filtrer par statut",
                                ["Tous","en_attente","acceptée","en_cours","livree","annulee","litige"])
    with col_f2:
        search_d = st.text_input("🔍 Rechercher (ville, nom, ID)", "")

    filtered = demandes
    if statut_f != "Tous":
        filtered = [d for d in filtered if d.get("statut") == statut_f]
    if search_d:
        s = search_d.lower()
        filtered = [d for d in filtered if
                    s in d.get("villeDepart","").lower() or
                    s in d.get("villeArrivee","").lower() or
                    s in d.get("expediteurNom","").lower() or
                    s in d.get("_id","").lower()]

    st.info(f"**{len(filtered)}** demande(s)")

    df = pd.DataFrame([{
        "ID":          d["_id"][:10],
        "Départ":      d.get("villeDepart",""),
        "Arrivée":     d.get("villeArrivee",""),
        "Expéditeur":  d.get("expediteurNom",""),
        "Prix (MAD)":  d.get("prixPropose",""),
        "Statut":      d.get("statut",""),
        "Paiement":    d.get("paiementStatut",""),
        "Type colis":  d.get("typeDocument",""),
    } for d in filtered])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Modifier statut d'une demande
    st.markdown("---")
    st.subheader("✏️ Modifier une demande")
    ids = ["—"] + [d["_id"][:10] + " — " + d.get("villeDepart","") + "→" + d.get("villeArrivee","")
                   for d in filtered]
    id_map = {d["_id"][:10] + " — " + d.get("villeDepart","") + "→" + d.get("villeArrivee",""): d
              for d in filtered}
    sel = st.selectbox("Demande", ids)
    if sel != "—":
        d_sel = id_map[sel]
        st.json({k: v for k, v in d_sel.items() if k != "_id"})
        new_statut = st.selectbox("Nouveau statut",
                                  ["en_attente","acceptée","en_cours","livree","annulee","litige"],
                                  index=["en_attente","acceptée","en_cours","livree","annulee","litige"]
                                  .index(d_sel.get("statut","en_attente"))
                                  if d_sel.get("statut") in
                                  ["en_attente","acceptée","en_cours","livree","annulee","litige"] else 0)
        if st.button("💾 Mettre à jour le statut", type="primary"):
            fs_patch("demandes", d_sel["_id"], {"statut": new_statut}, _token())
            st.success(f"✅ Statut mis à jour → {new_statut}")
            st.rerun()


# ─── 5. Trajets ───────────────────────────────────────────────────────────────
def tab_trajets():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #A1745C 0%, #6F4E37 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(20, 184, 166, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">🛣️ Trajets publiés</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Tous les trajets disponibles, en cours et expirés</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        trajets = fs_get("trajets", _token())

    if not trajets:
        st.info("Aucun trajet.")
        return

    # Métriques avancées
    nb_dispo = sum(1 for t in trajets if t.get("statut") == "disponible")
    nb_en_cours = sum(1 for t in trajets if t.get("statut") == "en_cours")
    nb_termine = sum(1 for t in trajets if t.get("statut") == "termine")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🛣️ Total", len(trajets))
    c2.metric("🟢 Disponibles", nb_dispo)
    c3.metric("🔵 En cours", nb_en_cours)
    c4.metric("⚫ Terminés", nb_termine)
    st.markdown("---")

    df = pd.DataFrame([{
        "ID":          t["_id"][:10],
        "Départ":      t.get("villeDepart",""),
        "Arrivée":     t.get("villeArrivee",""),
        "Voyageur":    t.get("voyageurNom",""),
        "Date":        str(t.get("dateDepart",""))[:10],
        "Véhicule":    t.get("vehicule",""),
        "Prix max":    t.get("prixMax",""),
        "Statut":      t.get("statut",""),
    } for t in trajets])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Supprimer un trajet
    st.markdown("---")
    st.subheader("🗑️ Supprimer un trajet")
    ids_t = ["—"] + [t["_id"][:10] + " — " + t.get("villeDepart","") + "→" + t.get("villeArrivee","")
                     for t in trajets]
    id_map_t = {t["_id"][:10] + " — " + t.get("villeDepart","") + "→" + t.get("villeArrivee",""): t
                for t in trajets}
    sel_t = st.selectbox("Trajet à supprimer", ids_t)
    if sel_t != "—":
        t_sel = id_map_t[sel_t]
        st.warning(f"⚠️ Vous allez supprimer le trajet {t_sel['_id'][:10]}...")
        if st.button("🗑️ Confirmer la suppression", type="primary"):
            fs_delete("trajets", t_sel["_id"], _token())
            st.success("✅ Trajet supprimé.")
            st.rerun()


# ─── 6. Litiges ───────────────────────────────────────────────────────────────
def tab_litiges():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #B5482F 0%, #7B2D1A 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(226, 75, 74, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">⚠️ Litiges & Réclamations</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Résolution des conflits et médiation entre utilisateurs</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        demandes = fs_get("demandes",      _token())
        reclams  = fs_get("reclamations",  _token())

    litiges = [d for d in demandes if "litige" in d.get("statut","")]

    c1, c2, c3 = st.columns(3)
    c1.metric("🚨 Litiges actifs", len(litiges))
    c2.metric("📩 Réclamations", len(reclams))
    c3.metric("✅ Résolus (livrées)",
              sum(1 for d in demandes if d.get("statut") == "livree"))
    st.markdown("---")

    st.subheader(f"🚨 Demandes en litige ({len(litiges)})")
    if litiges:
        df = pd.DataFrame([{
            "ID":         d["_id"][:8],
            "Départ":     d.get("villeDepart",""),
            "Arrivée":    d.get("villeArrivee",""),
            "Expéditeur": d.get("expediteurNom",""),
            "Prix":       f"{d.get('prixPropose',0)} MAD",
        } for d in litiges])
        st.dataframe(df, use_container_width=True, hide_index=True)
        # Résoudre un litige
        ids_l = ["—"] + [d["_id"][:8] for d in litiges]
        id_map_l = {d["_id"][:8]: d for d in litiges}
        sel_l = st.selectbox("Résoudre un litige", ids_l)
        if sel_l != "—":
            d_sel = id_map_l[sel_l]
            resolution = st.selectbox("Résolution",["livree","annulee","en_attente"])
            if st.button("✅ Appliquer résolution", type="primary"):
                fs_patch("demandes", d_sel["_id"], {"statut": resolution}, _token())
                st.success(f"✅ Litige résolu → {resolution}")
                st.rerun()
    else:
        st.success("✅ Aucun litige actif.")

    st.markdown("---")
    st.subheader(f"Réclamations ({len(reclams)})")
    if reclams:
        df_r = pd.DataFrame([{
            "ID":      r["_id"][:8],
            "Type":    r.get("type",""),
            "Statut":  r.get("statut",""),
            "Message": str(r.get("description",""))[:80],
        } for r in reclams])
        st.dataframe(df_r, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune réclamation.")


# ─── 7. Notifications ─────────────────────────────────────────────────────────
def tab_notifications():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #C8860D 0%, #8B5E0D 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(245, 158, 11, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">🔔 Notifications</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Envoyer des messages ciblés ou en masse aux utilisateurs</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        users = fs_get("users", _token())

    emails = [u.get("email", u["_id"]) for u in users if u.get("email")]
    uid_map = {u.get("email", u["_id"]): u["_id"] for u in users}

    tab1, tab2 = st.tabs(["📤 Envoyer", "📋 Historique"])

    with tab1:
        with st.form("notif_form"):
            dest  = st.selectbox("Destinataire", ["👥 Tous les utilisateurs"] + emails)
            titre = st.text_input("Titre de la notification")
            corps = st.text_area("Message")
            send  = st.form_submit_button("🚀 Envoyer", type="primary", use_container_width=True)

        if send and titre and corps:
            targets = users if dest == "👥 Tous les utilisateurs" else [{"_id": uid_map[dest]}]
            for u in targets:
                fs_add("notifications", {
                    "userId": u["_id"],
                    "titre": titre,
                    "corps": corps,
                    "lu": False,
                }, _token())
            st.success(f"✅ Notification envoyée à {len(targets)} utilisateur(s) !")

    with tab2:
        with st.spinner("Chargement..."):
            notifs = fs_get("notifications", _token())
        if notifs:
            df_n = pd.DataFrame([{
                "UserId": n.get("userId","")[:12],
                "Titre":  n.get("titre",""),
                "Corps":  str(n.get("corps",""))[:60],
                "Lu":     "✅" if n.get("lu") else "❌",
            } for n in reversed(notifs[-30:])])
            st.dataframe(df_n, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune notification.")


# ─── 8. Tarification ──────────────────────────────────────────────────────────
_DISTANCES = {
    frozenset({"Casablanca","Rabat"}):90, frozenset({"Casablanca","Marrakech"}):243,
    frozenset({"Casablanca","Fès"}):311,  frozenset({"Casablanca","Tanger"}):339,
    frozenset({"Casablanca","Agadir"}):469, frozenset({"Rabat","Fès"}):225,
    frozenset({"Rabat","Marrakech"}):326, frozenset({"Marrakech","Agadir"}):250,
    frozenset({"Fès","Tanger"}):299, frozenset({"Casablanca","Oujda"}):571,
    frozenset({"Casablanca","Meknès"}):268,
}

def tab_tarification():
    # Header hero
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #8D6E63 0%, #4E342E 100%);
        color: white;
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(16, 185, 129, 0.25);
        margin-bottom: 20px;
        position: relative; overflow: hidden;
    ">
        <div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:rgba(255,255,255,0.1);border-radius:50%"></div>
        <h2 style="margin:0;color:white;font-weight:800;font-size:1.7rem">💰 Simulateur de tarification</h2>
        <p style="margin:4px 0 0;opacity:0.9;font-size:0.9rem">Calculer le prix suggéré selon poids, distance et options</p>
    </div>
    """, unsafe_allow_html=True)
    villes = ["Casablanca","Rabat","Marrakech","Fès","Tanger","Agadir","Meknès","Oujda"]
    col1, col2 = st.columns(2)
    with col1:
        poids   = st.number_input("Poids (kg)", 0.1, 500.0, 5.0, 0.5)
        v_dep   = st.selectbox("Ville départ",  villes)
        v_arr   = st.selectbox("Ville arrivée", villes, index=1)
        fragile = st.checkbox("Fragile (+20%)")
        urgent  = st.checkbox("Urgent (+35%)")
        dist = _DISTANCES.get(frozenset({v_dep,v_arr}), 150)
        prix = 15.0 + poids*2.5 + dist*0.8
        if fragile: prix *= 1.20
        if urgent:  prix *= 1.35
        prix = math.ceil(prix*2)/2
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.metric("Prix suggéré", f"{prix:.1f} MAD", delta=f"{dist} km")
        fig = go.Figure(go.Bar(
            x=["Base", "Poids", "Distance"],
            y=[15, poids*2.5, dist*0.8],
            marker=dict(
                color=["#8D6E63", "#C8860D", "#5D4037"],
                cornerradius=8,
            ),
            text=[f"{15:.0f}", f"{poids*2.5:.0f}", f"{dist*0.8:.0f}"],
            textposition="outside",
            textfont=dict(size=14, color="#4E342E"),
            hovertemplate="<b>%{x}</b><br>%{y:.1f} MAD<extra></extra>",
        ))
        _style_chart(fig, height=260, show_legend=False)
        fig.update_layout(yaxis_title="MAD", bargap=0.45)
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
    st.markdown("---")
    st.subheader("Grille tarifaire — Depuis Casablanca")
    rows = []
    for v2 in ["Rabat","Marrakech","Fès","Tanger","Agadir"]:
        d = _DISTANCES.get(frozenset({"Casablanca",v2}), 0)
        rows.append({"Trajet":f"Casa→{v2}", "Dist.":f"{d}km",
                     "1kg":f"{math.ceil((15+1*2.5+d*0.8)*2)/2} MAD",
                     "5kg":f"{math.ceil((15+5*2.5+d*0.8)*2)/2} MAD",
                     "10kg":f"{math.ceil((15+10*2.5+d*0.8)*2)/2} MAD"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if "id_token" not in st.session_state:
        login_page()
        return

    page = sidebar()

    if   page == "📊 Tableau de bord":  tab_dashboard()
    elif page == "👥 Utilisateurs":     tab_users()
    elif page == "🆔 KYC":              tab_kyc()
    elif page == "📦 Demandes":         tab_demandes()
    elif page == "🛣️ Trajets":          tab_trajets()
    elif page == "⚠️ Litiges":          tab_litiges()
    elif page == "🔔 Notifications":    tab_notifications()
    elif page == "💰 Tarification":     tab_tarification()


if __name__ == "__main__":
    main()
