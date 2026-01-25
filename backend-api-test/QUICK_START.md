# Guide de démarrage rapide

## Problème: "Connection Failed, Connexion refused"

### Solution 1: Utiliser le frontend servi par Flask (RECOMMANDÉ)

1. **Démarrer le backend:**
```bash
cd backend-api-test
./start.sh
```

2. **Ouvrir dans le navigateur:**
```
http://localhost:5001/app
```

✅ **C'est la méthode la plus simple !** Le backend sert automatiquement le frontend.

---

### Solution 2: Servir le frontend avec un serveur HTTP

Si tu préfères ouvrir `frontend/index.html` directement:

1. **Démarrer le backend** (dans un terminal):
```bash
cd backend-api-test
./start.sh
```

2. **Servir le frontend** (dans un autre terminal):
```bash
cd backend-api-test
python3 -m http.server 8080
```

3. **Ouvrir dans le navigateur:**
```
http://localhost:8080/frontend/index.html
```

---

### Solution 3: Vérifier que le backend est bien démarré

```bash
# Vérifier si le backend répond
curl http://localhost:5001/api/health

# Devrait retourner:
# {"status":"ok","message":"OKU Desk API is running","version":"0.1.0"}
```

Si ça ne fonctionne pas:
```bash
# Vérifier les processus Python
ps aux | grep "app.py"

# Vérifier les ports
lsof -i :5001
```

---

## ⚠️ Erreur CORS avec file://

Si tu ouvres `frontend/index.html` directement (double-clic), tu auras une erreur CORS car les navigateurs bloquent les requêtes HTTP depuis `file://`.

**Solutions:**
- Utilise `http://localhost:5001/app` (servi par Flask)
- Ou utilise un serveur HTTP (Solution 2)

---

## Ports utilisés

- **Backend API:** Port 5001 (ou auto-détecté 5001-5010)
- **Frontend (optionnel):** Port 8080 (si tu utilises `python -m http.server`)

---

## Test rapide

```bash
# Terminal 1: Backend
cd backend-api-test && ./start.sh

# Terminal 2: Test API
curl http://localhost:5001/api/health

# Navigateur: Frontend
# Ouvre: http://localhost:5001/app
```
