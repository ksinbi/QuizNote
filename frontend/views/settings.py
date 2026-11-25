"""STEP 2. 문제 생성 조건 설정"""
import time

import streamlit as st

import api_client as api
import state
from components import ui

MAX_QUESTIONS = 20
DIFFICULTY_DESC = {"쉬움": "핵심 용어 · 정의 확인", "보통": "개념 비교 · 간단한 적용", "어려움": "종합 · 사례 분석"}


def validate(s: dict) -> list[str]:
    errors = []
    if not 1 <= s["num_questions"] <= MAX_QUESTIONS:
        errors.append(f"전체 문제 수는 1~{MAX_QUESTIONS} 사이로 입력해주세요.")
    if s["num_essay"] < 0:
        errors.append("서술형 문항 수는 0 이상이어야 해요.")
    elif s["num_essay"] > s["num_questions"]:
        errors.append("서술형 문항 수는 전체 문제 수보다 많을 수 없어요.")
    return errors


def render() -> None:
    flow = state.flow()
    cur = flow["settings"]
    ui.page_title("문제 생성 조건 설정", f"📄 <b>{ui.esc(flow['upload']['filename'])}</b>")

    left, right = st.columns(2, gap="medium")
    with left, st.container(border=True):
        st.markdown("**문항 구성**")
        n = st.number_input("전체 문제 수", min_value=1, max_value=MAX_QUESTIONS, value=int(cur["num_questions"]), step=1, key="set_n")
        e = st.number_input("서술형 문항 수", min_value=0, max_value=MAX_QUESTIONS, value=int(cur["num_essay"]), step=1, key="set_e")
        st.caption(f"객관식 **{max(0, n - e)}**문항 · 서술형 **{e}**문항")
        diff = st.segmented_control(
            "난이도", ["쉬움", "보통", "어려움"], default=cur["difficulty"], required=True, width="stretch", key="set_diff"
        )
        st.caption(DIFFICULTY_DESC.get(diff or cur["difficulty"], ""))

    with right, st.container(border=True):
        st.markdown("**채점 화면 옵션**")
        show_answer = st.toggle("정답 표시", value=cur["show_answer"], help="답변 제출 후 정답을 함께 보여줘요", key="set_ans")
        show_explanation = st.toggle("해설 제공", value=cur["show_explanation"], help="문제별 해설과 보충 설명을 보여줘요", key="set_exp")
        show_source = st.toggle("원문 출처 표기", value=cur["show_source"], help="근거가 된 PDF 페이지와 원문을 보여줘요", key="set_src")
        with st.expander("고급 설정", expanded=bool(cur["focus_topic"] or cur["use_web"])):
            focus = st.text_input("집중 주제 (선택)", value=cur["focus_topic"], max_chars=200, placeholder="예: 정규화, 3장 내용", key="set_focus")
            use_web = st.toggle("웹 검색 보강", value=cur["use_web"], help="실제 사례와 오답 보충 설명에 인터넷 검색을 활용해요 (느려질 수 있음)", key="set_web")

    new = {
        "num_questions": int(n),
        "num_essay": int(e),
        "difficulty": diff or cur["difficulty"],
        "show_answer": show_answer,
        "show_explanation": show_explanation,
        "show_source": show_source,
        "focus_topic": focus.strip(),
        "use_web": use_web,
    }
    if new != cur:
        state.update_flow(settings=new)

    errors = validate(new)
    if errors:
        st.error("\n\n".join(errors))

    back, _, go = st.columns([2, 1, 2])
    if back.button("← PDF 다시 선택", width="stretch"):
        state.update_flow(step="upload")
        st.rerun()
    if go.button("✨ 문제 생성하기", type="primary", width="stretch", disabled=bool(errors)):
        try:
            api.generate(flow["upload"]["session_id"], new)
        except api.APIError as err:
            st.error(str(err))
            return
        state.clear_study_cache()
        state.ss().gen_started = time.time()
        state.update_flow(step="generating", current_index=0, saved=None, ended=False)
        st.rerun()
