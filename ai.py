"""OpenAI 연동 + 규칙 기반 판정/대체 로직."""
import json
import os

from dotenv import load_dotenv

import db

load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-6-astra")
DISCLAIMER = "※ 본 내용은 생활습관 개선을 위한 참고 정보이며 의료적 진단을 대체하지 않습니다."

_client = None


def ai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=40, max_retries=1)
    return _client


def ask_json(system: str, user: str) -> dict:
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


COACH = ("당신은 사내 보건관리 코치입니다(의사가 아님). 한국어로, 직장인이 바로 실천할 수 있는 구체적 행동을 제시하세요. "
         "진단명을 단정하거나 약물을 권하지 마세요. 반드시 JSON으로만 답하세요.")


def _profile(emp):
    return {"성별": "남" if emp["gender"] == "M" else "여", "나이": emp["age"]}  # 이름·사번은 보내지 않음


# ---------------------------------------------------------------------------
# F2 미션 부여
# ---------------------------------------------------------------------------
FALLBACK_MISSIONS = {
    "bmi": ("하루 7,000보 이상 걷기", "BMI를 낮추려면 매일 꾸준히 걷는 것이 가장 쉬운 시작이에요.", "7,000보"),
    "waist": ("저녁 탄수화물 절반으로 줄이기", "허리둘레(복부비만)는 저녁 탄수화물 섭취와 관련이 커요.", "실천 여부"),
    "sbp": ("국물 남기고 싱겁게 먹기", "나트륨을 줄이면 혈압이 내려가요.", "실천 여부"),
    "dbp": ("하루 10분 스트레칭·심호흡", "긴장 완화는 혈압 관리에 도움이 돼요.", "10분"),
    "glucose": ("저녁 식사 후 간식 끊기", "야식과 간식을 줄이면 공복혈당 관리에 도움이 돼요.", "실천 여부"),
    "tchol": ("튀김·가공육 대신 생선·두부 먹기", "포화지방을 줄이면 콜레스테롤이 내려가요.", "실천 여부"),
    "tg": ("단 음료·술 대신 물 마시기", "당류와 알코올은 중성지방을 올려요.", "실천 여부"),
    "hdl": ("주 3회 30분 유산소 운동", "유산소 운동은 좋은 콜레스테롤(HDL)을 높여요.", "30분"),
    "alt": ("주 1회 이하로 음주 줄이기", "간수치 관리를 위해 음주를 줄여 보세요.", "실천 여부"),
    "ggt": ("금주일 지키기(주 5일 이상)", "γ-GTP는 음주에 민감하게 반응해요.", "실천 여부"),
}


def flagged_items(emp, values: dict):
    """주의·위험 항목을 위험 우선으로 정렬."""
    def deviation(i, v):  # 정상 경계에서 벗어난 정도(비율)
        normal = db.ITEMS[i]["ref"].get(emp["gender"], db.ITEMS[i]["ref"]["M"])[0]
        return v / normal if db.ITEMS[i]["better"] == "low" else normal / max(v, 1)

    out = [(i, db.grade(i, v, emp["gender"]), deviation(i, v)) for i, v in values.items()]
    out = sorted([x for x in out if x[1] != "정상"], key=lambda x: (x[1] != "위험", -x[2]))
    return [(i, g) for i, g, _ in out]


def _fallback_missions(flags):
    missions, used = [], set()
    for item, _ in flags:
        title, reason, target = FALLBACK_MISSIONS[item]
        if title in used:
            continue
        used.add(title)
        missions.append({"title": title, "related_items": [item], "reason": reason,
                         "frequency": "매일", "target": target, "weeks": 8})
        if len(missions) == 3:
            break
    if not missions:
        missions = [{"title": "하루 7,000보 이상 걷기", "related_items": ["bmi"], "reason": "지금의 좋은 수치를 유지해요.",
                     "frequency": "매일", "target": "7,000보", "weeks": 8}]
    return missions


def generate_missions(emp, values: dict, feedback: str = ""):
    """반환: (missions 리스트, source['AI'|'규칙'], error)"""
    flags = flagged_items(emp, values)
    if ai_available():
        try:
            data = {
                **_profile(emp),
                "최신검진": {db.ITEMS[i]["label"] + f"({i})": f"{v}{db.ITEMS[i]['unit']} [{db.grade(i, v, emp['gender'])}]"
                         for i, v in values.items()},
                "지난 효과평가 요약": feedback or "없음",
            }
            prompt = (
                f"다음 직원의 검진 결과에서 주의·위험 항목을 우선으로 8주짜리 건강 미션 3개를 만들어 주세요.\n{json.dumps(data, ensure_ascii=False)}\n"
                '형식: {"missions":[{"title":"","related_items":["항목코드"],"reason":"","frequency":"매일","target":"","weeks":8}]}\n'
                f"related_items는 다음 코드만 사용: {list(db.ITEMS)}")
            res = ask_json(COACH, prompt)
            ms = [m for m in res.get("missions", []) if m.get("title")]
            for m in ms:
                m["related_items"] = [i for i in m.get("related_items", []) if i in db.ITEMS] or [flags[0][0] if flags else "bmi"]
            if ms:
                return ms[:3], "AI", None
        except Exception as e:  # noqa: BLE001
            return _fallback_missions(flags), "규칙", str(e)
    return _fallback_missions(flags), "규칙", None


# ---------------------------------------------------------------------------
# F4 효과 평가
# ---------------------------------------------------------------------------
MATRIX = {
    (True, "개선"): ("🎉", "정말 잘하셨어요! 꾸준한 노력이 수치로 나타났어요.", "유지 및 목표 한 단계 상향"),
    (True, "유지"): ("👍", "꾸준히 실천하신 덕분에 더 나빠지지 않았어요.", "미션 유지 + 강도 조금 상향"),
    (True, "악화"): ("💪", "정말 고생 많으셨어요. 노력에도 수치가 나빠진 건 다른 원인이 있을 수 있으니 병원 진료를 받아 보세요. 지금의 습관은 계속 이어가요.", "진료 권고 + 미션 조정"),
    (False, "개선"): ("😊", "바쁜 중에도 실천한 만큼 좋아졌어요! 조금만 더 하면 더 좋아질 거예요.", "미션 지속"),
    (False, "유지"): ("🙂", "시작한 것만으로도 의미 있어요. 실천하기 쉬운 목표로 다시 해 봐요.", "난이도 하향"),
    (False, "악화"): ("🤝", "아쉽지만 지금부터 다시 시작하면 돼요. 작은 목표부터 함께 해 봐요.", "난이도 하향 + 주의 항목 우선"),
}


def rule_evaluate(emp, missions, prev: dict, nxt: dict):
    results = []
    for m in missions:
        st = db.mission_stats(m["id"])
        items = []
        for i in m["related_items"]:
            if i in prev and i in nxt:
                items.append({"item": i, "label": db.ITEMS[i]["label"], "prev": prev[i], "next": nxt[i],
                              "change": db.change_direction(i, prev[i], nxt[i]),
                              "grade": db.grade(i, nxt[i], emp["gender"])})
        score = sum(1 if x["change"] == "개선" else -1 if x["change"] == "악화" else 0 for x in items)
        change = "개선" if score > 0 else "악화" if score < 0 else "유지"
        high = st["rate"] >= 70
        emoji, msg, action = MATRIX[(high, change)]
        danger = any(x["grade"] == "위험" for x in items)
        see_doctor = danger or (high and change == "악화")
        if danger and not (high and change == "악화"):
            msg += " 다만 위험 단계 수치가 있어 병원 진료를 꼭 받아 보세요."
        results.append({"mission_id": m["id"], "title": m["title"], "rate": st["rate"], "logged": st["total"],
                        "change": change, "items": items, "emoji": emoji, "praise": msg,
                        "action": action, "see_doctor": see_doctor})
    return results


def ai_evaluate(emp, rule_results):
    """반환: (평가 dict, source, error). 규칙의 see_doctor는 AI가 끌 수 없음."""
    improved = [r["title"] for r in rule_results if r["change"] == "개선"]
    avg = round(sum(r["rate"] for r in rule_results) / len(rule_results)) if rule_results else 0
    if improved:
        summary = f"평균 달성률 {avg}%! '{improved[0]}' 등 {len(improved)}개 미션에서 수치가 좋아졌어요. 정말 잘하셨어요! 🎉"
    else:
        summary = f"평균 달성률 {avg}%. 그동안 노력해 주셔서 고마워요. 결과를 바탕으로 실천하기 쉬운 다음 미션을 함께 정해 봐요. 💪"
    if any(r["see_doctor"] for r in rule_results):
        summary += " 일부 수치는 병원 진료를 받아 보시길 권해요."
    fallback = {
        "summary": summary,
        "per_mission": [{"mission_id": r["mission_id"], "verdict": r["change"], "praise": r["praise"],
                         "explanation": ", ".join(f"{x['label']} {x['prev']}→{x['next']}({x['change']})" for x in r["items"]),
                         "action": r["action"], "see_doctor": r["see_doctor"]} for r in rule_results],
    }
    if not ai_available():
        return fallback, "규칙", None
    try:
        data = {**_profile(emp), "미션별 결과": [
            {k: r[k] for k in ("mission_id", "title", "rate", "change", "action", "see_doctor")} |
            {"항목변화": [{k: x[k] for k in ("label", "prev", "next", "change", "grade")} for x in r["items"]]}
            for r in rule_results]}
        prompt = (
            "건강행동 미션 수행 실적(rate=달성률%)과 검진 수치 변화를 보고 효과를 평가해 주세요. 목적은 건강행동 강화입니다.\n"
            "- 격려하는 코치 말투. 작은 개선도 구체적 수치로 칭찬하세요.\n"
            "- 악화되었으면 노력을 먼저 인정하고 다시 해 보자고 격려하세요. '실패' 등 비난하는 표현 금지.\n"
            "- see_doctor가 true면 병원 진료를 권하세요.\n"
            f"{json.dumps(data, ensure_ascii=False)}\n"
            '형식: {"summary":"","per_mission":[{"mission_id":0,"verdict":"개선|유지|악화","praise":"","explanation":"","action":"","see_doctor":false}]}')
        res = ask_json(COACH, prompt)
        by_id = {r["mission_id"]: r for r in rule_results}
        pm = []
        for p in res.get("per_mission", []):
            r = by_id.get(p.get("mission_id"))
            if r:
                p["see_doctor"] = bool(p.get("see_doctor")) or r["see_doctor"]
                p["verdict"] = r["change"]
                pm.append(p)
        if len(pm) != len(rule_results):
            raise ValueError("AI 응답의 미션 수가 맞지 않음")
        return {"summary": res.get("summary", ""), "per_mission": pm}, "AI", None
    except Exception as e:  # noqa: BLE001
        return fallback, "규칙", str(e)
