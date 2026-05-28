import os
import shutil
import tempfile
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from navigator import navigate_to_cell
from search_engine import (
    load_file_to_cache,
    remove_file_from_cache,
    search_multiple_files,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploaded_files"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Excel Search Tool")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup: preload excel cache ──────────────────────────────────────────────
@app.on_event("startup")
def preload_existing_files():
    count = 0
    for f in UPLOAD_DIR.iterdir():
        if f.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
            try:
                n = load_file_to_cache(str(f))
                print(f"[PRELOAD] {f.name} → {n} cells")
                count += 1
            except Exception as e:
                print(f"[PRELOAD ERROR] {f.name}: {e}")
    print(f"[STARTUP] preloaded {count} file(s)")


# ── Models ────────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    keyword:        str
    file_names:     List[str]
    case_sensitive: bool = False
    use_regex:      bool = False
    fuzzy:          bool = True
    score_cutoff:   int  = 60


class NavigateRequest(BaseModel):
    file_name:  str
    sheet_name: str
    cell_ref:   str


# ── API Routes (ต้องประกาศก่อน static mount) ─────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/files")
def list_files():
    files = []
    for f in UPLOAD_DIR.iterdir():
        if f.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
            files.append({"name": f.name, "size": f.stat().st_size})
    return {"files": files}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
        raise HTTPException(400, "รองรับเฉพาะไฟล์ Excel (.xlsx, .xls, .xlsm)")

    save_path = UPLOAD_DIR / file.filename
    content   = await file.read()

    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(UPLOAD_DIR), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(content)

        if save_path.exists():
            try:
                save_path.unlink()
            except PermissionError:
                Path(tmp_path).unlink(missing_ok=True)
                raise HTTPException(423, f"ไฟล์ '{file.filename}' กำลังเปิดอยู่ กรุณาปิดก่อน")

        Path(tmp_path).rename(save_path)

    except HTTPException:
        raise
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(500, f"บันทึกไฟล์ไม่สำเร็จ: {e}")

    try:
        n = load_file_to_cache(str(save_path))
        print(f"[CACHE] {file.filename} → {n} cells")
    except Exception as e:
        print(f"[CACHE ERROR] {file.filename}: {e}")

    return {"filename": file.filename, "message": "อัปโหลดสำเร็จ"}


@app.delete("/api/files/{filename}")
def delete_file(filename: str):
    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(404, f"ไม่พบไฟล์: {safe_name}")

    try:
        file_path.unlink()
        remove_file_from_cache(safe_name)
        return {"message": f"ลบ '{safe_name}' สำเร็จ"}
    except PermissionError:
        raise HTTPException(423, f"ไฟล์ '{safe_name}' กำลังเปิดอยู่ กรุณาปิดก่อน")
    except Exception as e:
        raise HTTPException(500, f"ลบไฟล์ไม่สำเร็จ: {e}")


@app.post("/api/search")
def search(req: SearchRequest):
    if not req.keyword.strip():
        raise HTTPException(400, "กรุณาระบุ keyword")

    file_paths = []
    for name in req.file_names:
        base = Path(name).name
        path = UPLOAD_DIR / base
        if path.exists():
            file_paths.append(str(path))

    if not file_paths:
        return {"total": 0, "results": [], "error": "ไม่พบไฟล์ที่ระบุ"}

    results = search_multiple_files(
        file_paths=file_paths,
        keyword=req.keyword,
        case_sensitive=req.case_sensitive,
        use_regex=req.use_regex,
        fuzzy=req.fuzzy,
        score_cutoff=req.score_cutoff,
    )

    return {
        "total": len(results),
        "results": [
            {
                "file_name":  str(r.file_name),
                "sheet_name": str(r.sheet_name),
                "row":        int(r.row),
                "col":        int(r.col),
                "cell_ref":   str(r.cell_ref),
                "cell_value": str(r.cell_value),
                "context":    str(r.context),
                "score":      int(r.score),
            }
            for r in results
        ],
    }


@app.post("/api/navigate")
def navigate(req: NavigateRequest):
    base      = Path(req.file_name).name
    file_path = UPLOAD_DIR / base
    if not file_path.exists():
        raise HTTPException(404, f"ไม่พบไฟล์: {base}")
    result = navigate_to_cell(str(file_path), req.sheet_name, req.cell_ref)
    return result


# ── Static Files + SPA Fallback ───────────────────────────────────────────────
# ⚠️ ต้องประกาศหลัง API routes ทั้งหมด
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    # Mount assets folder (js/css/images)
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve favicon และไฟล์ static อื่นๆ ที่ root
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        f = STATIC_DIR / "favicon.ico"
        if f.exists():
            return FileResponse(str(f))
        raise HTTPException(404)

    # SPA Fallback — ทุก path ที่ไม่ใช่ /api/* จะได้รับ index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        # ถ้าเป็น file จริงๆ ใน static folder ให้ส่งตรงๆ
        requested = STATIC_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(str(requested))
        # ทุกอย่างอื่น → index.html (React Router จัดการ)
        return FileResponse(str(STATIC_DIR / "index.html"))

else:
    @app.get("/", include_in_schema=False)
    def root_no_frontend():
        return {
            "message": "Excel Search Tool API running",
            "note": "Frontend not built. Run: cd frontend && npm run build && cp -r dist ../backend/static",
        }

    print("[WARNING] frontend/static not found — serving API only")