import os
import platform
import time


def navigate_to_cell(file_path: str, sheet_name: str, cell_ref: str) -> dict:
    system   = platform.system()
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        return {"success": False, "message": f"ไม่พบไฟล์: {abs_path}"}

    # Railway (Linux) ไม่มี Excel — return location info แทน
    if system not in ("Windows", "Darwin"):
        return {
            "success": True,
            "message": f"ตำแหน่ง: {sheet_name}!{cell_ref} (Server mode — ไม่สามารถเปิด Excel ได้)",
            "server_mode": True,
        }

    if system == "Windows":
        return _navigate_windows(abs_path, sheet_name, cell_ref)
    return _navigate_mac(abs_path, sheet_name, cell_ref)


def _navigate_windows(abs_path: str, sheet_name: str, cell_ref: str) -> dict:
    try:
        import xlwings as xw

        wb = None
        app = None
        try:
            for a in xw.apps:
                for book in a.books:
                    if os.path.normcase(book.fullname) == os.path.normcase(abs_path):
                        wb = book
                        app = a
                        break
                if wb:
                    break
        except Exception:
            pass

        if wb is None:
            app = xw.App(visible=True)
            wb  = app.books.open(abs_path)

        sheet  = wb.sheets[sheet_name]
        sheet.activate()
        target = sheet.range(cell_ref)
        target.select()

        original_color = target.color
        for _ in range(3):
            target.color = (255, 255, 0)
            time.sleep(0.15)
            target.color = (255, 165, 0)
            time.sleep(0.15)
        time.sleep(2.0)
        target.color = original_color if original_color else None

        try:
            app.activate(steal_focus=True)
        except Exception:
            pass

        return {"success": True, "message": f"นำทางไปยัง {sheet_name}!{cell_ref} สำเร็จ"}

    except ImportError:
        return {"success": False, "message": "ไม่พบ xlwings: py -m pip install xlwings"}
    except Exception as e:
        return {"success": False, "message": f"เกิดข้อผิดพลาด: {e}"}


def _navigate_mac(abs_path: str, sheet_name: str, cell_ref: str) -> dict:
    try:
        import xlwings as xw

        wb     = xw.Book(abs_path)
        sheet  = wb.sheets[sheet_name]
        sheet.activate()
        target = sheet.range(cell_ref)
        target.select()

        original_color = target.color
        for _ in range(3):
            target.color = (255, 255, 0)
            time.sleep(0.15)
            target.color = (255, 165, 0)
            time.sleep(0.15)
        time.sleep(2.0)
        target.color = original_color if original_color else None

        return {"success": True, "message": f"นำทางไปยัง {sheet_name}!{cell_ref} สำเร็จ"}
    except Exception as e:
        return {"success": False, "message": f"เกิดข้อผิดพลาด: {e}"}
