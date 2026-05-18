from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, send_from_directory, Response
import json
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
from datetime import datetime
import os, json, math

app = Flask(__name__)
app.secret_key = "knowledge-platform-secret-2026"

BASE        = "data"
MD          = f"{BASE}/master_data"
RD          = f"{BASE}/reference_data"
CD          = f"{BASE}/catalog"
PD          = f"{BASE}/platform_data"
UPLOAD_DIR  = "static/uploads"
DEFAULT_PASS= "Pass1234!"

# Common columns for Content Hub = VISIBLE_COLS
COMMON_COLS = [
    "Primary Thematic", "Platform", "Content Family", "Content Types",
    "Content Name (EN)", "Content Name (FR)", "Content Description",
    "Content Published Link", "Owner Team", "Author Team", "Contact Team",
    "Published Date", "Last Update Date"
]

# Common columns for Document Hub (first 10 of document_hub.csv)
COMMON_COLS_DOC = [
    "ID", "Content Family", "Content Types", "Category",
    "Owner Team", "Author Team", "Contact Team",
    "Doc Name (FR)", "Doc Name (EN)", "Instance name"
]


os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── HELPERS ───────────────────────────────────────────────────
def csv_read(path):
    """Read CSV with encoding fallback and clean column names."""
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            df = pd.read_csv(path, encoding=enc).fillna("")
            # Strip whitespace and non-breaking spaces from column names
            df.columns = [c.strip().replace('\xa0',' ').replace('\t',' ') for c in df.columns]
            return df
        except Exception:
            continue
    return pd.DataFrame()

def csv_write(path, df):
    df.to_csv(path, index=False, encoding="utf-8-sig")

def load_ref(name):
    return csv_read(f"{RD}/{name}.csv").to_dict("records")

def load_taxonomy():
    df = csv_read(f"{RD}/org_taxonomy.csv")
    tax = {}
    for _, r in df.iterrows():
        d, sd, t = str(r["Department"]), str(r["Sub Department"]), str(r["Team"])
        if d not in tax: tax[d] = {}
        if sd not in tax[d]: tax[d][sd] = []
        tax[d][sd].append(t)
    return tax

def load_all_catalog():
    """Load Content Hub data from content_hub.csv"""
    path = f"{CD}/content_hub.csv"
    if not os.path.exists(path):
        return []
    df = csv_read(path)
    if df.empty: return []
    df["List Name"] = "Content Hub"
    return df.to_dict("records")

def load_doc_catalog():
    """Load Document Hub data from document_hub.csv"""
    path = f"{CD}/document_hub.csv"
    if not os.path.exists(path):
        return []
    df = csv_read(path)
    if df.empty: return []
    df["List Name"] = "Document Hub"
    return df.to_dict("records")

def load_data_catalog():
    """Load Data Catalog data from business_glossary.csv"""
    path = f"{CD}/business_glossary.csv"
    if not os.path.exists(path):
        return []
    df = csv_read(path)
    if df.empty: return []
    df["List Name"] = "Data Catalog"
    return df.to_dict("records")

def get_custom_cols(rows):
    result = {}
    for row in rows:
        ln = row.get("List Name","")
        if ln not in result:
            result[ln] = sorted([k for k in row.keys() if k not in COMMON_COLS])
    return result

def clean(rows):
    """Convertit toutes les valeurs en types JSON-serialisables."""
    def safe(v):
        if v is None: return ""
        try:
            import numpy as np
            if isinstance(v, (np.integer,)): return int(v)
            if isinstance(v, (np.floating,)):
                return "" if math.isnan(v) else float(v)
            if isinstance(v, np.bool_): return bool(v)
        except ImportError:
            pass
        if isinstance(v, float):
            return "" if math.isnan(v) else v
        if not isinstance(v, (str, int, float, bool)):
            return str(v)
        return v
    return [{k: safe(v) for k, v in row.items()} for row in rows]

def clean_dict(d):
    """Nettoie un dict simple (row de CSV)."""
    return {k: ("" if (not isinstance(v,(str,int,float,bool)) or (isinstance(v,float) and math.isnan(v))) else v)
            for k, v in d.items()}

# ── AUTH ──────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **k):
        if "uid" not in session: return redirect(url_for("login"))
        return f(*a, **k)
    return d

def cur_user():
    if "uid" not in session: return None
    df = csv_read(f"{PD}/users.csv")
    row = df[df["Username"] == session.get("username","")]
    if row.empty: return None
    u = row.iloc[0].to_dict()
    # Normalise les clés importantes
    u.setdefault("team",       u.get("Team",""))
    u.setdefault("department", u.get("Department",""))
    u.setdefault("sub_department", u.get("Sub Department",""))
    u.setdefault("username",   u.get("Username",""))
    u.setdefault("full_name",  u.get("User Name",""))
    u.setdefault("Access Group", u.get("access_group","Read Only"))
    # Clé minuscule pour Jinja (user.access_group)
    u["access_group"] = u.get("Access Group", "Read Only")
    return clean_dict(u)

def notif_count(u):
    return session.get("notif_count", 0)

def ctx():
    u = cur_user()
    if not u: return {}
    try:
        all_rows      = load_all_catalog()
        catalog_count      = len(all_rows)
        doc_count          = len(load_doc_catalog())
        data_catalog_count = len(load_data_catalog())
        emp_count     = len(csv_read(f"{MD}/employees.csv"))
        faq_count     = len(csv_read(f"{PD}/faq.csv"))
        ev_count      = len(csv_read(f"{PD}/events.csv"))
    except:
        catalog_count = emp_count = faq_count = ev_count = doc_count = data_catalog_count = 0
    return {
        "user": u,
        "notif_count": notif_count(u),
        "catalog_count":      catalog_count,
        "doc_count":          doc_count,
        "data_catalog_count": data_catalog_count,
        "emp_count": emp_count,
        "faq_count": faq_count,
        "ev_count": ev_count,
    }

# ── ROUTES: PAGES ─────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("login") if "uid" not in session else url_for("catalog"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        df = csv_read(f"{PD}/users.csv")
        row = df[df["Username"] == username]
        if not row.empty:
            stored = str(row.iloc[0].get("Password",""))
            ok = (password == DEFAULT_PASS) or (stored and check_password_hash(stored, password))
            if ok:
                u = row.iloc[0].to_dict()
                session.update({
                    "uid":           str(u.get("UserID","")),
                    "username":      str(u.get("Username","")),
                    "full_name":     str(u.get("User Name","")),
                    "team":          str(u.get("Team","")),
                    "department":    str(u.get("Department","")),
                    "sub_department":str(u.get("Sub Department","")),
                    "access_group":  str(u.get("Access Group","Read Only")),
                    "notif_count":   0
                })
                return redirect(url_for("catalog"))
        flash("Identifiants incorrects")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/catalog")
@login_required
def catalog():
    import json as _json
    rows = load_all_catalog()
    plats = sorted(set(
        p.strip() for r in rows
        for p in str(r.get("Platform","")).split(";") if p.strip()
    ))
    dates      = sorted([r.get("Published Date","") for r in rows if r.get("Published Date","")])
    teams      = sorted(set(str(r.get("Owner Team","")) for r in rows if r.get("Owner Team","")))
    categories = sorted(set(str(r.get("Primary Thematic","")) for r in rows if r.get("Primary Thematic","")))
    return render_template("catalog.html",
        platforms_json  = _json.dumps(plats),
        rows_json       = _json.dumps(clean(rows)),
        teams_json      = _json.dumps(teams),
        categories_json = _json.dumps(categories),
        date_min        = dates[0]  if dates else "2023-01-01",
        date_max        = dates[-1] if dates else "2025-12-31",
        **ctx())

@app.route("/kanban")
@login_required
def kanban():
    from flask import redirect
    return redirect("/catalog?view=card")

@app.route("/datacatalog")
@login_required
def datacatalog():
    import json as _json
    rows = load_data_catalog()
    plats = sorted(set(
        p.strip() for r in rows
        for p in str(r.get("Platform","")).split(";") if p.strip()
    ))
    dates      = sorted([r.get("Published Date","") for r in rows if r.get("Published Date","")])
    teams      = sorted(set(str(r.get("Owner Team","")) for r in rows if r.get("Owner Team","")))
    categories = sorted(set(str(r.get("Category","")) for r in rows if r.get("Category","")))
    return render_template("datacatalog.html",
        platforms_json  = _json.dumps(plats),
        rows_json       = _json.dumps(clean(rows)),
        teams_json      = _json.dumps(teams),
        categories_json = _json.dumps(categories),
        date_min        = dates[0]  if dates else "2023-01-01",
        date_max        = dates[-1] if dates else "2025-12-31",
        **ctx())

@app.route("/dochub")
@login_required
def dochub():
    import json as _json
    rows = load_doc_catalog()
    plats = sorted(set(
        p.strip() for r in rows
        for p in str(r.get("Platform","")).split(";") if p.strip()
    ))
    dates      = sorted([r.get("Published Date","") for r in rows if r.get("Published Date","")])
    teams      = sorted(set(str(r.get("Owner Team","")) for r in rows if r.get("Owner Team","")))
    categories = sorted(set(str(r.get("Primary Thematic","")) for r in rows if r.get("Primary Thematic","")))
    return render_template("dochub.html",
        platforms_json  = _json.dumps(plats),
        rows_json       = _json.dumps(clean(rows)),
        teams_json      = _json.dumps(teams),
        categories_json = _json.dumps(categories),
        date_min        = dates[0]  if dates else "2022-01-01",
        date_max        = dates[-1] if dates else "2025-12-31",
        **ctx())

@app.route("/pole")
@login_required
def pole():
    import json as _json
    org  = pd.read_csv(f"{RD}/org_taxonomy.csv", encoding="utf-8-sig").fillna("")
    acts = pd.read_csv(f"{RD}/activity_taxonomy.csv", encoding="utf-8-sig").fillna("")
    emps = pd.read_csv(f"{MD}/employees.csv", encoding="utf-8-sig").fillna("")
    
    # Construire un dict dept -> {teams, sub_depts, nb_people, activities}
    intro_data = {}
    for dept in org["Department"].unique():
        dept_rows = org[org["Department"]==dept]
        emp_rows  = emps[emps["Department"]==dept]
        dept_acts = acts[acts["Activity Category"]==dept].to_dict("records")
        intro_data[dept] = {
            "sub_depts":    sorted(dept_rows["Sub Department"].unique().tolist()),
            "teams":        sorted(dept_rows["Team"].unique().tolist()),
            "nb_teams":     int(dept_rows["Team"].nunique()),
            "nb_sub_depts": int(dept_rows["Sub Department"].nunique()),
            "nb_people":    int(len(emp_rows)),
            "activities":   dept_acts,
        }
    return render_template("pole.html",
        intro_json=_json.dumps(intro_data),
        **ctx())

@app.route("/people")
@login_required
def people():
    return render_template("people.html", **ctx())

@app.route("/faq")
@login_required
def faq():
    return render_template("faq.html", **ctx())

@app.route("/calendar")
@login_required
def calendar_page():
    import json as _json
    # Lecture directe du CSV events avec pandas
    df = pd.read_csv(f"{PD}/events.csv", encoding="utf-8-sig").fillna("")
    events = []
    for _, row in df.iterrows():
        events.append({
            "id":          str(row.get("Event ID","")),
            "title":       str(row.get("Title","")),
            "date":        str(row.get("Start Date","")),
            "end_date":    str(row.get("End Date","")),
            "team":        str(row.get("Team","")),
            "department":  str(row.get("Department","")),
            "location":    str(row.get("Location","")),
            "description": str(row.get("Description","")),
        })
    return render_template("calendar.html",
        events_json=_json.dumps(events),
        **ctx())

# ── API: CATALOG ──────────────────────────────────────────────
@app.route("/api/notifications")
@login_required
def api_notifications():
    notifs = session.get("notifications", [])
    return jsonify({"notifications": notifs})

@app.route("/api/notifications/clear", methods=["POST"])
@login_required
def api_notifications_clear():
    session["notifications"] = []
    session["notif_count"]   = 0
    return jsonify({"ok": True})

# ── Document versions JSON path ──────────────────────────────
DOC_VERSIONS_PATH = f"{BASE}/catalog/doc_versions.json"
DOC_UPLOADS_DIR   = os.path.join("static", "uploads", "docs")
os.makedirs(DOC_UPLOADS_DIR, exist_ok=True)

def load_doc_versions():
    try:
        with open(DOC_VERSIONS_PATH) as f: return json.load(f)
    except: return {}

def save_doc_versions(data):
    with open(DOC_VERSIONS_PATH, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)

def can_edit():
    u = cur_user()
    return u.get("access_group","Read Only") in ("Editor","Super Admin")

@app.route("/api/doc/versions/<doc_id>")
@login_required
def api_doc_versions(doc_id):
    data = load_doc_versions()
    return jsonify(data.get(doc_id, {"files":[], "links":[]}))

@app.route("/api/doc/upload/<doc_id>", methods=["POST"])
@login_required
def api_doc_upload(doc_id):
    if not can_edit(): return jsonify({"error":"Unauthorized"}), 403
    import datetime
    f = request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    fname = f"{doc_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"
    fpath = os.path.join(DOC_UPLOADS_DIR, fname)
    f.save(fpath)
    data = load_doc_versions()
    if doc_id not in data: data[doc_id] = {"files":[], "links":[]}
    u = cur_user()
    entry = {
        "filename": fname,
        "original": f.filename,
        "size": os.path.getsize(fpath),
        "date": datetime.datetime.now().strftime("%d %b %Y"),
        "author": u.get("username","?"),
        "current": True
    }
    # Previous current → not current
    for v in data[doc_id]["files"]: v["current"] = False
    data[doc_id]["files"].insert(0, entry)
    save_doc_versions(data)
    return jsonify({"ok": True, "entry": entry})

@app.route("/api/doc/download/<doc_id>/<filename>")
@login_required
def api_doc_download(doc_id, filename):
    from flask import send_from_directory
    return send_from_directory(DOC_UPLOADS_DIR, filename, as_attachment=True)

@app.route("/api/doc/delete-file/<doc_id>/<filename>", methods=["POST"])
@login_required
def api_doc_delete_file(doc_id, filename):
    if not can_edit(): return jsonify({"error":"Unauthorized"}), 403
    data = load_doc_versions()
    if doc_id in data:
        data[doc_id]["files"] = [v for v in data[doc_id]["files"] if v["filename"] != filename]
        save_doc_versions(data)
    fpath = os.path.join(DOC_UPLOADS_DIR, filename)
    if os.path.exists(fpath): os.remove(fpath)
    return jsonify({"ok": True})

@app.route("/api/doc/restore-file/<doc_id>/<filename>", methods=["POST"])
@login_required
def api_doc_restore_file(doc_id, filename):
    if not can_edit(): return jsonify({"error":"Unauthorized"}), 403
    data = load_doc_versions()
    if doc_id in data:
        for v in data[doc_id]["files"]:
            v["current"] = (v["filename"] == filename)
        save_doc_versions(data)
    return jsonify({"ok": True})

@app.route("/api/doc/add-link/<doc_id>", methods=["POST"])
@login_required
def api_doc_add_link(doc_id):
    if not can_edit(): return jsonify({"error":"Unauthorized"}), 403
    import datetime
    body = request.get_json(silent=True) or {}
    url  = body.get("url","").strip()
    if not url: return jsonify({"error":"No URL"}), 400
    data = load_doc_versions()
    if doc_id not in data: data[doc_id] = {"files":[], "links":[]}
    u = cur_user()
    for lnk in data[doc_id]["links"]: lnk["current"] = False
    data[doc_id]["links"].insert(0, {
        "url":     url,
        "date":    datetime.datetime.now().strftime("%d %b %Y"),
        "author":  u.get("username","?"),
        "current": True
    })
    save_doc_versions(data)
    return jsonify({"ok": True})

@app.route("/api/doc/delete-link/<doc_id>", methods=["POST"])
@login_required
def api_doc_delete_link(doc_id):
    if not can_edit(): return jsonify({"error":"Unauthorized"}), 403
    body = request.get_json(silent=True) or {}
    url  = body.get("url","")
    data = load_doc_versions()
    if doc_id in data:
        data[doc_id]["links"] = [l for l in data[doc_id]["links"] if l["url"] != url]
        save_doc_versions(data)
    return jsonify({"ok": True})

@app.route("/api/doc/restore-link/<doc_id>", methods=["POST"])
@login_required
def api_doc_restore_link(doc_id):
    if not can_edit(): return jsonify({"error":"Unauthorized"}), 403
    body = request.get_json(silent=True) or {}
    url  = body.get("url","")
    data = load_doc_versions()
    if doc_id in data:
        for l in data[doc_id]["links"]: l["current"] = (l["url"] == url)
        save_doc_versions(data)
    return jsonify({"ok": True})

@app.route("/api/report", methods=["POST"])
@login_required
def api_report():
    import datetime
    data = request.get_json(silent=True) or {}
    u    = cur_user()
    notif = {
        "id":      f"report_{int(datetime.datetime.now().timestamp()*1000)}",
        "type":    "report",
        "message": f"⚑ Report on « {data.get('content_name','?')} » — {data.get('reason','?')} (Team: {data.get('owner_team','?')})",
        "from":    u.get("username","?"),
        "ts":      datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "note":    data.get("message",""),
    }
    notifs = session.get("notifications", [])
    notifs.insert(0, notif)
    session["notifications"] = notifs[:20]
    session["notif_count"]   = len(notifs)
    session.modified = True
    return jsonify({"ok": True})

@app.route("/api/reuse-request", methods=["POST"])
@login_required
def api_reuse_request():
    import datetime
    data = request.get_json(silent=True) or {}
    u    = cur_user()
    notif = {
        "id":      f"reuse_{int(datetime.datetime.now().timestamp()*1000)}",
        "type":    "reuse_request",
        "message": f"Reuse request for « {data.get('content_name','?')} » (Team: {data.get('owner_team','?')})",
        "from":    u.get("username","?"),
        "ts":      datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "note":    data.get("message",""),
    }
    notifs = session.get("notifications", [])
    notifs.insert(0, notif)
    session["notifications"] = notifs[:20]   # garder les 20 dernières
    session["notif_count"]   = len(notifs)
    session.modified = True
    return jsonify({"ok": True})

@app.route("/api/catalog")
@login_required
def api_catalog():
    rows = load_all_catalog()
    return jsonify({
        "rows": clean(rows),
        "common_cols": COMMON_COLS,
        "custom_cols": get_custom_cols(rows)
    })

@app.route("/api/dochub")
@login_required
def api_dochub():
    rows = load_doc_catalog()
    return jsonify({
        "rows": clean(rows),
        "common_cols": COMMON_COLS_DOC,
        "custom_cols": get_custom_cols(rows)
    })

@app.route("/api/datacatalog")
@login_required
def api_datacatalog():
    rows = load_data_catalog()
    return jsonify({
        "rows": clean(rows),
        "common_cols": COMMON_COLS,
        "custom_cols": get_custom_cols(rows)
    })

@app.route("/api/pole-data")
@login_required
def api_pole_data():
    dept    = request.args.get("department","")
    subdept = request.args.get("sub_department","")
    team    = request.args.get("team","")
    rows = load_all_catalog()
    tax  = load_taxonomy()
    if team:
        filtered = [r for r in rows if str(r.get("Owner Team","")) == team]
    elif subdept:
        teams = tax.get(dept,{}).get(subdept,[])
        filtered = [r for r in rows if str(r.get("Owner Team","")) in teams]
    elif dept:
        teams = [t for sd in tax.get(dept,{}).values() for t in sd]
        filtered = [r for r in rows if str(r.get("Owner Team","")) in teams]
    else:
        filtered = rows
    return jsonify({
        "rows": clean(filtered),
        "common_cols": COMMON_COLS,
        "custom_cols": get_custom_cols(filtered)
    })

@app.route("/api/catalog/update", methods=["POST"])
@login_required
def api_catalog_update():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    data = request.json
    list_name = data.get("list_name","")
    row_id    = data.get("id","")
    col       = data.get("column","")
    value     = data.get("value","")
    fname = list_name.replace(" ","_").lower() + ".csv"
    path  = f"{CD}/{fname}"
    if not os.path.exists(path):
        return jsonify({"error":"File not found"}), 404
    df = csv_read(path)
    if "ID" in df.columns and row_id:
        df.loc[df["ID"] == row_id, col] = value
    csv_write(path, df)
    return jsonify({"ok": True})

@app.route("/api/catalog/add-row", methods=["POST"])
@login_required
def api_catalog_add_row():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    data = request.json
    list_name = data.get("list_name","")
    fname = list_name.replace(" ","_").lower() + ".csv"
    path  = f"{CD}/{fname}"
    if not os.path.exists(path):
        return jsonify({"error":"File not found"}), 404
    df = csv_read(path)
    new_row = {col: data.get(col,"") for col in df.columns}
    if not new_row.get("Owner Team"):
        new_row["Owner Team"] = u.get("team","")
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    csv_write(path, df)
    return jsonify({"ok": True})

@app.route("/api/catalog/delete-row", methods=["POST"])
@login_required
def api_catalog_delete_row():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    data    = request.json
    list_name = data.get("list_name","")
    row_id    = data.get("id","")
    fname = list_name.replace(" ","_").lower() + ".csv"
    path  = f"{CD}/{fname}"
    if not os.path.exists(path):
        return jsonify({"error":"File not found"}), 404
    df = csv_read(path)
    df = df[df["ID"] != row_id]
    csv_write(path, df)
    return jsonify({"ok": True})

# ── API: DOCUMENTS ────────────────────────────────────────────
@app.route("/api/documents")
@login_required
def api_documents():
    dept    = request.args.get("department","")
    subdept = request.args.get("sub_department","")
    team    = request.args.get("team","")
    df = csv_read(f"{CD}/finished_documents.csv")
    if df.empty: return jsonify({"documents":[]})
    if team and "Owner Team" in df.columns:
        df = df[df["Owner Team"] == team]
    elif subdept:
        tax = load_taxonomy()
        teams = tax.get(dept,{}).get(subdept,[])
        df = df[df["Owner Team"].isin(teams)]
    elif dept:
        tax = load_taxonomy()
        teams = [t for sd in tax.get(dept,{}).values() for t in sd]
        df = df[df["Owner Team"].isin(teams)]
    return jsonify({"documents": clean(df.to_dict("records"))})

@app.route("/api/documents/upload", methods=["POST"])
@login_required
def api_documents_upload():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    if "file" not in request.files:
        return jsonify({"error":"No file"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".pdf"):
        return jsonify({"error":"PDF only"}), 400
    df = csv_read(f"{CD}/finished_documents.csv")
    title = request.form.get("title","Untitled")
    existing = df[df["English Name"] == title] if not df.empty and "English Name" in df.columns else pd.DataFrame()
    version = f"v{len(existing)+1}"
    fname = secure_filename(f"{title}_{version}_{datetime.datetime.now().strftime('%Y%m%d')}.pdf")
    fpath = os.path.join(UPLOAD_DIR, fname)
    f.save(fpath)
    fsize = os.path.getsize(fpath)
    new_row = {
        "ID": f"DOC_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "English Name": title,
        "French Name": request.form.get("french_name",""),
        "Content Category": "Document",
        "Content Sub Category": request.form.get("sub_category","Finished Document"),
        "Classification": request.form.get("classification","Internal"),
        "Description": request.form.get("description",""),
        "Owner Team": request.form.get("owner_team", u.get("team","")),
        "Contact Team": request.form.get("contact_team",""),
        "Published Links": "",
        "Version": version,
        "Upload Date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "File Path": fpath,
        "Uploaded By": u.get("username",""),
        "File Size": f"{fsize//1024} KB"
    }
    if df.empty or "ID" not in df.columns:
        df = pd.DataFrame([new_row])
    else:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    csv_write(f"{CD}/finished_documents.csv", df)
    return jsonify({"ok": True, "version": version, "filename": fname})

@app.route("/api/documents/delete", methods=["POST"])
@login_required
def api_documents_delete():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    doc_id = request.json.get("id")
    df = csv_read(f"{CD}/finished_documents.csv")
    row = df[df["ID"] == doc_id]
    if not row.empty:
        fp = str(row.iloc[0].get("File Path",""))
        if fp and os.path.exists(fp):
            os.remove(fp)
    df = df[df["ID"] != doc_id]
    csv_write(f"{CD}/finished_documents.csv", df)
    return jsonify({"ok": True})

@app.route("/uploads/<filename>")
@login_required
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ── API: REFERENCE DATA ───────────────────────────────────────
@app.route("/api/taxonomy")
@login_required
def api_taxonomy():
    return jsonify({"taxonomy": load_taxonomy()})

@app.route("/api/reference/<name>")
@login_required
def api_reference(name):
    allowed = ["org_taxonomy","activity_taxonomy","content_categories",
               "classifications","workscopes","access_groups"]
    if name not in allowed:
        return jsonify({"error":"Not found"}), 404
    return jsonify({"data": load_ref(name)})

# ── API: PEOPLE ───────────────────────────────────────────────
@app.route("/api/people")
@login_required
def api_people():
    dept    = request.args.get("department","")
    subdept = request.args.get("sub_department","")
    team    = request.args.get("team","")
    df = csv_read(f"{MD}/employees.csv")
    if team:     df = df[df["Team"] == team]
    elif subdept: df = df[df["Sub Department"] == subdept]
    elif dept:   df = df[df["Department"] == dept]
    return jsonify({"employees": clean(df.to_dict("records"))})

@app.route("/api/people/pdf/<emp_id>")
@login_required
def people_pdf(emp_id):
    return jsonify({"pdf_url": "/static/fake_org.pdf"})

# ── API: FAQ ──────────────────────────────────────────────────
@app.route("/api/faq")
@login_required
def api_faq():
    df = csv_read(f"{PD}/faq.csv")
    return jsonify({"faqs": clean(df.to_dict("records"))})

@app.route("/api/faq/ask", methods=["POST"])
@login_required
def api_faq_ask():
    u = cur_user()
    data = request.json
    df = csv_read(f"{PD}/faq.csv")
    new_id = f"FAQ_{len(df)+1:03d}"
    new_row = {
        "FAQ ID": new_id,
        "Question": data.get("question",""),
        "Asked By": u.get("username",""),
        "Answer": "", "Answered By": "",
        "Status": "pending",
        "Created At": datetime.datetime.now().strftime("%Y-%m-%d"),
        "Answered At": ""
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    csv_write(f"{PD}/faq.csv", df)
    return jsonify({"ok": True, "id": new_id})

@app.route("/api/faq/answer", methods=["POST"])
@login_required
def api_faq_answer():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    data = request.json
    df = csv_read(f"{PD}/faq.csv")
    mask = df["FAQ ID"] == data.get("id")
    df.loc[mask, "Answer"]      = data.get("answer","")
    df.loc[mask, "Answered By"] = u.get("username","")
    df.loc[mask, "Status"]      = "answered"
    df.loc[mask, "Answered At"] = datetime.datetime.now().strftime("%Y-%m-%d")
    csv_write(f"{PD}/faq.csv", df)
    return jsonify({"ok": True})

# ── API: REUSE ────────────────────────────────────────────────
REUSE_STORE = []

@app.route("/api/reuse", methods=["POST"])
@login_required
def api_reuse():
    u = cur_user()
    data = request.json
    req = {
        "id": len(REUSE_STORE)+1,
        "requester":      u.get("username",""),
        "requester_name": u.get("full_name", u.get("User Name","")),
        "requester_team": u.get("team", u.get("Team","")),
        "content_id":    data.get("content_id",""),
        "content_name":  data.get("content_name",""),
        "list_name":     data.get("list_name",""),
        "owner_team":    data.get("owner_team",""),
        "message":       data.get("message",""),
        "status":        "pending",
        "created_at":    datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    REUSE_STORE.append(req)
    return jsonify({"ok": True, "id": req["id"]})

@app.route("/api/reuse/requests")
@login_required
def api_reuse_requests():
    u = cur_user()
    if u["Access Group"] == "Super Admin":
        return jsonify({"requests": REUSE_STORE})
    tax = load_taxonomy()
    dept = u.get("department", u.get("Department",""))
    teams = [t for sd in tax.get(dept,{}).values() for t in sd]
    filtered = [r for r in REUSE_STORE if r["owner_team"] in teams]
    return jsonify({"requests": filtered})

@app.route("/api/reuse/my-requests")
@login_required
def api_my_reuse():
    u = cur_user()
    mine = [r for r in REUSE_STORE if r["requester"] == u.get("username","")]
    return jsonify({"requests": mine})

@app.route("/api/reuse/update", methods=["POST"])
@login_required
def api_reuse_update():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    data = request.json
    for r in REUSE_STORE:
        if r["id"] == data.get("id"):
            r["status"] = data.get("status","pending")
            break
    return jsonify({"ok": True})

# ── API: CALENDAR ─────────────────────────────────────────────
@app.route("/api/events", methods=["GET"])
@login_required
def api_events():
    df = csv_read(f"{PD}/events.csv")
    dept = request.args.get("department","")
    team = request.args.get("team","")
    if team and "Team" in df.columns:
        df = df[df["Team"] == team]
    elif dept and "Department" in df.columns:
        df = df[df["Department"] == dept]
    rows = clean(df.to_dict("records"))
    # Normalise TOUTES les cles pour le frontend JS
    normalized = []
    for r in rows:
        normalized.append({
            "id":          r.get("Event ID", r.get("id","")),
            "date":        r.get("Start Date", r.get("date","")),
            "end_date":    r.get("End Date", r.get("end_date","")),
            "title":       r.get("Title", r.get("title","")),
            "team":        r.get("Team", r.get("team","")),
            "department":  r.get("Department", r.get("department","")),
            "location":    r.get("Location", r.get("location","")),
            "description": r.get("Description", r.get("description","")),
            "created_by":  r.get("Created By", r.get("created_by","")),
        })
    return jsonify({"events": normalized})

@app.route("/api/events", methods=["POST"])
@login_required
def api_events_add():
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    data = request.json
    df = csv_read(f"{PD}/events.csv")
    new_id = f"EVT_{len(df)+1:03d}"
    new_row = {
        "Event ID":    new_id,
        "Title":       data.get("title",""),
        "Team":        data.get("team", u.get("team","")),
        "Department":  data.get("department", u.get("department","")),
        "Start Date":  data.get("start_date",""),
        "End Date":    data.get("end_date",""),
        "Location":    data.get("location",""),
        "Description": data.get("description",""),
        "Created By":  u.get("username","")
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    csv_write(f"{PD}/events.csv", df)
    return jsonify({"ok": True, "id": new_id})

@app.route("/api/events/<event_id>", methods=["PUT","DELETE"])
@login_required
def api_events_manage(event_id):
    u = cur_user()
    if u["Access Group"] not in ("Editor","Super Admin"):
        return jsonify({"error":"Not allowed"}), 403
    df = csv_read(f"{PD}/events.csv")
    if request.method == "DELETE":
        df = df[df["Event ID"] != event_id]
    else:
        data = request.json
        for col, val in data.items():
            if col in df.columns:
                df.loc[df["Event ID"] == event_id, col] = val
    csv_write(f"{PD}/events.csv", df)
    return jsonify({"ok": True})

# ── FAKE PDF ──────────────────────────────────────────────────
@app.route("/static/fake_org.pdf")
def fake_pdf():
    pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>
stream
BT /F1 72 Tf 220 400 Td (ORG) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
trailer<</Size 5/Root 1 0 R>>
startxref
360
%%EOF"""
    return Response(pdf_content, mimetype="application/pdf",
                    headers={"Content-Disposition": "inline; filename=ORG.pdf"})


@app.route("/api/calendar-meta")
@login_required
def api_calendar_meta():
    tax = load_taxonomy()
    teams = sorted(set(t for sd in tax.values() for teams in sd.values() for t in teams))
    depts = sorted(tax.keys())
    return jsonify({"teams": teams, "departments": depts})


@app.route("/api/pole-intro")
@login_required
def api_pole_intro():
    """Retourne les données d'intro pour un département donné."""
    dept = request.args.get("department","")
    
    org  = pd.read_csv(f"{RD}/org_taxonomy.csv", encoding="utf-8-sig").fillna("")
    acts = pd.read_csv(f"{RD}/activity_taxonomy.csv", encoding="utf-8-sig").fillna("")
    emps = pd.read_csv(f"{MD}/employees.csv", encoding="utf-8-sig").fillna("")
    
    if dept:
        dept_rows = org[org["Department"]==dept]
        emp_rows  = emps[emps["Department"]==dept]
    else:
        dept_rows = org
        emp_rows  = emps
    
    # Stats
    sub_depts = sorted(dept_rows["Sub Department"].unique().tolist())
    teams     = sorted(dept_rows["Team"].unique().tolist())
    nb_people = len(emp_rows)
    
    # Activités du département (via activity_taxonomy — match par Department)
    act_dept = acts.to_dict("records") if not dept else [
        r for r in acts.to_dict("records")
        if any(dept.lower() in str(r.get("Activity Category","")).lower() or
               dept.lower() in str(r.get("Activity Sub Category","")).lower()
               for _ in [1])
    ]
    # Fallback : prendre les activités dont la catégorie = département
    dept_acts = acts[acts["Activity Category"]==dept].to_dict("records")
    if not dept_acts:
        # Chercher par proximité
        dept_clean = dept.lower().replace(" & "," ").replace("-","")
        dept_acts = [r for r in acts.to_dict("records")
                     if dept_clean in str(r.get("Activity Category","")).lower()]
    
    return jsonify({
        "department":  dept,
        "sub_depts":   sub_depts,
        "teams":       teams,
        "nb_teams":    len(teams),
        "nb_sub_depts":len(sub_depts),
        "nb_people":   nb_people,
        "activities":  dept_acts,
    })


@app.route("/docs/<path:filename>")
@login_required
def serve_doc(filename):
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), BASE, "Docs")
    return send_from_directory(docs_dir, filename)


# ── CONTENT STUDIO ─────────────────────────────────────────────

CS_FILE = f"{PD}/content_studio.csv"
CS_COLS = ["Content ID","Title","Content Category","Content Sub Category","Body",
           "Author","Author Team","Status","Created At","Updated At",
           "Submitted At","Validated Editor At","Validated Admin At","Published At",
           "Editor Comment","Admin Comment","Channels","Platform","KB ID"]

def cs_read():
    if not os.path.exists(CS_FILE):
        pd.DataFrame(columns=CS_COLS).to_csv(CS_FILE, index=False, encoding="utf-8-sig")
    return pd.read_csv(CS_FILE, encoding="utf-8-sig").fillna("")

def cs_write(df):
    df.to_csv(CS_FILE, index=False, encoding="utf-8-sig")

def cs_next_id(df):
    ids = [str(r) for r in df["Content ID"].tolist() if str(r).startswith("CS_")]
    nums = [int(r.split("_")[1]) for r in ids if len(r.split("_"))>1 and r.split("_")[1].isdigit()]
    return f"CS_{(max(nums)+1 if nums else 1):03d}"

@app.route("/studio")
@login_required
def studio():
    u = cur_user()
    if u.get("access_group","Read Only") == "Read Only":
        return redirect(url_for("catalog"))
    return render_template("studio.html", **ctx())

@app.route("/api/studio", methods=["GET"])
@login_required
def api_studio_list():
    u = cur_user()
    df = cs_read()
    rows = clean(df.to_dict("records"))
    role = u.get("access_group","Read Only")
    team = u.get("team","")
    if role == "Super Admin":
        visible = rows
    elif role == "Editor":
        visible = [r for r in rows if r.get("Author Team")==team
                   or r.get("Status") in ("Pending Editor","Pending Admin","Published")]
    else:
        visible = []
    return jsonify({"items": visible})

@app.route("/api/studio", methods=["POST"])
@login_required
def api_studio_create():
    u = cur_user()
    if u.get("access_group","Read Only") == "Read Only":
        return jsonify({"error":"forbidden"}), 403
    data = request.json
    df = cs_read()
    now = datetime.now().strftime("%Y-%m-%d")
    new_row = {col:"" for col in CS_COLS}
    new_row.update({
        "Content ID": cs_next_id(df), "Title": data.get("title",""),
        "Content Category": data.get("category",""),
        "Content Sub Category": data.get("sub_category",""),
        "Body": data.get("body",""), "Author": u.get("username",""),
        "Author Team": u.get("team",""), "Status": "Draft",
        "Created At": now, "Updated At": now,
        "Channels": data.get("channels",""), "Platform": data.get("channels",""),
    })
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    cs_write(df)
    return jsonify({"id": new_row["Content ID"], "status": "Draft"})

@app.route("/api/studio/<cid>", methods=["PUT"])
@login_required
def api_studio_update(cid):
    u = cur_user()
    df = cs_read()
    idx = df[df["Content ID"]==cid].index
    if idx.empty: return jsonify({"error":"not found"}), 404
    i = idx[0]
    data = request.json
    now = datetime.now().strftime("%Y-%m-%d")
    action = data.get("action","save")
    role = u.get("access_group","Read Only")

    if action == "save":
        for k,c in [("title","Title"),("category","Content Category"),
                    ("sub_category","Content Sub Category"),("body","Body")]:
            if k in data: df.at[i,c] = data[k]
        if "channels" in data: df.at[i,"Channels"]=data["channels"]; df.at[i,"Platform"]=data["channels"]
        df.at[i,"Updated At"] = now

    elif action == "submit":
        df.at[i,"Status"]="Pending Editor"; df.at[i,"Submitted At"]=now; df.at[i,"Updated At"]=now

    elif action == "validate_editor" and role in ("Editor","Super Admin"):
        df.at[i,"Status"]="Pending Admin"; df.at[i,"Validated Editor At"]=now
        df.at[i,"Editor Comment"]=data.get("comment",""); df.at[i,"Updated At"]=now

    elif action == "validate_admin" and role == "Super Admin":
        df.at[i,"Status"]="Published"; df.at[i,"Validated Admin At"]=now
        df.at[i,"Published At"]=now; df.at[i,"Admin Comment"]=data.get("comment","")
        df.at[i,"Updated At"]=now
        try:
            kb = pd.read_csv(f"{CD}/content_list.csv", encoding="utf-8-sig").fillna("")
            kb_ids = [str(r) for r in kb["ID"].tolist() if str(r).startswith("CL_")]
            nums = [int(r.split("_")[1]) for r in kb_ids if r.split("_")[1].isdigit()]
            new_kb_id = f"CL_{(max(nums)+1 if nums else 1):03d}"
            kb_row = {col:"" for col in kb.columns}
            kb_row.update({"ID":new_kb_id,"English Name":str(df.at[i,"Title"]),
                "French Name":str(df.at[i,"Title"]),"Content Category":str(df.at[i,"Content Category"]),
                "Content Sub Category":str(df.at[i,"Content Sub Category"]),
                "Classification":"External","Owner Team":str(df.at[i,"Author Team"]),
                "Contact Team":str(df.at[i,"Author Team"]),"Platform":str(df.at[i,"Channels"])})
            kb = pd.concat([kb, pd.DataFrame([kb_row])], ignore_index=True)
            kb.to_csv(f"{CD}/content_list.csv", index=False, encoding="utf-8-sig")
            df.at[i,"KB ID"] = new_kb_id
        except Exception as e:
            print(f"KB sync error: {e}")

    elif action == "reject" and role in ("Editor","Super Admin"):
        df.at[i,"Status"]="Draft"; df.at[i,"Editor Comment"]=data.get("comment",""); df.at[i,"Updated At"]=now

    cs_write(df)
    return jsonify({"status": str(df.at[i,"Status"])})

@app.route("/api/studio/<cid>", methods=["DELETE"])
@login_required
def api_studio_delete(cid):
    u = cur_user()
    df = cs_read()
    row = df[df["Content ID"]==cid]
    if row.empty: return jsonify({"error":"not found"}), 404
    if row.iloc[0]["Author"] != u.get("username") and u.get("access_group") != "Super Admin":
        return jsonify({"error":"forbidden"}), 403
    df = df[df["Content ID"]!=cid]
    cs_write(df)
    return jsonify({"ok":True})

@app.route("/api/studio/<cid>/export-pdf")
@login_required
def api_studio_export_pdf(cid):
    df = cs_read()
    row = df[df["Content ID"]==cid]
    if row.empty: return "Not found", 404
    r = row.iloc[0].to_dict()
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;color:#1a1a1a;line-height:1.7}}
h1{{color:#006B5E;border-bottom:2px solid #006B5E;padding-bottom:8px}}
.meta{{color:#888;font-size:12px;margin-bottom:24px;padding:8px 12px;background:#f5f5f0;border-radius:6px}}
</style></head><body>
<h1>{r.get('Title','')}</h1>
<div class="meta">Category: {r.get('Content Category','')} | Team: {r.get('Author Team','')} | Published: {r.get('Published At','')} | Channels: {r.get('Channels','')}</div>
{r.get('Body','')}
</body></html>"""
    return Response(html, mimetype="text/html",
        headers={{"Content-Disposition": f"attachment; filename={cid}.html"}})


if __name__ == "__main__":
    app.run(debug=True, port=5001, use_reloader=False)

# Ajout route manquante calendar-meta
