# Swiftli Admin Dashboard

Tableau de bord administrateur pour Swiftli — gestion KYC, utilisateurs, demandes, trajets, litiges.

## 🚀 Déploiement sur Streamlit Cloud

1. Va sur [share.streamlit.io](https://share.streamlit.io)
2. Connecte ton compte GitHub
3. Clique sur **"New app"** et sélectionne ce repo
4. Main file path : `admin_dashboard.py`
5. **Settings → Secrets** → colle le contenu de `.streamlit/secrets.toml.example` (avec tes vraies clés)
6. Deploy → tu obtiens une URL publique du type `https://swiftli-admin.streamlit.app`

## 🔐 Accès équipe

Le dashboard vérifie 2 conditions au login :
1. Le compte Firebase existe (signup via l'app Swiftli)
2. L'email est dans la liste `ADMIN_EMAILS` (secrets) **OU** le champ `role="admin"` dans Firestore

Pour ajouter un coéquipier :
- Édite la variable `ADMIN_EMAILS` dans les secrets Streamlit
- Sépare par virgules : `alice@swiftli.ma,bob@swiftli.ma`

## 💻 Lancement local

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Édite .streamlit/secrets.toml avec tes vraies clés
streamlit run admin_dashboard.py
```

## 📋 Fonctionnalités

- 📊 Tableau de bord temps réel (utilisateurs, demandes, CA, KYC en attente)
- 👥 Gestion des utilisateurs (rôles, KYC)
- 🆔 Vérification KYC avec photos (CIN recto/verso + photo profil)
- 📦 Suivi des demandes
- 🛣️ Gestion des trajets
- ⚠️ Résolution de litiges
- 🔔 Envoi de notifications
- 💰 Simulateur de tarification
