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
STATIC_DIR = BASE_DIR / "static"          # frontend build output
UPLOAD_DIR.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Excel Search Tool")

# CORS — อนุญาตทุก origin ใน dev / Railway จัดการ HTTPS เอง
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup: preload ทุกไฟล์ที่มีอยู่แล้ว ────────────────────────────────────
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


# ── API Endpoints ─────────────────────────────────────────────────────────────
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


# ── Serve React Frontend (production) ────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """ส่ง index.html ให้ React Router จัดการ"""
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built yet"}
