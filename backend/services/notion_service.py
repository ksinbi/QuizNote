"""Notion API 연동: 학습 결과를 사용자의 Notion 페이지 하위에 새 페이지로 생성합니다.

토큰은 OAuth로 발급받아 DB에 암호화 저장되며, 이 모듈은 복호화된 토큰을 요청 단위로만 사용합니다.
내보낼 항목(items)은 사용자가 선택합니다:
  filename · questions · answers · explanations · user_answers · results · sources · stats · tutor
"""
from datetime import datetime

from notion_client import Client
from notion_client.errors import APIResponseError

_MAX_TEXT = 1900  # Notion rich_text 1개당 2000자 제한
_MAX_CHILDREN = 100  # 요청 1회당 블록 100개 제한
_MAX_REPLY_BLOCKS = 40  # 튜터 답변 1개를 나눌 최대 문단 수


class NotionExportError(Exception):
    pass


# ---------- 블록 빌더 ----------
def _rt(text: str, bold: bool = False, color: str = "default") -> list[dict]:
    text = text or " "
    return [
        {"type": "text", "text": {"content": text[i : i + _MAX_TEXT]}, "annotations": {"bold": bold, "color": color}}
        for i in range(0, len(text), _MAX_TEXT)
    ]


def _block(kind: str, text: str, color: str = "default", bold: bool = False, **extra) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": _rt(text, bold, color), **extra}}


def _heading(level: int, text: str) -> dict:
    return _block(f"heading_{level}", text)


def _para(text: str, color: str = "default", bold: bool = False) -> dict:
    return _block("paragraph", text, color, bold)


def _bullet(text: str, color: str = "default") -> dict:
    return _block("bulleted_list_item", text, color)


def _callout(text: str, emoji: str, color: str = "gray_background") -> dict:
    return _block("callout", text, icon={"type": "emoji", "emoji": emoji}, color=color)


def _quote(text: str) -> dict:
    return _block("quote", text)


def _toggle(title: str, children: list[dict], color: str = "default") -> dict:
    return _block("toggle", title, color, True, children=children[:_MAX_CHILDREN])


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _correct_answer_text(q: dict) -> str:
    if q["type"] == "mcq":
        return f"{q['answer_index'] + 1}번. {q['options'][q['answer_index']]}"
    return q.get("model_answer", "")


def _question_children(q: dict, r: dict | None, items: set[str]) -> list[dict]:
    blocks: list[dict] = []
    if q["type"] == "mcq":
        blocks += [_bullet(f"{i + 1}. {opt}") for i, opt in enumerate(q["options"])]
    if "user_answers" in items:
        blocks.append(_para(f"✍️ 내 답변: {r['user_answer'] if r else '(미응답)'}"))
    if "results" in items and r:
        label = f"⭕ 정답 ({r['score']}점)" if r["is_correct"] else f"❌ 오답 ({r['score']}점)"
        blocks.append(_para(label, "green" if r["is_correct"] else "red", bold=True))
        if r.get("feedback") and q["type"] == "essay":
            blocks.append(_callout(r["feedback"], "🧑‍🏫"))
    if "answers" in items:
        blocks.append(_para(f"✅ 정답: {_correct_answer_text(q)}"))
    if "explanations" in items:
        explanation = q.get("explanation") or ""
        if explanation:
            blocks.append(_callout(explanation, "💡", "yellow_background"))
        if r and r.get("supplement"):
            blocks.append(_callout(r["supplement"], "📚", "blue_background"))
    if "sources" in items and (q.get("source_page") or q.get("source_quote")):
        blocks.append(_para(f"📖 원문 출처: p.{q.get('source_page') or '?'}", "gray"))
        if q.get("source_quote"):
            blocks.append(_quote(q["source_quote"]))
    return blocks or [_para(" ")]


def build_export_blocks(data: dict, items: set[str]) -> list[dict]:
    """data: {filename, created_at, settings, questions(정답 포함), results{id: 결과}, report}"""
    rep = data["report"]
    blocks: list[dict] = []

    header_lines = []
    if "filename" in items:
        header_lines.append(f"📄 PDF 파일: {data['filename']}")
    header_lines.append(f"🕒 학습 일시: {data['created_at']:%Y-%m-%d %H:%M}")
    s = data.get("settings") or {}
    if s:
        header_lines.append(
            f"⚙️ 설정: 총 {s.get('num_questions')}문항 (서술형 {s.get('num_essay')}) · 난이도 {s.get('difficulty')}"
        )
    blocks.append(_callout("\n".join(header_lines), "🎓"))

    if "stats" in items:
        blocks += [
            _heading(2, "📊 최종 학습 통계"),
            _bullet(f"전체 문제 수: {rep['total']}"),
            _bullet(f"정답 수: {rep['correct']}", "green"),
            _bullet(f"오답 수: {rep['wrong']}", "red"),
            _bullet(f"최종 정답률: {rep['accuracy']}%"),
        ]
        if rep.get("weak_concepts"):
            blocks.append(_para("🎯 복습이 필요한 개념: " + ", ".join(rep["weak_concepts"])))

    if "questions" in items:
        blocks += [_divider(), _heading(2, "📝 문제별 결과")]
        for q in data["questions"]:
            r = data["results"].get(q["id"])
            mark = ""
            if "results" in items and r:
                mark = "⭕ " if r["is_correct"] else "❌ "
            kind = "객관식" if q["type"] == "mcq" else "서술형"
            color = "default"
            if "results" in items and r:
                color = "green_background" if r["is_correct"] else "red_background"
            blocks.append(_toggle(f"{mark}Q{q['id']}. [{kind}] {q['question']}", _question_children(q, r, items), color))
    elif "results" in items:
        blocks += [_divider(), _heading(2, "📝 정답 및 오답 결과")]
        for item in rep["items"]:
            blocks.append(_bullet(f"Q{item['question_id']}: {'정답' if item['is_correct'] else '오답'} ({item['score']}점)"))

    if "tutor" in items and data.get("tutor_log"):
        blocks += _tutor_blocks(data["tutor_log"])
    return blocks


def _tutor_blocks(log: list[dict]) -> list[dict]:
    """AI 튜터 질문 기록: 질문마다 토글(제목=질문, 내용=답변)."""
    blocks = [_divider(), _heading(2, "💬 AI 튜터 질문 기록")]
    for e in log:
        where = f"Q{e['qid']}" if e.get("qid") is not None else "복습"
        reply = (e.get("reply") or "").replace("**", "")
        paragraphs = [p.strip() for p in reply.split("\n\n") if p.strip()] or [" "]
        if len(paragraphs) > _MAX_REPLY_BLOCKS:
            paragraphs = paragraphs[: _MAX_REPLY_BLOCKS - 1] + ["\n\n".join(paragraphs[_MAX_REPLY_BLOCKS - 1 :])]
        blocks.append(_toggle(f"🙋 [{where}] {e.get('label') or e.get('message', '')}", [_para(p) for p in paragraphs]))
    return blocks


# ---------- API 호출 ----------
def _friendly_error(e: APIResponseError) -> NotionExportError:
    if e.status == 401:
        return NotionExportError("Notion 연결이 만료되었거나 해제되었습니다. Notion을 다시 연결해주세요.")
    if e.status in (403, 404):
        return NotionExportError(
            "선택한 페이지에 접근할 수 없습니다. Notion 연결 시 해당 페이지를 공유(허용)했는지 확인하거나 다시 연결해주세요."
        )
    if e.status == 429:
        return NotionExportError("Notion 요청이 많습니다. 잠시 후 다시 시도해주세요.")
    return NotionExportError(f"Notion API 오류: {e}")


def _page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "제목 없음"
    return "제목 없음"


def list_pages(token: str, limit: int = 100) -> list[dict]:
    """OAuth 연결 시 사용자가 이 앱에 공유한 페이지 목록."""
    notion = Client(auth=token)
    try:
        res = notion.search(filter={"property": "object", "value": "page"}, page_size=limit)
    except APIResponseError as e:
        raise _friendly_error(e) from e
    pages = []
    for p in res.get("results", []):
        if p.get("object") != "page" or p.get("archived") or p.get("in_trash"):
            continue
        icon = (p.get("icon") or {}).get("emoji", "📄")
        pages.append({"id": p["id"].replace("-", ""), "title": _page_title(p), "url": p.get("url", ""), "icon": icon})
    return pages


def export_to_notion(token: str, parent_page_id: str, title: str, data: dict, items: set[str]) -> str:
    if not data["questions"]:
        raise NotionExportError("내보낼 문제가 없습니다.")
    title = title.strip() or f"[학습 결과] {data['filename']} · {datetime.now():%Y-%m-%d %H:%M}"
    blocks = build_export_blocks(data, items)
    notion = Client(auth=token)
    try:
        page = notion.pages.create(
            parent={"page_id": parent_page_id.replace("-", "")},
            icon={"type": "emoji", "emoji": "📝"},
            properties={"title": {"title": _rt(title)}},
            children=blocks[:_MAX_CHILDREN],
        )
        for i in range(_MAX_CHILDREN, len(blocks), _MAX_CHILDREN):
            notion.blocks.children.append(block_id=page["id"], children=blocks[i : i + _MAX_CHILDREN])
    except APIResponseError as e:
        raise _friendly_error(e) from e
    return page.get("url", "")
