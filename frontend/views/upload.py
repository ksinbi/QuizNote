"""STEP 1. PDF 업로드 — 드래그 앤 드롭, 파일 정보, 미리보기, 삭제/재업로드, 텍스트 추출"""
import pymupdf
import streamlit as st

import api_client as api
import state
from components import ui

MAX_MB = 30


@st.cache_data(max_entries=48, show_spinner=False)
def _render_page(file_key: str, page: int, _data: bytes) -> bytes:
    """PDF 페이지를 PNG로 렌더링 (브라우저 PDF 뷰어 지원 여부와 무관하게 미리보기)."""
    with pymupdf.open(stream=_data, filetype="pdf") as doc:
        pix = doc[page - 1].get_pixmap(dpi=110)
        return pix.tobytes("png")


def _clear_upload() -> None:
    s = state.ss()
    s.pdf_bytes = None
    s.uploaded_file_id = None
    s.upload_error = None
    s.uploader_nonce += 1  # 업로더 위젯 초기화
    state.clear_study_cache()
    state.update_flow(upload=None, step="upload")


def render() -> None:
    s = state.ss()
    ui.page_title("학습할 PDF를 올려주세요", "AI가 문서를 분석해서 원하는 조건에 맞는 문제를 만들어 드려요.")

    file = st.file_uploader(
        "PDF 파일을 끌어다 놓거나 클릭해서 선택하세요",
        type=["pdf"],
        key=f"uploader_{s.uploader_nonce}",
        help=f"최대 {MAX_MB}MB · 텍스트가 포함된 PDF",
    )

    if file is not None and s.uploaded_file_id != file.file_id:
        data = file.getvalue()
        s.uploaded_file_id = file.file_id
        s.upload_error = None
        if len(data) > MAX_MB * 1024 * 1024:
            s.upload_error = f"파일이 너무 커요. 최대 {MAX_MB}MB까지 업로드할 수 있어요."
        else:
            with st.spinner("텍스트를 추출하고 문서를 분석하는 중..."):
                try:
                    info = api.upload_pdf(file.name, data)
                except api.APIError as e:
                    s.upload_error = str(e)
                else:
                    s.pdf_bytes = data
                    state.clear_study_cache()
                    state.update_flow(upload=info, step="upload")
    elif file is None and s.uploaded_file_id is not None:
        # 업로더의 X 버튼으로 파일을 지운 경우
        _clear_upload()
        st.rerun()

    if s.upload_error:
        st.error(s.upload_error)
        return

    upload = state.flow()["upload"]
    if not upload:
        return

    info_col, preview_col = st.columns([2, 3], gap="medium")
    with info_col:
        ui.html_block(
            f"""<div class="qn-panel">
  <div class="qn-file"><span class="ic">📕</span><div><b>{ui.esc(upload['filename'])}</b><small>{ui.format_bytes(upload['file_size'])}</small></div></div>
  <div class="qn-info">
    <div><small>전체 페이지</small><b>{upload['num_pages']}p</b></div>
    <div><small>텍스트 페이지</small><b>{upload['num_text_pages']}p</b></div>
    <div><small>추출 글자 수</small><b>{upload['num_chars']:,}</b></div>
    <div><small>분석 단위</small><b>{upload['num_chunks']}개</b></div>
  </div>
</div>"""
        )
        if upload["num_text_pages"] < upload["num_pages"]:
            st.warning(f"일부 페이지({upload['num_pages'] - upload['num_text_pages']}p)는 이미지라 텍스트를 추출하지 못했어요.")
        c1, c2 = st.columns(2)
        if c1.button("🗑️ 삭제", width="stretch"):
            _clear_upload()
            st.rerun()
        if c2.button("🔄 다시 올리기", width="stretch", help="현재 파일을 지우고 새 파일을 선택해요"):
            _clear_upload()
            st.rerun()

    with preview_col:
        with st.container(border=True):
            if s.pdf_bytes:
                page = 1
                if upload["num_pages"] > 1:
                    page = st.slider("미리보기 페이지", 1, upload["num_pages"], 1)
                st.image(_render_page(s.uploaded_file_id or upload["session_id"], page, s.pdf_bytes), width="stretch")
            else:
                st.info("새로고침하여 미리보기가 사라졌어요. 분석된 문서 정보는 그대로 유지돼요.")

    st.write("")
    _, right = st.columns([3, 2])
    if right.button("다음: 문제 조건 설정 →", type="primary", width="stretch"):
        state.update_flow(step="settings")
        st.rerun()
