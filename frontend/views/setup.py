"""STEP 1. PDF 업로드 + 문제 생성 조건 설정 (한 화면)

왼쪽: 드래그 앤 드롭 업로드, 파일 정보, 미리보기, 다른 PDF 선택
오른쪽: 문항 수 · 서술형 수 · 난이도 · 부가 옵션 → AI 문제 생성
"""
import time

import pymupdf
import streamlit as st

import api_client as api
import state
from components import ui

MAX_MB = 30
MAX_QUESTIONS = 20
COUNT_OPTIONS = [5, 10, 15, 20]
ESSAY_OPTIONS = [0, 1, 2, 3]
DIFFICULTY_DESC = {"쉬움": "핵심 용어 · 정의 확인", "보통": "핵심 개념 중심", "어려움": "종합 · 사례 분석"}
OPTIONS = [
    ("show_answer", "list-check", "정답 표시", "답변을 제출하면 정답을 함께 보여줍니다."),
    ("show_explanation", "lightbulb", "해설 포함", "문항별 상세한 해설과 보충 설명을 제공합니다."),
    ("show_source", "book", "원문 출처(페이지) 표기", "PDF 내 해당 개념이 등장하는 페이지 번호와 원문을 함께 표시합니다."),
]


@st.cache_data(max_entries=48, show_spinner=False)
def _render_page(file_key: str, page: int, _data: bytes) -> bytes:
    """PDF 페이지를 PNG로 렌더링 (브라우저 PDF 뷰어 지원 여부와 무관하게 미리보기)."""
    with pymupdf.open(stream=_data, filetype="pdf") as doc:
        pix = doc[page - 1].get_pixmap(dpi=110)
        return pix.tobytes("png")


def validate(s: dict) -> list[str]:
    errors = []
    if not 1 <= s["num_questions"] <= MAX_QUESTIONS:
        errors.append(f"전체 문제 수는 1~{MAX_QUESTIONS} 사이로 선택해주세요.")
    if s["num_essay"] < 0:
        errors.append("서술형 문항 수는 0 이상이어야 해요.")
    elif s["num_essay"] > s["num_questions"]:
        errors.append("서술형 문항 수는 전체 문제 수보다 많을 수 없어요.")
    return errors


CUSTOM = "직접 입력"


def _count_picker(label: str, unit: str, presets: list[int], current: int, lo: int, hi: int, key: str) -> int:
    """자주 쓰는 개수는 버튼으로, 그 외 개수는 '직접 입력'으로 지정."""
    custom_key = f"{key}_custom"
    choice = st.session_state.get(key, current if current in presets else CUSTOM)
    if choice == CUSTOM:
        value = int(st.session_state.get(custom_key, min(max(current, lo), hi)))
    else:
        value = int(choice)
    ui.field_label(label, f"{value}{unit} 선택됨")
    choice = st.segmented_control(
        label, [*presets, CUSTOM], default=current if current in presets else CUSTOM,
        format_func=lambda v: v if v == CUSTOM else f"{v}{unit}",
        required=True, width="stretch", key=key, label_visibility="collapsed",
    )
    if choice != CUSTOM:
        return int(choice)
    return int(st.number_input(
        f"{label} 직접 입력", min_value=lo, max_value=hi, value=min(max(current, lo), hi), step=1,
        key=custom_key, width=220, help=f"{lo}~{hi} 사이로 입력해주세요",
    ))


def _clear_upload() -> None:
    s = state.ss()
    s.pdf_bytes = None
    s.uploaded_file_id = None
    s.upload_error = None
    s.uploader_nonce += 1  # 업로더 위젯 초기화
    s.preview_open = False
    state.clear_study_cache()
    state.update_flow(upload=None, step="upload")


def _handle_file(file) -> None:
    s = state.ss()
    if file is None or s.uploaded_file_id == file.file_id:
        return
    data = file.getvalue()
    s.uploaded_file_id = file.file_id
    s.upload_error = None
    if len(data) > MAX_MB * 1024 * 1024:
        s.upload_error = f"파일이 너무 커요. 최대 {MAX_MB}MB까지 업로드할 수 있어요."
        return
    with st.spinner("텍스트를 추출하고 문서를 분석하는 중..."):
        try:
            info = api.upload_pdf(file.name, data)
        except api.APIError as e:
            s.upload_error = str(e)
            return
    s.pdf_bytes = data
    state.clear_study_cache()
    state.update_flow(upload=info, step="upload")
    st.rerun()


def render() -> None:
    flow = state.flow()
    n = flow["settings"]["num_questions"]
    ui.page_header(
        1,
        "AI 학습 자료 분석 및 퀴즈 구성",
        "<b>PDF</b> 업로드 및 문제 설정",
        f'{ui.icon("clock", 18)}<span>예상 생성 시간: 약 {15 + n * 4}초</span>',
    )
    left, right = st.columns(2, gap="medium")
    with left, st.container(key="qn_card_pdf", height="stretch"):
        _pdf_panel()
    with right, st.container(key="qn_card_settings", height="stretch"):
        _settings_panel()


# ---------- 왼쪽: 학습 자료 PDF ----------
def _pdf_panel() -> None:
    s = state.ss()
    upload = state.flow()["upload"]
    ready = '<span class="qn-ready">' + ui.icon("check-circle", 16) + "분석 준비 완료</span>" if upload else ""
    ui.card_title("file-up", "학습 자료 PDF", ready)

    if not upload:
        with st.container(key="qn_dropzone"):
            file = st.file_uploader(
                "PDF 파일을 끌어다 놓거나 클릭해서 선택하세요",
                type=["pdf"],
                key=f"uploader_{s.uploader_nonce}",
                help=f"최대 {MAX_MB}MB · 텍스트가 포함된 PDF",
            )
        _handle_file(file)
        if s.upload_error:
            st.error(s.upload_error)
        else:
            st.caption("업로드하면 AI가 텍스트를 추출하고 문서를 분석해요. 스캔 이미지 PDF는 텍스트를 읽지 못할 수 있어요.")
        return

    ui.html_block(
        f"""<div class="qn-file"><div class="qn-pdf">{ui.icon("file-text", 26)}PDF</div>
<div style="min-width:0"><b>{ui.esc(upload['filename'])}</b>
<small>{ui.icon("pages", 16)}{upload['num_pages']}페이지 · {ui.icon("drive", 16)}{ui.format_bytes(upload['file_size'])}</small></div></div>"""
    )
    preview_open = s.get("preview_open", False)
    with st.container(horizontal=True, key="qn_file_actions"):
        if st.button("미리보기 닫기" if preview_open else "빠른 미리보기",
                     icon=":material/visibility_off:" if preview_open else ":material/visibility:", key="qn_preview_toggle"):
            s.preview_open = not preview_open
            st.rerun()
        if st.button("다른 PDF 선택", icon=":material/swap_horiz:", key="qn_change_pdf"):
            _clear_upload()
            st.rerun()

    if preview_open:
        with st.container(key="qn_preview"):
            if s.pdf_bytes:
                page = 1
                if upload["num_pages"] > 1:
                    page = st.slider("미리보기 페이지", 1, upload["num_pages"], 1)
                st.image(_render_page(s.uploaded_file_id or upload["session_id"], page, s.pdf_bytes), width="stretch")
            else:
                st.info("새로고침하여 미리보기가 사라졌어요. 분석된 문서 정보는 그대로 유지돼요.")

    chips = [
        f"텍스트 {upload['num_text_pages']}페이지",
        f"{upload['num_chars']:,}자 추출",
        f"분석 단위 {upload['num_chunks']}개",
        "의미 + 키워드 검색" if upload.get("retriever_mode", "").startswith("hybrid") else "키워드 검색",
    ]
    ui.html_block(
        '<div class="qn-keywords"><div><span>AI 문서 분석 결과</span><span>자동 분석됨</span></div>'
        f'<div class="qn-kw">{"".join(f"<span>{ui.esc(c)}</span>" for c in chips)}</div></div>'
    )
    if upload["num_text_pages"] < upload["num_pages"]:
        st.warning(f"일부 페이지({upload['num_pages'] - upload['num_text_pages']}p)는 이미지라 텍스트를 추출하지 못했어요.")

    st.space("stretch")  # 교체 영역을 카드 맨 아래로
    with st.container(key="qn_dropzone_replace"):
        file = st.file_uploader(
            "여기에 새 PDF 파일을 드래그하여 교체할 수 있습니다.",
            type=["pdf"],
            key=f"uploader_{s.uploader_nonce}",
            help=f"최대 {MAX_MB}MB",
        )
    _handle_file(file)
    if s.upload_error:
        st.error(s.upload_error)


# ---------- 오른쪽: 문제 생성 세부 설정 ----------
def _settings_panel() -> None:
    flow = state.flow()
    cur = flow["settings"]
    ui.card_title("sliders", "문제 생성 세부 설정", "맞춤형 출제")

    n = _count_picker("총 문제 수", "문제", COUNT_OPTIONS, cur["num_questions"], 1, MAX_QUESTIONS, "set_n")
    e = _count_picker("서술형 문항 수", "문항", ESSAY_OPTIONS, cur["num_essay"], 0, MAX_QUESTIONS, "set_e")
    diff_now = st.session_state.get("set_diff") or cur["difficulty"]
    ui.field_label("난이도", DIFFICULTY_DESC.get(diff_now, ""))
    diff = st.segmented_control(
        "난이도", ["쉬움", "보통", "어려움"], default=cur["difficulty"], required=True,
        width="stretch", key="set_diff", label_visibility="collapsed",
    )

    ui.html_block('<div class="qn-opt-title">부가 옵션</div>')
    toggles = {}
    for key, icon_name, title, desc in OPTIONS:
        with st.container(horizontal=True, key=f"qn_opt_{key}", vertical_alignment="center", wrap=False):
            ui.html_block(f'<div class="qn-opt">{ui.icon(icon_name, 20)}<div><b>{title}</b><small>{desc}</small></div></div>', width="stretch")
            toggles[key] = st.toggle(title, value=cur[key], key=f"set_{key}", label_visibility="collapsed")
    with st.expander("고급 설정", icon=":material/tune:", expanded=bool(cur["focus_topic"] or cur["use_web"])):
        focus = st.text_input("집중 주제 (선택)", value=cur["focus_topic"], max_chars=200, placeholder="예: 정규화, 3장 내용", key="set_focus")
        use_web = st.toggle("웹 검색 보강", value=cur["use_web"], help="실제 사례와 오답 보충 설명에 인터넷 검색을 활용해요 (느려질 수 있음)", key="set_web")

    new = {
        "num_questions": n,
        "num_essay": e,
        "difficulty": diff or cur["difficulty"],
        **toggles,
        "focus_topic": focus.strip(),
        "use_web": use_web,
    }
    if new != cur:
        state.update_flow(settings=new)

    errors = validate(new)
    if errors:
        st.error("\n\n".join(errors))

    upload = flow["upload"]
    with st.container(key="qn_generate"):
        clicked = st.button(
            "AI 문제 생성하기", icon=":material/auto_awesome:", type="primary", width="stretch",
            disabled=bool(errors) or not upload, help=None if upload else "먼저 PDF를 업로드해주세요",
        )
    if clicked:
        try:
            api.generate(upload["session_id"], new)
        except api.APIError as err:
            st.error(str(err))
            return
        state.clear_study_cache()
        state.ss().gen_started = time.time()
        state.update_flow(step="generating", current_index=0, saved=None, ended=False)
        st.rerun()
