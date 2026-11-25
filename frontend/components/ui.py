"""재사용 UI 조각: CSS 주입, 단계 표시, 문제/채점 카드, 통계 카드. (HTML은 모두 escape 처리)"""
import html
import re
from pathlib import Path

import streamlit as st

CIRCLED = ["①", "②", "③", "④"]
STEP_LABELS = [
    ("upload", "PDF 업로드"),
    ("settings", "조건 설정"),
    ("generating", "문제 생성"),
    ("quiz", "문제 풀이"),
    ("summary", "결과 · 저장"),
    ("done", "완료"),
]
_CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "style.css"


def esc(text) -> str:
    return html.escape(str(text or ""))


def rich(text: str) -> str:
    """escape 후 **굵게**와 줄바꿈만 HTML로 변환."""
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return out.replace("\n", "<br>")


def inject_css() -> None:
    st.markdown(f"<style>{_CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def page_title(title: str, subtitle: str = "") -> None:
    sub = f'<p class="qn-subtitle">{subtitle}</p>' if subtitle else ""
    html_block(f'<h1 class="qn-title">{esc(title)}</h1>{sub}')


# ---------- 단계 표시 ----------
def step_indicator(current: str) -> None:
    idx = next(i for i, (k, _) in enumerate(STEP_LABELS) if k == current)
    items = []
    for i, (_, label) in enumerate(STEP_LABELS):
        cls = "done" if i < idx else "active" if i == idx else ""
        mark = "✓" if i < idx else str(i + 1)
        items.append(f'<div class="qn-step {cls}"><span class="dot">{mark}</span><span class="lbl">{label}</span></div>')
    html_block(
        f'<div class="qn-steps">{"".join(items)}</div>'
        f'<div class="qn-steps-mobile">STEP {idx + 1}. {STEP_LABELS[idx][1]} <span>{idx + 1} / {len(STEP_LABELS)}</span></div>'
    )


# ---------- 문제 / 채점 카드 ----------
def _choice_index(text: str) -> int | None:
    m = re.match(r"^\s*([1-4])", text or "")
    return int(m.group(1)) - 1 if m else None


def format_user_answer(q: dict, answer: str) -> str:
    if q["type"] != "mcq":
        return answer
    i = _choice_index(answer)
    opts = q.get("options") or []
    return f"{i + 1}번. {opts[i]}" if i is not None and i < len(opts) else answer


def question_card(q: dict, index: int, total: int, result: dict | None, settings: dict) -> str:
    kind = "객관식" if q["type"] == "mcq" else "서술형"
    tags = f'<span class="qn-tag dark">Q{index + 1} / {total}</span><span class="qn-tag {"mcq" if q["type"] == "mcq" else "essay"}">{kind}</span>'
    if q.get("concept"):
        tags += f'<span class="qn-tag">#{esc(q["concept"])}</span>'
    body = f'<div class="qn-tags">{tags}</div><p class="qn-question">{esc(q["question"])}</p>'

    if q["type"] == "mcq":
        picked = _choice_index(result["user_answer"]) if result else None
        correct = None
        if result and settings.get("show_answer"):
            m = re.match(r"^([1-4])번", result.get("correct_answer", ""))
            correct = int(m.group(1)) - 1 if m else None
        rows = []
        for i, opt in enumerate(q.get("options") or []):
            cls = ""
            if correct == i or (picked == i and result and result["is_correct"]):
                cls = "correct"
            elif picked == i:
                cls = "wrong"
            rows.append(f'<li class="{cls}"><span>{CIRCLED[i]}</span><span>{esc(opt)}</span></li>')
        body += f'<ol class="qn-options">{"".join(rows)}</ol>'
    elif not result:
        body += '<p class="qn-hint">✍️ 아래 입력창에 2~5문장으로 답변해주세요. 핵심 키워드와 의미를 기준으로 채점해요.</p>'
    return f'<div class="qn-card">{body}</div>'


def result_card(q: dict, r: dict, settings: dict) -> str:
    ok = r["is_correct"]
    essay = q["type"] == "essay"
    if ok:
        head = "⭕ 정답입니다!"
    elif essay and r.get("verdict") == "partial":
        head = "🔺 부분 정답이에요"
    else:
        head = "❌ 오답입니다"
    score = f'<span class="qn-score">{r["score"]}점</span>' if essay else ""
    parts = [f'<div class="qn-result-head"><b>{head}</b>{score}</div>']

    cmp = [
        f'<div class="qn-box {"ok" if ok else "ng"}"><small>내 답변</small><p>{esc(format_user_answer(q, r["user_answer"]))}</p></div>'
    ]
    if settings.get("show_answer"):
        cmp.append(f'<div class="qn-box ok"><small>{"모범 답안" if essay else "정답"}</small><p>{esc(r["correct_answer"])}</p></div>')
    parts.append(f'<div class="qn-compare">{"".join(cmp)}</div>')

    if essay:
        if r.get("feedback"):
            parts.append(f'<p class="qn-feedback">🧑‍🏫 {esc(r["feedback"])}</p>')
        chips = "".join(f'<span class="qn-chip ok">✓ {esc(p)}</span>' for p in r.get("matched_points") or [])
        chips += "".join(f'<span class="qn-chip ng">✗ {esc(p)}</span>' for p in r.get("missing_points") or [])
        if chips:
            parts.append(f'<div class="qn-chips">{chips}</div>')

    if settings.get("show_explanation") and (r.get("explanation") or r.get("supplement")):
        exp = f'<small>💡 해설</small><div>{rich(r.get("explanation", ""))}</div>' if r.get("explanation") else ""
        if r.get("supplement"):
            exp += f'<div class="qn-sup"><small>📚 보충 설명</small><div>{rich(r["supplement"])}</div></div>'
        refs = "".join(f"<li>🌐 {esc(x)}</li>" for x in r.get("references") or [])
        if refs:
            exp += f'<ul class="qn-refs">{refs}</ul>'
        parts.append(f'<div class="qn-explain">{exp}</div>')

    if settings.get("show_source") and (r.get("source_page") or r.get("source_quote")):
        page = f" · PDF {r['source_page']}페이지" if r.get("source_page") else ""
        quote = f"<blockquote>{esc(r['source_quote'])}</blockquote>" if r.get("source_quote") else ""
        parts.append(f'<div class="qn-source"><small>📖 원문 출처{page}</small>{quote}</div>')

    return f'<div class="qn-card qn-result {"ok" if ok else "ng"}">{"".join(parts)}</div>'


def progress_strip(questions: list[dict], results: dict, index: int) -> str:
    segs = []
    for i, q in enumerate(questions):
        r = results.get(q["id"])
        cls = ("ok" if r["is_correct"] else "ng") if r else ("cur" if i == index else "")
        segs.append(f'<span class="{cls}"></span>')
    answered = len(results)
    correct = sum(1 for r in results.values() if r["is_correct"])
    return (
        f'<div class="qn-progress"><div class="qn-progress-top"><b>문제 {index + 1} <span>/ {len(questions)}</span></b>'
        f'<div><span class="qn-pill ok">정답 {correct}</span><span class="qn-pill ng">오답 {answered - correct}</span></div></div>'
        f'<div class="qn-segs">{"".join(segs)}</div></div>'
    )


# ---------- 통계 ----------
def stat_cards(total: int, correct: int, wrong: int, accuracy: float) -> None:
    color = "#10b981" if accuracy >= 80 else "#f59e0b" if accuracy >= 50 else "#f43f5e"
    html_block(
        f"""<div class="qn-stats">
  <div class="qn-stat ring" style="--p:{accuracy};--c:{color}"><div><b style="color:{color}">{accuracy:g}%</b><small>최종 정답률</small></div></div>
  <div class="qn-stat"><b>{total}</b><small>전체 문제</small></div>
  <div class="qn-stat ok"><b>{correct}</b><small>정답</small></div>
  <div class="qn-stat ng"><b>{wrong}</b><small>오답</small></div>
</div>"""
    )


def question_review(questions: list[dict], display: dict | None = None) -> None:
    """문제별 답변 결과 (펼쳐서 상세 확인). questions 항목은 result 필드를 포함."""
    display = display or {"show_answer": True, "show_explanation": True, "show_source": True}
    for i, q in enumerate(questions, start=1):
        r = q.get("result")
        mark = "⭕" if r and r["is_correct"] else "❌" if r else "➖"
        extra = f" ({r['score']}점)" if r and q["type"] == "essay" else "" if r else " (미응답)"
        with st.expander(f"{mark} Q{i}. {q['question'][:70]}{'…' if len(q['question']) > 70 else ''}{extra}"):
            parts = [f'<p class="qn-question">{esc(q["question"])}</p>']
            if q["type"] == "mcq" and q.get("options"):
                rows = []
                for j, o in enumerate(q["options"]):
                    cls = "correct" if display["show_answer"] and q.get("answer_index") == j else ""
                    rows.append(f'<li class="{cls}"><span>{CIRCLED[j]}</span><span>{esc(o)}</span></li>')
                parts.append(f'<ol class="qn-options">{"".join(rows)}</ol>')
            if r:
                parts.append(
                    f'<p><b class="muted">내 답변</b> <span class="{"txt-ok" if r["is_correct"] else "txt-ng"}">{esc(format_user_answer(q, r["user_answer"]))}</span></p>'
                )
                if display["show_answer"]:
                    label = "모범 답안" if q["type"] == "essay" else "정답"
                    parts.append(f'<p><b class="muted">{label}</b> <span class="txt-ok">{esc(r["correct_answer"])}</span></p>')
                if r.get("feedback") and q["type"] == "essay":
                    parts.append(f'<p class="qn-feedback">🧑‍🏫 {esc(r["feedback"])}</p>')
            explanation = q.get("explanation") or (r or {}).get("explanation")
            if display["show_explanation"] and explanation:
                parts.append(f'<div class="qn-explain"><small>💡 해설</small><div>{rich(explanation)}</div></div>')
            if display["show_source"] and (q.get("source_page") or q.get("source_quote")):
                page = f" · {q['source_page']}페이지" if q.get("source_page") else ""
                quote = f"<blockquote>{esc(q['source_quote'])}</blockquote>" if q.get("source_quote") else ""
                parts.append(f'<div class="qn-source"><small>📖 원문 출처{page}</small>{quote}</div>')
            html_block("".join(parts))


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"
