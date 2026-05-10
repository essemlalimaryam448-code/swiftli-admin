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

# ─── Couleurs ─────────────────────────────────────────────────────────────────
GREEN   = "#1D9E75"
GREEN_D = "#0F6E56"
AMBER   = "#EF9F27"
RED     = "#E24B4A"
BLUE    = "#185FA5"

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Swiftli Admin", page_icon="📦", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown(f"""
<style>
  [data-testid="stSidebar"] {{
      background: linear-gradient(160deg, {GREEN_D} 0%, #062e1e 100%);
  }}
  [data-testid="stSidebar"] * {{ color: white !important; }}
  [data-testid="metric-container"] {{
      background: white; border: 1px solid #E5E7EB;
      border-radius: 14px; padding: 16px;
      box-shadow: 0 1px 4px rgba(0,0,0,.06);
  }}
  .section-title {{
      font-size: 1.15rem; font-weight: 700; color: {GREEN_D};
      margin-bottom: 1rem; padding-bottom: 6px;
      border-bottom: 2px solid {GREEN};
  }}
  .badge-pending  {{ background:#FEF3C7; color:#92400E; padding:2px 10px; border-radius:99px; font-size:.8rem; }}
  .badge-approved {{ background:#D1FAE5; color:#065F46; padding:2px 10px; border-radius:99px; font-size:.8rem; }}
  .badge-rejected {{ background:#FEE2E2; color:#991B1B; padding:2px 10px; border-radius:99px; font-size:.8rem; }}
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
    st.caption(f"**{label}**")
    if not url:
        st.markdown(
            "<div style='background:#F3F4F6;border-radius:8px;height:140px;"
            "display:flex;align-items:center;justify-content:center;"
            "color:#9CA3AF;font-size:13px'>Non fourni</div>",
            unsafe_allow_html=True)
        return

    display_url = _signed_url(url)
    try:
        st.image(display_url, use_container_width=True)
        st.markdown(f"<a href='{display_url}' target='_blank' "
                    "style='font-size:11px;color:#6B7280'>"
                    "🔗 Ouvrir en plein écran</a>",
                    unsafe_allow_html=True)
    except Exception as e:
        st.error(f"⚠️ Photo inaccessible")
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
        return (f"<div style='background:#D1FAE5;color:#065F46;padding:10px 14px;"
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
        <div style="text-align:center;padding:32px 0 16px">
            <div style="font-size:3rem">📦</div>
            <h1 style="color:{GREEN_D};margin:0">Swiftli Admin</h1>
            <p style="color:#6B7280">Connectez-vous avec votre compte Firebase</p>
        </div>""", unsafe_allow_html=True)
        with st.form("login"):
            email    = st.text_input("📧 Email", placeholder="votre@email.com")
            password = st.text_input("🔑 Mot de passe", type="password")
            ok       = st.form_submit_button("Se connecter", use_container_width=True)
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
        st.markdown(f"""
        <div style="text-align:center;padding:20px 0 10px">
            <div style="font-size:2.5rem">📦</div>
            <h2 style="margin:4px 0;font-weight:800">Swiftli</h2>
            <small>Admin Dashboard v2.0</small><br>
            <small style="opacity:.7">{st.session_state.get("user_email","")}</small>
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
        if st.button("🚪 Déconnexion", use_container_width=True):
            for k in ["id_token", "local_id", "user_email"]:
                st.session_state.pop(k, None)
            st.rerun()
    return page


# ─── 1. Tableau de bord ───────────────────────────────────────────────────────
def tab_dashboard():
    st.markdown('<div class="section-title">📊 Vue d\'ensemble en temps réel</div>',
                unsafe_allow_html=True)

    with st.spinner("Chargement des données..."):
        users    = fs_get("users",    _token())
        demandes = fs_get("demandes", _token())
        trajets  = fs_get("trajets",  _token())
        reclams  = fs_get("reclamations", _token())

    # ── KPIs ──────────────────────────────────────────────────────────────────
    ca = sum(float(d.get("prixPropose", 0)) for d in demandes
             if d.get("paiementStatut") == "payé")
    kyc_pending = sum(1 for u in users if u.get("kycStatut") == "en_verification")
    livrees = sum(1 for d in demandes if d.get("statut") == "livree")

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("👥 Utilisateurs",   len(users))
    c2.metric("📦 Demandes",       len(demandes))
    c3.metric("🛣️ Trajets",        len(trajets))
    c4.metric("💰 CA (MAD)",       f"{ca:,.0f}")
    c5.metric("🆔 KYC en attente", kyc_pending)
    c6.metric("⚠️ Réclamations",   len(reclams))

    st.markdown("---")
    col_g1, col_g2, col_g3 = st.columns(3)

    # Demandes par statut
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
            df = pd.DataFrame([{"Statut": labels_fr.get(k,k), "Nombre": v}
                                for k, v in statuts.items()])
            fig = px.pie(df, names="Statut", values="Nombre", hole=0.42,
                         color_discrete_sequence=[GREEN,AMBER,BLUE,"#8B5CF6",RED,GREEN_D])
            fig.update_layout(margin=dict(t=0,b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune demande.")

    # KYC statuts
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
            df_k = pd.DataFrame([{"Statut": kyc_labels.get(k,k), "Nombre": v}
                                  for k,v in kyc_counts.items()])
            fig2 = px.bar(df_k, x="Statut", y="Nombre",
                          color="Statut",
                          color_discrete_map={
                              "Non soumis":"#9CA3AF","En attente":AMBER,
                              "Approuvé":GREEN,"Rejeté":RED,
                          })
            fig2.update_layout(margin=dict(t=0,b=0), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
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

    # Récentes demandes
    st.markdown("---")
    st.subheader("📦 Dernières demandes")
    if demandes:
        df_d = pd.DataFrame([{
            "ID":        d["_id"][:8],
            "Départ":    d.get("villeDepart",""),
            "Arrivée":   d.get("villeArrivee",""),
            "Expéditeur":d.get("expediteurNom",""),
            "Prix":      f"{d.get('prixPropose',0)} MAD",
            "Statut":    d.get("statut",""),
            "Paiement":  d.get("paiementStatut",""),
        } for d in reversed(demandes[-15:])])
        st.dataframe(df_d, use_container_width=True, hide_index=True)


# ─── 2. Utilisateurs ──────────────────────────────────────────────────────────
def tab_users():
    st.markdown('<div class="section-title">👥 Gestion des Utilisateurs</div>',
                unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        users = fs_get("users", _token())

    if not users:
        st.info("Aucun utilisateur.")
        return

    # Filtres
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        search = st.text_input("🔍 Rechercher (nom, email, UID)", "")
    with col_f2:
        role_f = st.selectbox("Rôle", ["Tous", "user", "admin", "voyageur"])
    with col_f3:
        kyc_f = st.selectbox("KYC", ["Tous", "non_soumis", "en_verification", "approuve", "rejete"])

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

    st.info(f"**{len(filtered)}** utilisateur(s) trouvé(s)")

    # Tableau
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
    st.dataframe(df, use_container_width=True, hide_index=True)

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
    st.markdown('<div class="section-title">🆔 KYC — Vérification d\'identité</div>',
                unsafe_allow_html=True)

    with st.spinner("Chargement depuis Firestore..."):
        users = fs_get("users", _token())

    # Séparer par statut KYC
    kyc_users = [u for u in users
                 if u.get("kycStatut") in ("en_verification","approuve","rejete")
                 or u.get("cinRectoUrl") or u.get("cinVersoUrl")]

    # Métriques
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Total dossiers",  len(kyc_users))
    m2.metric("🟡 En attente",  sum(1 for u in kyc_users if u.get("kycStatut")=="en_verification"))
    m3.metric("🟢 Approuvés",   sum(1 for u in kyc_users if u.get("kycStatut")=="approuve"))
    m4.metric("🔴 Rejetés",     sum(1 for u in kyc_users if u.get("kycStatut")=="rejete"))

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
    st.markdown('<div class="section-title">📦 Gestion des Demandes</div>',
                unsafe_allow_html=True)

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
    c1.metric("Total",         len(demandes))
    c2.metric("En attente",    statuts_count.get("en_attente",0))
    c3.metric("En cours",      statuts_count.get("en_cours",0))
    c4.metric("Livrées",       statuts_count.get("livree",0))
    c5.metric("CA encaissé",   f"{ca:,.0f} MAD")

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
    st.markdown('<div class="section-title">🛣️ Trajets publiés</div>', unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        trajets = fs_get("trajets", _token())

    if not trajets:
        st.info("Aucun trajet.")
        return

    st.metric("Total trajets", len(trajets))
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
    st.markdown('<div class="section-title">⚠️ Litiges & Réclamations</div>',
                unsafe_allow_html=True)

    with st.spinner("Chargement..."):
        demandes = fs_get("demandes",      _token())
        reclams  = fs_get("reclamations",  _token())

    litiges = [d for d in demandes if "litige" in d.get("statut","")]

    st.subheader(f"Demandes en litige ({len(litiges)})")
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
    st.markdown('<div class="section-title">🔔 Notifications</div>', unsafe_allow_html=True)

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
    st.markdown('<div class="section-title">💰 Simulateur de tarification</div>',
                unsafe_allow_html=True)
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
            x=["Base","Poids","Distance"],
            y=[15, poids*2.5, dist*0.8],
            marker_color=[GREEN, BLUE, AMBER],
        ))
        fig.update_layout(height=220, margin=dict(t=10,b=10), yaxis_title="MAD")
        st.plotly_chart(fig, use_container_width=True)
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
