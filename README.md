# Excel Search Tool

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

เปิด http://localhost:5173

---

## Deploy บน Railway

### ขั้นตอน

1. **Build frontend ก่อน**
```bash
cd frontend
npm install
npm run build
# copy dist → backend/static
cp -r dist ../backend/static
```

2. **Push ขึ้น GitHub**
```bash
git add .
git commit -m "deploy"
git push
```

3. **Railway Settings**
- Root Directory: `backend`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment Variables:
  - `ALLOWED_ORIGINS` = `https://your-app.railway.app`

4. Railway จะ deploy อัตโนมัติ

---

## โครงสร้างไฟล์

```
excel-search-tool/
├── railway.json
├── nixpacks.toml
├── Procfile
├── .gitignore
├── backend/
│   ├── main.py
│   ├── search_engine.py
│   ├── navigator.py
│   ├── requirements.txt
│   ├── uploaded_files/    ← Excel files (auto-created)
│   └── static/            ← Frontend build output
└── frontend/
    ├── src/
    │   └── App.jsx
    ├── vite.config.js
    └── package.json
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | 8000 | Railway จัด auto |
| `ALLOWED_ORIGINS` | `*` | CORS origins คั่นด้วย comma |
