"""건강검진 연계 건강미션 관리 앱 (Streamlit)."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import ai
import db

st.set_page_config(page_title="나의 건강 사이클", page_icon="💚", layout="wide")
db.init_db()

GRADE_COLOR = {"정상": "#16a34a", "주의": "#ea580c", "위험": "#dc2626"}
GRADE_BG = {"정상": "#dcfce7", "주의": "#ffedd5", "위험": "#fee2e2"}
MENUS = ["🏠 내 건강 현황", "📋 검진 결과", "🎯 미션 받기", "✍️ 수행 기록", "📈 효과 평가"]

st.markdown("""
<style>
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;color:#fff;margin-right:4px}
.tag{display:inline-block;padding:1px 8px;border-radius:6px;font-size:0.75rem;background:#e0f2fe;color:#075985;margin:2px 4px 2px 0}
.praise{font-size:1.15rem;font-weight:600;line-height:1.6;margin:6px 0}
.step{display:inline-block;padding:6px 12px;border-radius:8px;margin:2px;background:#f1f5f9;color:#64748b;font-size:0.9rem}
.step.on{background:#16a34a;color:#fff;font-weight:700}
.disc{color:#94a3b8;font-size:0.78rem;margin-top:8px}
</style>""", unsafe_allow_html=True)


def badge(g):
    return f'<span class="badge" style="background:{GRADE_COLOR[g]}">{g}</span>'


def tags(items):
    return "".join(f'<span class="tag">#{db.ITEMS[i]["label"]}</span>' for i in items if i in db.ITEMS)


def disclaimer():
    st.markdown(f'<div class="disc">{ai.DISCLAIMER}</div>', unsafe_allow_html=True)


def go_to(page):
    st.session_state.menu = page


# ---------------------------------------------------------------------------
# 개인 링크로 직원 식별
# ---------------------------------------------------------------------------
emp = db.get_employee(st.query_params.get("emp", ""))
if not emp:
    st.title("💚 나의 건강 사이클")
    st.warning("개인 링크로 접속해 주세요. 링크가 올바르지 않거나 직원번호가 없습니다.")
    st.caption("데모용: 아래에서 직원을 고르면 해당 직원의 개인 링크로 이동합니다.")
    emps = db.list_employees()
    pick = st.selectbox("직원 선택", emps, format_func=lambda e: f"{e['emp_id']} · {e['name']}")
    if st.button("이 직원의 링크로 접속", type="primary"):
        st.query_params["emp"] = pick["emp_id"]
        st.rerun()
    st.stop()

EMP_ID = emp["emp_id"]
checkups = db.get_checkups(EMP_ID)
years = sorted(checkups)
latest_year = years[-1]
latest = checkups[latest_year]
active = db.get_missions(EMP_ID, "진행중")
evals = db.get_evaluations(EMP_ID)

# 사이클 단계
if not active:
    stage = 1  # 미션 받을 차례
elif any(y > min(m["base_year"] for m in active) for y in years):
    stage = 3  # 다음 검진 결과 도착 → 효과 평가
else:
    stage = 2  # 실천·기록 중
STAGES = ["① 검진", "② 미션", "③ 실천·기록", "④ 효과 평가"]

with st.sidebar:
    st.markdown(f"### 💚 {emp['name']}님의 건강 사이클")
    st.caption(f"{'남' if emp['gender'] == 'M' else '여'} · {emp['age']}세 · 최근 검진 {latest_year}년")
    st.radio("메뉴", MENUS, key="menu", label_visibility="collapsed")
    st.divider()
    st.markdown("**현재 단계**")
    st.markdown(" ".join(f'<span class="step {"on" if i == stage else ""}">{s}</span>' for i, s in enumerate(STAGES)),
                unsafe_allow_html=True)
    st.caption(f"🤖 AI 키 설정됨 · 모델 {ai.MODEL}" if ai.ai_available() else "⚙️ AI 키 없음: 규칙 기반으로 동작")

menu = st.session_state.menu


# ---------------------------------------------------------------------------
# 🏠 내 건강 현황
# ---------------------------------------------------------------------------
if menu == MENUS[0]:
    st.title(f"안녕하세요, {emp['name']}님 👋")
    flags = ai.flagged_items(emp, latest)
    stats = [db.mission_stats(m["id"]) for m in active]
    avg = round(sum(s["rate"] for s in stats) / len(stats)) if stats else 0
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{latest_year}년 주의·위험 항목", f"{len(flags)}개")
    c2.metric("진행 중 미션", f"{len(active)}개")
    c3.metric("평균 달성률", f"{avg}%")

    st.subheader("신경 써야 할 항목")
    if flags:
        cols = st.columns(min(len(flags), 4))
        for idx, (i, g) in enumerate(flags):
            with cols[idx % len(cols)].container(border=True):
                st.markdown(f"**{db.ITEMS[i]['label']}** {badge(g)}", unsafe_allow_html=True)
                st.markdown(f"### {latest[i]:g} <small>{db.ITEMS[i]['unit']}</small>", unsafe_allow_html=True)
                st.caption(f"정상 {db.ITEMS[i]['normal_text']}")
    else:
        st.success("모든 항목이 정상이에요! 지금의 습관을 유지해요. 🎉")

    st.subheader("진행 중 미션")
    if not active:
        st.info("진행 중인 미션이 없어요.")
        st.button("🎯 미션 받으러 가기", on_click=go_to, args=(MENUS[2],), type="primary")
    for m, s in zip(active, stats):
        with st.container(border=True):
            st.markdown(f"**{m['title']}** {tags(m['related_items'])}", unsafe_allow_html=True)
            st.progress(s["rate"] / 100, text=f"달성률 {s['rate']}% · 기록 {s['total']}일 · 연속 {s['streak']}일")
    if active:
        st.button("✍️ 오늘 기록하러 가기", on_click=go_to, args=(MENUS[3],), type="primary")


# ---------------------------------------------------------------------------
# 📋 검진 결과 (F1)
# ---------------------------------------------------------------------------
elif menu == MENUS[1]:
    st.title("📋 검진 결과")
    st.caption("연도별 사내 건강검진 결과입니다. ▲▼는 직전 검진 대비 변화량입니다.")
    rows, grades = [], []
    for i, spec in db.ITEMS.items():
        row, grow = {"항목": spec["label"], "단위": spec["unit"], "정상 기준": spec["normal_text"]}, {}
        for k, y in enumerate(years):
            v = checkups[y].get(i)
            if v is None:
                row[f"{y}년"] = "-"
                continue
            g = db.grade(i, v, emp["gender"])
            arrow = ""
            if k > 0 and i in checkups[years[k - 1]]:
                d = round(v - checkups[years[k - 1]][i], 1)
                arrow = f" ▲{d}" if d > 0 else f" ▼{abs(d)}" if d < 0 else " -"
            row[f"{y}년"] = f"{v:g}{arrow} · {g}"
            grow[f"{y}년"] = g
        rows.append(row)
        grades.append(grow)
    df = pd.DataFrame(rows)

    def color(_):
        out = pd.DataFrame("", index=df.index, columns=df.columns)
        for r, gr in enumerate(grades):
            for col, g in gr.items():
                out.loc[r, col] = f"background-color:{GRADE_BG[g]};color:{GRADE_COLOR[g]};font-weight:600"
        return out

    st.dataframe(df.style.apply(color, axis=None), hide_index=True, use_container_width=True)
    st.markdown(" ".join(badge(g) + f"<small>{t}</small>&nbsp;&nbsp;" for g, t in
                         [("정상", "기준 이내"), ("주의", "관리 필요"), ("위험", "진료 권고")]), unsafe_allow_html=True)

    st.subheader("항목별 추세")
    item = st.selectbox("항목 선택", list(db.ITEMS), format_func=lambda i: db.ITEMS[i]["label"],
                        index=list(db.ITEMS).index(ai.flagged_items(emp, latest)[0][0]) if ai.flagged_items(emp, latest) else 0)
    spec = db.ITEMS[item]
    pts = [(y, checkups[y][item]) for y in years if item in checkups[y]]
    normal = spec["ref"][emp["gender"]][0]
    vals = [v for _, v in pts] + [normal]
    lo, hi = min(vals) * 0.85, max(vals) * 1.1
    fig = go.Figure()
    if spec["better"] == "low":
        fig.add_hrect(y0=18.5 if item == "bmi" else lo, y1=normal, fillcolor="#bbf7d0", opacity=0.45, line_width=0,
                      annotation_text="정상 범위", annotation_position="top left")
    else:
        fig.add_hrect(y0=normal, y1=hi, fillcolor="#bbf7d0", opacity=0.45, line_width=0,
                      annotation_text="정상 범위", annotation_position="top left")
    fig.add_trace(go.Scatter(x=[str(y) for y, _ in pts], y=[v for _, v in pts], mode="lines+markers+text",
                             text=[f"{v:g}" for _, v in pts], textposition="top center",
                             line=dict(color="#0f766e", width=3), marker=dict(size=10)))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=spec["unit"],
                      yaxis_range=[lo, hi], xaxis_type="category", plot_bgcolor="white", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# 🎯 미션 받기 (F2)
# ---------------------------------------------------------------------------
elif menu == MENUS[2]:
    st.title("🎯 건강 미션")
    key = f"proposals_{EMP_ID}"
    feedback = st.session_state.get(f"feedback_{EMP_ID}", "")
    flags = ai.flagged_items(emp, latest)
    st.markdown(f"**{latest_year}년 검진 기준 관리 항목:** " +
                (" ".join(f"{db.ITEMS[i]['label']} {badge(g)}" for i, g in flags) or "없음 (모두 정상)"),
                unsafe_allow_html=True)
    if feedback:
        st.info("지난 효과 평가 결과를 반영해서 다음 미션을 만들어요.")

    if st.button("🤖 AI 미션 받기", type="primary"):
        with st.spinner("검진 결과를 분석해서 미션을 만들고 있어요..."):
            ms, src, err = ai.generate_missions(emp, latest, feedback)
        st.session_state[key] = ms
        st.session_state[f"{key}_src"] = (src, err)

    proposals = st.session_state.get(key, [])
    if proposals:
        src, err = st.session_state.get(f"{key}_src", ("규칙", None))
        st.subheader("제안된 미션")
        if src == "규칙":
            st.caption("⚙️ AI 응답을 받지 못해 규칙 기반 기본 미션을 제안했어요." if err or ai.ai_available()
                       else "⚙️ AI 키가 없어 규칙 기반 기본 미션을 제안했어요.")
            if err:
                with st.expander("오류 상세"):
                    st.code(err)
        cols = st.columns(len(proposals))
        for idx, m in enumerate(list(proposals)):
            with cols[idx].container(border=True):
                st.markdown(f"#### {m['title']}")
                st.markdown(tags(m["related_items"]), unsafe_allow_html=True)
                st.write(m.get("reason", ""))
                st.caption(f"🔁 {m.get('frequency', '매일')} · 🎯 {m.get('target', '')} · 📅 {m.get('weeks', 8)}주")
                a = r = st  # 좁은 카드에서 글자가 잘리지 않도록 버튼을 세로로 배치
                if a.button("✅ 수락", key=f"acc_{idx}", use_container_width=True, type="primary"):
                    if len(db.get_missions(EMP_ID, "진행중")) >= 5:
                        st.warning("진행 중 미션은 최대 5개까지예요.")
                    else:
                        db.add_mission(EMP_ID, latest_year, m)
                        proposals.pop(idx)
                        st.toast(f"'{m['title']}' 미션을 시작해요! 💪")
                        st.rerun()
                if r.button("거절", key=f"rej_{idx}", use_container_width=True):
                    proposals.pop(idx)
                    st.rerun()
        disclaimer()

    st.subheader("진행 중 미션")
    if not active:
        st.caption("아직 진행 중인 미션이 없어요. 위에서 미션을 받아 보세요.")
    for m in active:
        s = db.mission_stats(m["id"])
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{m['title']}** {tags(m['related_items'])}<br><small>{m['base_year']}년 검진 기준 · "
                        f"{m['frequency']} · 목표 {m['target']}</small>", unsafe_allow_html=True)
            c1.progress(s["rate"] / 100, text=f"달성률 {s['rate']}%")
            if c2.button("완료 처리", key=f"done_{m['id']}", use_container_width=True):
                db.set_mission_status(m["id"], "완료")
                st.rerun()
    done = db.get_missions(EMP_ID, "완료")
    if done:
        with st.expander(f"완료한 미션 {len(done)}개"):
            for m in done:
                st.write(f"✔️ {m['title']} ({m['base_year']}년 검진 기준) · 달성률 {db.mission_stats(m['id'])['rate']}%")


# ---------------------------------------------------------------------------
# ✍️ 수행 기록 (F3)
# ---------------------------------------------------------------------------
elif menu == MENUS[3]:
    st.title("✍️ 수행 기록")
    if not active:
        st.info("진행 중인 미션이 없어요. 먼저 미션을 받아 주세요.")
        st.button("🎯 미션 받으러 가기", on_click=go_to, args=(MENUS[2],), type="primary")
        st.stop()

    with st.form("log", clear_on_submit=False, border=True):
        c1, c2 = st.columns([3, 1])
        mission = c1.selectbox("미션", active, format_func=lambda m: m["title"])
        log_date = c2.date_input("날짜", value=date.today(), max_value=date.today(),
                                 min_value=date.today() - timedelta(days=365))
        achieved = st.toggle("오늘 미션 달성! ✅", value=True)
        c3, c4 = st.columns([1, 3])
        value = c3.number_input("수치(선택)", min_value=0.0, max_value=1_000_000.0, value=None, placeholder="예: 7500")
        memo = c4.text_input("메모(선택)", max_chars=200)
        if st.form_submit_button("저장", type="primary", use_container_width=True):
            db.upsert_log(mission["id"], log_date, achieved, value, memo.strip())
            s = db.mission_stats(mission["id"])
            st.toast(f"기록했어요! 달성률 {s['rate']}% · 연속 {s['streak']}일 🔥")
            if achieved and s["streak"] >= 7:
                st.balloons()

    st.subheader("누적 실적")
    stats = {m["id"]: db.mission_stats(m["id"]) for m in active}
    cols = st.columns(min(len(active), 3))
    for idx, m in enumerate(active):
        s = stats[m["id"]]
        with cols[idx % len(cols)].container(border=True):
            st.markdown(f"**{m['title']}**")
            a, b, c = st.columns(3)
            a.metric("달성률", f"{s['rate']}%")
            b.metric("기록일", f"{s['total']}일")
            c.metric("연속", f"{s['streak']}일")
            st.progress(s["rate"] / 100)

    logs = db.get_logs([m["id"] for m in active])
    if logs:
        titles = {m["id"]: m["title"] for m in active}
        ldf = pd.DataFrame(logs)
        ldf["미션"] = ldf["mission_id"].map(titles)
        ldf["날짜"] = pd.to_datetime(ldf["log_date"])
        ldf["주"] = (ldf["날짜"] - pd.to_timedelta(ldf["날짜"].dt.weekday, unit="D")).dt.strftime("%m/%d주")
        weekly = ldf.groupby(["주", "미션"], as_index=False)["achieved"].mean()
        weekly["달성률(%)"] = (weekly["achieved"] * 100).round()
        st.subheader("주별 달성률")
        fig = px.bar(weekly, x="주", y="달성률(%)", color="미션", barmode="group",
                     color_discrete_sequence=["#16a34a", "#0ea5e9", "#f59e0b", "#8b5cf6", "#ef4444"])
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), yaxis_range=[0, 100],
                          plot_bgcolor="white", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("전체 기록")
        show = ldf.sort_values("log_date", ascending=False)[["log_date", "미션", "achieved", "value", "memo"]]
        show["achieved"] = show["achieved"].map({1: "✅ 달성", 0: "⬜ 미달성"})
        st.dataframe(show.rename(columns={"log_date": "날짜", "achieved": "결과", "value": "수치", "memo": "메모"}),
                     hide_index=True, use_container_width=True, height=300)


# ---------------------------------------------------------------------------
# 📈 효과 평가 (F4)
# ---------------------------------------------------------------------------
elif menu == MENUS[4]:
    st.title("📈 효과 평가")
    st.caption("건강행동 미션 실적과 다음 검진 결과를 함께 보고, 노력의 효과를 확인해요.")

    def show_eval(ev):
        rule = {r["mission_id"]: r for r in ev["rule"]}
        st.markdown(f"#### 💬 {ev['ai'].get('summary', '')}")
        st.caption(f"{ev['prev_year']}년 → {ev['next_year']}년 검진 비교 · 평가 방식: {ev['source']} · {ev['created_at']}")
        for p in ev["ai"]["per_mission"]:
            r = rule.get(p["mission_id"])
            if not r:
                continue
            with st.container(border=True):
                st.markdown(f"**{r['title']}** · 달성률 **{r['rate']}%** · 연관 수치 **{r['change']}**")
                st.markdown(f'<div class="praise">{r["emoji"]} {p.get("praise", "")}</div>', unsafe_allow_html=True)
                if p.get("see_doctor"):
                    st.error("🏥 병원 진료(상담)를 받아 보시길 권해요. 수치 변화에 다른 원인이 있을 수 있어요.")
                c1, c2 = st.columns([3, 2])
                if r["items"]:
                    idf = pd.DataFrame([{"항목": x["label"], "검진": f"{ev['prev_year']}년", "값": x["prev"]} for x in r["items"]] +
                                       [{"항목": x["label"], "검진": f"{ev['next_year']}년", "값": x["next"]} for x in r["items"]])
                    fig = px.bar(idf, x="항목", y="값", color="검진", barmode="group", text="값",
                                 color_discrete_sequence=["#94a3b8", "#16a34a"])
                    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
                                      legend=dict(orientation="h", y=-0.3), legend_title_text="")
                    c1.plotly_chart(fig, use_container_width=True, key=f"ev_{ev['id']}_{r['mission_id']}")
                c2.markdown("**수치 변화**")
                for x in r["items"]:
                    c2.markdown(f"- {x['label']}: {x['prev']:g} → {x['next']:g} ({x['change']}) {badge(x['grade'])}",
                                unsafe_allow_html=True)
                c2.markdown(f"**설명** {p.get('explanation', '')}")
                c2.markdown(f"**다음 행동** {p.get('action', '')}")
        st.caption("※ 검진 2회 비교에 따른 참고용 분석이며, 미션과 수치 변화의 인과관계를 단정하지 않습니다.")
        disclaimer()

    if len(years) < 2:
        st.info(f"아직 다음 검진 결과가 없어요({latest_year}년 검진만 있음). 다음 검진 후에 효과를 평가할 수 있어요. "
                "그동안 미션을 꾸준히 기록해 주세요! 💪")
        st.button("📈 효과 평가하기", disabled=True)
    else:
        c1, c2 = st.columns(2)
        base_years = sorted({m["base_year"] for m in db.get_missions(EMP_ID) if m["status"] != "제안"} & set(years[:-1]))
        default = years.index(base_years[-1]) if base_years else len(years) - 2
        prev_y = c1.selectbox("직전 검진(미션 시작 기준)", years[:-1], index=min(default, len(years) - 2))
        next_opts = [y for y in years if y > prev_y]
        next_y = c2.selectbox("다음 검진", next_opts, index=0)
        targets = [m for m in db.get_missions(EMP_ID) if m["base_year"] == prev_y and m["status"] in ("진행중", "완료")]
        if not targets:
            st.info(f"{prev_y}년 검진을 기준으로 수행한 미션이 없어 평가할 수 없어요.")
        if st.button("📈 효과 평가하기", type="primary", disabled=not targets):
            with st.spinner("미션 실적과 검진 변화를 분석하고 있어요..."):
                rule = ai.rule_evaluate(emp, targets, checkups[prev_y], checkups[next_y])
                res, src, err = ai.ai_evaluate(emp, rule)
            db.save_evaluation(EMP_ID, prev_y, next_y, rule, res, src)
            if err:
                st.caption("⚙️ AI 응답을 받지 못해 규칙 기반 메시지로 평가했어요.")
                with st.expander("오류 상세"):
                    st.code(err)
            evals = db.get_evaluations(EMP_ID)

    if evals:
        st.divider()
        options = {e["id"]: f"{e['created_at']} · {e['prev_year']}→{e['next_year']}년" for e in evals}
        sel = st.selectbox("평가 결과 조회", list(options), format_func=options.get)
        ev = next(e for e in evals if e["id"] == sel)
        show_eval(ev)

        def next_cycle(ev=ev):
            st.session_state[f"feedback_{EMP_ID}"] = " / ".join(
                f"{r['title']}: 달성률 {r['rate']}%, 수치 {r['change']}, 권고 {r['action']}" for r in ev["rule"])
            st.session_state.pop(f"proposals_{EMP_ID}", None)
            for r in ev["rule"]:
                db.set_mission_status(r["mission_id"], "완료")
            st.session_state.menu = MENUS[2]

        st.button("🎯 평가를 반영해 다음 미션 받기", type="primary", on_click=next_cycle)
