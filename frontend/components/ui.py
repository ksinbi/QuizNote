"""재사용 UI 조각: CSS 주입, 로고 · 아이콘, 페이지 헤더, 문제/채점 카드, 통계 카드. (HTML은 모두 escape 처리)"""
import html
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

CIRCLED = ["①", "②", "③", "④"]
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_CSS_PATH = _ASSETS / "style.css"
BOT_AVATAR = str(_ASSETS / "bot.svg")


def esc(text) -> str:
    return html.escape(str(text or ""))


def rich(text: str) -> str:
    """escape 후 **굵게**와 줄바꿈만 HTML로 변환."""
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return out.replace("\n", "<br>")


def inject_css() -> None:
    st.markdown(f"<style>{_CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def html_block(markup: str, width: str = "stretch") -> None:
    st.markdown(markup, unsafe_allow_html=True, width=width)


# ---------- 아이콘 ----------
# 버튼 · 입력창 등 Streamlit 기본 위젯과 같은 Material Symbols(Rounded) 글꼴을 써서 화면 전체 아이콘 모양을 통일
_ICONS = {
    "file-text": "description",
    "file-up": "upload_file",
    "sliders": "tune",
    "clock": "schedule",
    "check": "check",
    "check-circle": "check_circle",
    "x-circle": "cancel",
    "alert": "error",
    "sparkles": "auto_awesome",
    "loader": "progress_activity",
    "lightbulb": "lightbulb",
    "drive": "hard_drive",
    "book": "menu_book",
    "list-check": "fact_check",
    "trophy": "emoji_events",
    "folder": "folder_open",
    "bot": "smart_toy",
    "pages": "auto_stories",
}


def icon(name: str, size: int = 18, cls: str = "") -> str:
    return f'<span class="qn-ic {cls}" style="font-size:{size}px" translate="no" aria-hidden="true">{_ICONS[name]}</span>'


def brand(light: bool = False) -> str:
    return (
        f'<div class="qn-brand{" light" if light else ""}"><span class="qn-logo">{icon("file-text", 20)}</span>'
        "<span>Quiz<b>Note</b></span></div>"
    )


def footer() -> None:
    html_block(
        f'<div class="qn-footer"><span>© {datetime.now().year} Quiz Note. All rights reserved.</span>'
        "<span><span>이용약관</span><span>개인정보처리방침</span></span></div>"
    )


# ---------- 페이지 헤더 ----------
def page_header(step: int | None, eyebrow: str, title: str, right: str = "") -> None:
    badge = f'<span class="qn-step-badge">STEP {step:02d}</span>' if step else ""
    eb = f'<div class="qn-eyebrow">{badge}<span>{esc(eyebrow)}</span></div>' if (badge or eyebrow) else ""
    side = f'<div class="qn-head-side">{right}</div>' if right else ""
    html_block(f'<div class="qn-head"><div>{eb}<h1 class="qn-h1">{title}</h1></div>{side}</div>')


def card_title(icon_name: str, title: str, right: str = "") -> None:
    html_block(f'<div class="qn-card-title"><div>{icon(icon_name, 20)}<span>{esc(title)}</span></div><div>{right}</div></div>')


def field_label(label: str, right: str = "") -> None:
    html_block(f'<div class="qn-field"><span>{esc(label)}</span><small>{esc(right)}</small></div>')


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


def question_head(q: dict, index: int, current: bool) -> str:
    badge = f'<span class="qn-qno{" cur" if current else ""}">Q{index + 1}{" · 진행 중" if current else ""}</span>'
    concept = f'<span class="qn-concept">{esc(q["concept"])}</span>' if q.get("concept") else ""
    kind = ""
    if current:
        n = len(q.get("options") or [])
        kind = f'<span class="qn-kind">{"객관식 " + str(n) + "지선다" if q["type"] == "mcq" else "서술형"}</span>'
    return f'<div class="qn-qhead"><div>{badge}{concept}</div>{kind}</div><p class="qn-question">{esc(q["question"])}</p>'


def question_card(q: dict, index: int) -> str:
    """이미 답한 문제 (질문만)"""
    return f'<div class="qn-card">{question_head(q, index, False)}</div>'


def my_bubble(text: str, label: str = "내 답변") -> str:
    return f'<div class="qn-me"><div><small>{esc(label)}</small><p>{esc(text)}</p></div></div>'


def result_card(q: dict, r: dict, settings: dict) -> str:
    ok = r["is_correct"]
    essay = q["type"] == "essay"
    if ok:
        badge = f'<span class="qn-verdict ok">{icon("check-circle", 18)}정답입니다!</span>'
    elif essay and r.get("verdict") == "partial":
        badge = f'<span class="qn-verdict mid">{icon("alert", 18)}부분 정답이에요</span>'
    else:
        badge = f'<span class="qn-verdict ng">{icon("x-circle", 18)}오답입니다</span>'
    side = []
    if essay:
        side.append(f'<span class="qn-src">{r["score"]}점</span>')
    if settings.get("show_source") and r.get("source_page"):
        side.append(f'<span class="qn-src">[원문 출처: p.{esc(r["source_page"])}]</span>')
    parts = [f'<div class="qn-rhead">{badge}<div>{"".join(side)}</div></div>']

    if settings.get("show_answer") and (essay or not ok):
        label = "모범 답안" if essay else "정답"
        parts.append(f'<div class="qn-answer">{icon("lightbulb", 18)}<div><b>{label}:</b> {esc(r["correct_answer"])}</div></div>')

    if essay:
        if r.get("feedback"):
            parts.append(f'<p class="qn-body">{esc(r["feedback"])}</p>')
        chips = "".join(f'<span class="qn-chip ok">✓ {esc(p)}</span>' for p in r.get("matched_points") or [])
        chips += "".join(f'<span class="qn-chip ng">✗ {esc(p)}</span>' for p in r.get("missing_points") or [])
        if chips:
            parts.append(f'<div class="qn-chips">{chips}</div>')

    if settings.get("show_explanation"):
        if r.get("explanation"):
            parts.append(f'<p class="qn-body">{rich(r["explanation"])}</p>')
        if r.get("supplement"):
            parts.append(f'<div class="qn-sup"><small>보충 설명</small><p>{rich(r["supplement"])}</p></div>')
        refs = "".join(f"<li>{esc(x)}</li>" for x in r.get("references") or [])
        if refs:
            parts.append(f'<ul class="qn-refs">{refs}</ul>')

    if settings.get("show_source") and r.get("source_quote"):
        parts.append(f'<blockquote class="qn-quote">{esc(r["source_quote"])}</blockquote>')

    return f'<div class="qn-card">{"".join(parts)}</div>'


def quiz_bar(filename: str, index: int, total: int, answered: int, correct: int) -> str:
    pct = round((index + 1) / total * 100) if total else 0
    return (
        f'<div class="qn-quizbar"><div class="qn-doc"><span class="qn-doc-ic">{icon("file-text", 18)}</span>'
        f'<div><small>학습 중인 문서</small><b>{esc(filename)}</b></div></div>'
        f'<div class="qn-qprog"><div><small>진행률</small><span>문제 <b>{index + 1} / {total}</b></span></div>'
        f'<div class="qn-bar"><i style="width:{pct}%"></i></div></div>'
        f'<span class="qn-score-pill">{icon("check-circle", 18)}현재 <b>{correct}/{answered}</b> 정답</span></div>'
    )


# ---------- 통계 ----------
def stat_cards(total: int, correct: int, wrong: int, accuracy: float) -> None:
    color = "#10b981" if accuracy >= 80 else "#f59e0b" if accuracy >= 50 else "#ef4444"
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
        mark = ":material/check_circle:" if r and r["is_correct"] else ":material/cancel:" if r else ":material/remove:"
        extra = f" ({r['score']}점)" if r and q["type"] == "essay" else "" if r else " (미응답)"
        title = f"Q{i}. {q['question'][:70]}{'…' if len(q['question']) > 70 else ''}{extra}"
        with st.expander(title, icon=mark):
            parts = [f'<p class="qn-question">{esc(q["question"])}</p>']
            if q["type"] == "mcq" and q.get("options"):
                rows = []
                for j, o in enumerate(q["options"]):
                    cls = "correct" if display["show_answer"] and q.get("answer_index") == j else ""
                    rows.append(f'<li class="{cls}"><span>{j + 1}</span><span>{esc(o)}</span></li>')
                parts.append(f'<ol class="qn-options">{"".join(rows)}</ol>')
            if r:
                parts.append(
                    f'<p class="qn-line"><b>내 답변</b> <span class="{"txt-ok" if r["is_correct"] else "txt-ng"}">{esc(format_user_answer(q, r["user_answer"]))}</span></p>'
                )
                if display["show_answer"]:
                    label = "모범 답안" if q["type"] == "essay" else "정답"
                    parts.append(f'<p class="qn-line"><b>{label}</b> <span class="txt-ok">{esc(r["correct_answer"])}</span></p>')
                if r.get("feedback") and q["type"] == "essay":
                    parts.append(f'<p class="qn-body">{esc(r["feedback"])}</p>')
            explanation = q.get("explanation") or (r or {}).get("explanation")
            if display["show_explanation"] and explanation:
                parts.append(f'<p class="qn-body">{rich(explanation)}</p>')
            if display["show_source"] and (q.get("source_page") or q.get("source_quote")):
                page = f'<span class="qn-src">[원문 출처: p.{esc(q["source_page"])}]</span>' if q.get("source_page") else ""
                quote = f'<blockquote class="qn-quote">{esc(q["source_quote"])}</blockquote>' if q.get("source_quote") else ""
                parts.append(f"{page}{quote}")
            html_block("".join(parts))


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"
