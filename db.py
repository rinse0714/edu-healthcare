"""SQLite 저장소: 스키마, 샘플 데이터, 판정 기준, CRUD."""
import json
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "health.db"

# ---------------------------------------------------------------------------
# 검진 항목 정의
# better: "low"(낮을수록 좋음) / "high"(높을수록 좋음)
# ref: 성별별 (정상 경계, 주의 경계). low → 값 <= 정상경계면 정상, <= 주의경계면 주의, 초과면 위험
#                                  high → 값 >= 정상경계면 정상, >= 주의경계면 주의, 미만이면 위험
# ---------------------------------------------------------------------------
ITEMS = {
    "bmi":     {"label": "BMI",         "unit": "kg/m²", "better": "low",  "ref": {"M": (22.9, 29.9), "F": (22.9, 29.9)}, "normal_text": "18.5~22.9"},
    "waist":   {"label": "허리둘레",     "unit": "cm",    "better": "low",  "ref": {"M": (89.9, 99.9), "F": (84.9, 94.9)}, "normal_text": "남<90 / 여<85"},
    "sbp":     {"label": "수축기 혈압",  "unit": "mmHg",  "better": "low",  "ref": {"M": (119, 139), "F": (119, 139)}, "normal_text": "<120"},
    "dbp":     {"label": "이완기 혈압",  "unit": "mmHg",  "better": "low",  "ref": {"M": (79, 89), "F": (79, 89)}, "normal_text": "<80"},
    "glucose": {"label": "공복혈당",     "unit": "mg/dL", "better": "low",  "ref": {"M": (99, 125), "F": (99, 125)}, "normal_text": "<100"},
    "tchol":   {"label": "총콜레스테롤", "unit": "mg/dL", "better": "low",  "ref": {"M": (199, 239), "F": (199, 239)}, "normal_text": "<200"},
    "tg":      {"label": "중성지방",     "unit": "mg/dL", "better": "low",  "ref": {"M": (149, 199), "F": (149, 199)}, "normal_text": "<150"},
    "hdl":     {"label": "HDL 콜레스테롤", "unit": "mg/dL", "better": "high", "ref": {"M": (60, 40), "F": (60, 40)}, "normal_text": "≥60"},
    "alt":     {"label": "ALT(간수치)",  "unit": "U/L",   "better": "low",  "ref": {"M": (35, 70), "F": (35, 70)}, "normal_text": "≤35"},
    "ggt":     {"label": "γ-GTP",        "unit": "U/L",   "better": "low",  "ref": {"M": (63, 126), "F": (35, 70)}, "normal_text": "남≤63 / 여≤35"},
}


def grade(item: str, value: float, gender: str) -> str:
    """정상 / 주의 / 위험 판정."""
    spec = ITEMS[item]
    normal, caution = spec["ref"].get(gender, spec["ref"]["M"])
    if item == "bmi" and value < 18.5:
        return "주의"
    if spec["better"] == "low":
        return "정상" if value <= normal else ("주의" if value <= caution else "위험")
    return "정상" if value >= normal else ("주의" if value >= caution else "위험")


def change_direction(item: str, prev: float, curr: float) -> str:
    """좋은 방향이면 작은 변화도 '개선', ±1% 이내 '유지', 나쁜 방향 1% 초과 '악화'."""
    if prev == 0:
        return "유지"
    pct = (curr - prev) / prev * 100
    good = pct < 0 if ITEMS[item]["better"] == "low" else pct > 0
    if good and curr != prev:
        return "개선"
    if abs(pct) <= 1:
        return "유지"
    return "악화"


# ---------------------------------------------------------------------------
# 연결 및 스키마
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    emp_id TEXT PRIMARY KEY, name TEXT, gender TEXT, age INTEGER);
CREATE TABLE IF NOT EXISTS checkups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, year INTEGER, item TEXT, value REAL,
    UNIQUE(emp_id, year, item));
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, base_year INTEGER, title TEXT,
    related_items TEXT, reason TEXT, frequency TEXT, target TEXT, weeks INTEGER,
    status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS mission_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id INTEGER, log_date TEXT,
    achieved INTEGER, value REAL, memo TEXT,
    UNIQUE(mission_id, log_date));
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, prev_year INTEGER, next_year INTEGER,
    rule_json TEXT, ai_json TEXT, source TEXT, created_at TEXT);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            seed_data(conn)


# ---------------------------------------------------------------------------
# 샘플 데이터 (PRD 3.2~3.3)
# ---------------------------------------------------------------------------
_ORDER = ["bmi", "waist", "sbp", "dbp", "glucose", "tchol", "tg", "hdl", "alt", "ggt"]
SAMPLE = {
    "E001": ("김건강", "M", 45, {
        2024: [26.1, 93, 138, 88, 98, 215, 210, 42, 30, 55],
        2025: [26.8, 95, 142, 90, 102, 222, 235, 40, 33, 60],
        2026: [25.6, 91, 131, 84, 97, 208, 172, 45, 29, 50],
    }),
    "E002": ("이튼튼", "F", 38, {
        2024: [24.5, 82, 118, 76, 104, 190, 130, 55, 20, 20],
        2025: [25.3, 85, 120, 78, 109, 196, 142, 53, 22, 22],
        2026: [25.4, 86, 121, 79, 112, 199, 148, 52, 23, 23],
    }),
    "E003": ("박활력", "M", 52, {
        2025: [24.0, 88, 126, 82, 95, 205, 160, 48, 58, 110],
    }),
}
SAMPLE_MISSIONS = {
    "E001": (0.88, [
        ("하루 7,000보 이상 걷기", ["bmi", "tg", "glucose"], "중성지방·BMI가 주의 단계예요. 걷기는 지방 연소와 혈당 조절에 좋아요.", "매일", "7,000보"),
        ("국물 남기고 싱겁게 먹기", ["sbp", "dbp"], "혈압이 위험 단계예요. 나트륨을 줄이면 혈압이 내려가요.", "매일", "실천 여부"),
        ("주 3회 30분 유산소 운동", ["hdl", "waist"], "HDL이 낮고 허리둘레가 기준을 넘었어요.", "매일", "30분"),
    ]),
    "E002": (0.40, [
        ("저녁 식사 후 간식 끊기", ["glucose", "bmi"], "공복혈당이 주의 단계예요. 야식을 줄이면 혈당 관리에 도움이 돼요.", "매일", "실천 여부"),
        ("점심 후 15분 걷기", ["bmi", "waist", "glucose"], "BMI·허리둘레가 늘고 있어요. 식후 걷기는 혈당 상승도 막아 줘요.", "매일", "15분"),
    ]),
}


def seed_data(conn):
    rng = random.Random(42)
    for emp, (name, gender, age, years) in SAMPLE.items():
        conn.execute("INSERT INTO employees VALUES (?,?,?,?)", (emp, name, gender, age))
        for year, values in years.items():
            for item, v in zip(_ORDER, values):
                conn.execute("INSERT INTO checkups(emp_id, year, item, value) VALUES (?,?,?,?)", (emp, year, item, v))
    start = date(2026, 8, 3)  # 2025 검진 후 ~ 2026 검진 전 8주 기록
    for emp, (p, missions) in SAMPLE_MISSIONS.items():
        for title, items, reason, freq, target in missions:
            cur = conn.execute(
                "INSERT INTO missions(emp_id, base_year, title, related_items, reason, frequency, target, weeks, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (emp, 2025, title, json.dumps(items, ensure_ascii=False), reason, freq, target, 8, "진행중", "2026-08-03 09:00"))
            for d in range(56):
                conn.execute("INSERT INTO mission_logs(mission_id, log_date, achieved, value, memo) VALUES (?,?,?,?,?)",
                             (cur.lastrowid, (start + timedelta(days=d)).isoformat(), int(rng.random() < p), None, ""))


# ---------------------------------------------------------------------------
# 조회 / 저장
# ---------------------------------------------------------------------------
def get_employee(emp_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM employees WHERE emp_id=?", (emp_id,)).fetchone()
    return dict(row) if row else None


def list_employees():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM employees ORDER BY emp_id")]


def get_checkups(emp_id) -> dict:
    """{year: {item: value}}"""
    out = {}
    with get_conn() as conn:
        for r in conn.execute("SELECT year, item, value FROM checkups WHERE emp_id=? ORDER BY year", (emp_id,)):
            out.setdefault(r["year"], {})[r["item"]] = r["value"]
    return out


def get_missions(emp_id, status=None):
    sql, args = "SELECT * FROM missions WHERE emp_id=?", [emp_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]
    for r in rows:
        r["related_items"] = json.loads(r["related_items"] or "[]")
    return rows


def add_mission(emp_id, base_year, m: dict, status="진행중"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO missions(emp_id, base_year, title, related_items, reason, frequency, target, weeks, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (emp_id, base_year, m["title"], json.dumps(m.get("related_items", []), ensure_ascii=False),
             m.get("reason", ""), m.get("frequency", "매일"), str(m.get("target", "")), int(m.get("weeks", 8) or 8),
             status, datetime.now().strftime("%Y-%m-%d %H:%M")))


def set_mission_status(mission_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE missions SET status=? WHERE id=?", (status, mission_id))


def upsert_log(mission_id, log_date, achieved, value=None, memo=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO mission_logs(mission_id, log_date, achieved, value, memo) VALUES (?,?,?,?,?)"
            " ON CONFLICT(mission_id, log_date) DO UPDATE SET achieved=excluded.achieved, value=excluded.value, memo=excluded.memo",
            (mission_id, str(log_date), int(achieved), value, memo))


def get_logs(mission_ids):
    if not mission_ids:
        return []
    q = ",".join("?" * len(mission_ids))
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM mission_logs WHERE mission_id IN ({q}) ORDER BY log_date", list(mission_ids))]


def mission_stats(mission_id) -> dict:
    logs = get_logs([mission_id])
    total = len(logs)
    done = sum(l["achieved"] for l in logs)
    streak = 0
    prev_day = None
    for l in reversed(logs):  # 마지막 기록일부터 거꾸로 연속 달성일 계산
        d = date.fromisoformat(l["log_date"])
        if not l["achieved"] or (prev_day and (prev_day - d).days != 1):
            break
        streak += 1
        prev_day = d
    return {"total": total, "done": done, "rate": round(done / total * 100) if total else 0, "streak": streak}


def save_evaluation(emp_id, prev_year, next_year, rule, ai, source):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO evaluations(emp_id, prev_year, next_year, rule_json, ai_json, source, created_at) VALUES (?,?,?,?,?,?,?)",
            (emp_id, prev_year, next_year, json.dumps(rule, ensure_ascii=False), json.dumps(ai, ensure_ascii=False),
             source, datetime.now().strftime("%Y-%m-%d %H:%M")))


def get_evaluations(emp_id):
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM evaluations WHERE emp_id=? ORDER BY id DESC", (emp_id,))]
    for r in rows:
        r["rule"] = json.loads(r["rule_json"])
        r["ai"] = json.loads(r["ai_json"])
    return rows
