import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import hashlib

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import docx2txt

import pdfplumber
from pptx import Presentation
from pptx.slide import Slide
from pptx.shapes.picture import Picture
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE

###############################################################################
# NLTK 설정 (stopwords 등)
###############################################################################
nltk_data_dir = "/tmp/nltk_data"
os.makedirs(nltk_data_dir, exist_ok=True)
os.environ["NLTK_DATA"] = nltk_data_dir
nltk.data.path.append(nltk_data_dir)

try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", download_dir=nltk_data_dir)
try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords", download_dir=nltk_data_dir)

korean_stopwords = [
    "이","그","저","것","수","등","들","및","더","로","를","에",
    "의","은","는","가","와","과","하다","있다","되다","이다",
    "으로","에서","까지","부터","만","그리고","하지만","그러나"
]
english_stopwords = set(stopwords.words("english"))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# Streamlit 페이지 설정 (페이지 제목: studyhelper)
###############################################################################
st.set_page_config(page_title="studyhelper", layout="centered")

###############################################################################
# .env 로드 및 OpenAI API 키 설정
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# (openai>=1.0.0) ChatCompletion 함수
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    try:
        resp = openai.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 긴 텍스트 -> 청크 분할 (문자 기준)
###############################################################################
def split_text_into_chunks(text, max_chars=3000):
    chunks = []
    start_idx = 0
    while start_idx < len(text):
        end_idx = min(start_idx + max_chars, len(text))
        chunk = text[start_idx:end_idx]
        chunks.append(chunk)
        start_idx = end_idx
    return chunks

###############################################################################
# 고급 분석 -> 부분 요약 -> 최종 요약(중요문장/질문/핵심단어/관련근거)
# (docx/ppt/pdf 이미지/밑줄/색상 등도 추가)
###############################################################################
def advanced_document_processing(full_text, highlights="", images_info=""):
    chunks = split_text_into_chunks(full_text, max_chars=3000)

    partial_summaries = []
    for i, chunk in enumerate(chunks):
        prompt_chunk = f"""
        아래는 문서의 일부 내용입니다 (청크 {i+1}/{len(chunks)}).
        ---
        {chunk}
        ---
        이 텍스트를 간단히 요약해 주세요.
        """
        summary = ask_gpt([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt_chunk.strip()},
        ], model_name="gpt-4")
        partial_summaries.append(summary)

    combined_text = "\n\n".join(partial_summaries)
    final_prompt = f"""
    아래는 여러 부분 요약을 합친 내용입니다:
    ---
    {combined_text}
    ---
    추가 정보:
    - 밑줄/색상 강조된 문구들:
    {highlights}
    - 포함된 이미지 정보:
    {images_info}

    다음을 수행해 주세요:
    1) 문서 전체 요약
    2) 중요한 문장 3개
    3) 사용자에게 묻고 싶은 질문(또는 퀴즈) 2~3개
    4) 핵심 단어(Keywords) 5개
    5) 관련 근거(References) 2~3개 (가상)
    """
    final_result = ask_gpt([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": final_prompt.strip()},
    ], model_name="gpt-4")

    return final_result

###############################################################################
# 파일 파싱 함수들 (DOCX / PDF / PPT)
###############################################################################
def parse_docx(file_bytes):
    try:
        text = docx2txt.process(BytesIO(file_bytes))
        return text if text else ""
    except Exception as e:
        st.error(f"DOCX 파일 처리 오류: {e}")
        return ""

def parse_pdf(file_bytes):
    text_list = []
    images_info = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                text_list.append(page_text)
                if page.images:
                    for img in page.images:
                        images_info.append(f"PDF Page {i+1} 이미지: {img}")
    except Exception as e:
        st.error(f"PDF 파일 처리 오류: {e}")
    return "\n".join(text_list), images_info

def parse_ppt(file_bytes):
    highlights = []
    images_info = []
    text_runs = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide_idx, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run_text = run.text
                            if run.font.underline:
                                highlights.append(f"[슬라이드 {slide_idx+1}] 밑줄: {run_text}")
                            if run.font.color and run.font.color.rgb:
                                color_str = run.font.color.rgb
                                highlights.append(f"[슬라이드 {slide_idx+1}] 색상({color_str}): {run_text}")
                            text_runs.append(run_text)
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and isinstance(shape, Picture):
                    w, h = shape.width, shape.height
                    images_info.append(f"[슬라이드 {slide_idx+1}] 이미지 크기: {w}x{h}")
    except Exception as e:
        st.error(f"PPT 파일 처리 오류: {e}")

    return "\n".join(text_runs), "\n".join(highlights), "\n".join(images_info)

###############################################################################
# GPT 채팅 인터페이스 (+ GPT 질문 답변 기능)
###############################################################################
def chat_interface():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 1) 기존 대화 표시
    for chat in st.session_state.chat_history:
        role = chat["role"]
        content = chat["message"]
        with st.chat_message(role):
            st.write(content)

    # 2) GPT 질문 감지
    #    - 단순 예시로, "질문:" 문자열이 있으면 찾아서 표시
    #    - 실제로는 더 정교한 패턴 검색/파싱이 필요할 수도 있음
    last_gpt_message = ""
    if st.session_state.chat_history:
        last_msg = st.session_state.chat_history[-1]
        if last_msg["role"] == "assistant":
            last_gpt_message = last_msg["message"]
    user_answer_text = ""
    if "질문:" in last_gpt_message:
        # 사용자 답변받기
        user_answer_text = st.text_input("GPT 질문에 대한 답변을 입력하세요:")
        if st.button("GPT에게 답변 전달"):
            # GPT에게 "사용자는 이렇게 답변했다" 라고 추가 메시지
            st.session_state.chat_history.append({
                "role": "user",
                "message": f"사용자의 답변: {user_answer_text}"
            })
            with st.chat_message("user"):
                st.write(f"(사용자 답변) {user_answer_text}")

            with st.spinner("GPT가 답변을 확인 중..."):
                # 이전 대화 전체를 기반으로 응답 생성
                full_messages = [
                    {"role": msg["role"], "content": msg["message"]}
                    for msg in st.session_state.chat_history
                ]
                gpt_answer = ask_gpt(full_messages, model_name="gpt-4", temperature=0.7)

            st.session_state.chat_history.append({
                "role": "assistant",
                "message": gpt_answer
            })
            with st.chat_message("assistant"):
                st.write(gpt_answer)

    # 3) 일반 채팅 입력
    user_chat_input = st.chat_input("메시지를 입력하세요:")
    if user_chat_input:
        # 사용자 메시지 추가
        st.session_state.chat_history.append({"role": "user", "message": user_chat_input})
        with st.chat_message("user"):
            st.write(user_chat_input)

        # GPT 응답
        with st.spinner("GPT가 응답 중..."):
            role_messages = [
                {"role": msg["role"], "content": msg["message"]}
                for msg in st.session_state.chat_history
            ]
            response_text = ask_gpt(role_messages, model_name="gpt-4", temperature=0.7)

        st.session_state.chat_history.append({"role": "assistant", "message": response_text})
        with st.chat_message("assistant"):
            st.write(response_text)

###############################################################################
# 커뮤니티 탭 (이미지 등록)
###############################################################################
def community_tab():
    st.header("커뮤니티 (문제 공유)")

    if "community_ideas" not in st.session_state:
        st.session_state.community_ideas = []

    st.subheader("새로운 문제/아이디어 제안하기")
    idea_title = st.text_input("제목", "")
    idea_content = st.text_area("내용 (간략 소개)", "")

    image_files = st.file_uploader("이미지를 등록하세요 (선택)", type=["png","jpg","jpeg"], accept_multiple_files=True)

    if st.button("등록"):
        if idea_title.strip() and idea_content.strip():
            images_data = []
            if image_files:
                for img in image_files:
                    images_data.append(img.getvalue())

            new_idea = {
                "title": idea_title,
                "content": idea_content,
                "comments": [],
                "images": images_data,
            }
            st.session_state.community_ideas.append(new_idea)
            st.success("등록되었습니다!")
        else:
            st.warning("제목과 내용을 입력하세요.")

    st.write("---")
    st.subheader("커뮤니티 목록")
    if len(st.session_state.community_ideas) == 0:
        st.write("아직 등록된 문제가 없습니다.")
    else:
        for idx, idea in enumerate(st.session_state.community_ideas):
            with st.expander(f"{idx+1}. {idea['title']}"):
                st.write(f"**내용**: {idea['content']}")
                if idea.get("images"):
                    st.write("### 첨부 이미지")
                    for img_bytes in idea["images"]:
                        st.image(img_bytes)
                st.write("### 댓글")
                if len(idea["comments"]) == 0:
                    st.write("아직 댓글이 없습니다.")
                else:
                    for c_idx, comment in enumerate(idea["comments"]):
                        st.write(f"- {comment}")

                comment_text = st.text_input("댓글 달기", key=f"comment_{idx}")
                if st.button(f"댓글 등록 #{idx+1}"):
                    if comment_text.strip():
                        idea["comments"].append(comment_text.strip())
                        st.success("댓글이 등록되었습니다!")
                        st.experimental_rerun()

###############################################################################
# 파일 분석 -> 자동 요약
###############################################################################
def analyze_file(file_bytes, filename):
    extension = filename.split(".")[-1].lower()
    raw_text = ""
    highlight_text = ""
    images_info = []

    if extension == "docx":
        raw_text = parse_docx(file_bytes)
    elif extension == "pdf":
        pdf_text, pdf_imgs = parse_pdf(file_bytes)
        raw_text = pdf_text
        images_info = pdf_imgs
    elif extension == "pptx":
        ppt_text, ppt_highlights, ppt_imgs = parse_ppt(file_bytes)
        raw_text = ppt_text
        highlight_text = ppt_highlights
        images_info = ppt_imgs
    else:
        st.error("지원하지 않는 파일 형식입니다.")
        return

    if not raw_text.strip():
        st.warning("텍스트를 추출할 수 없습니다.")
        return

    images_join = "\n".join(images_info)
    with st.spinner("문서 분석 중..."):
        result = advanced_document_processing(raw_text, highlight_text, images_join)

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # system 메시지(분석 완료) + assistant 메시지(분석 결과)
    st.session_state.chat_history.append({
        "role": "system",
        "message": f"업로드된 파일({filename}) 분석 완료."
    })
    st.session_state.chat_history.append({
        "role": "assistant",
        "message": result
    })
    st.success("파일 분석 완료! 아래 GPT 채팅에서 대화를 이어가 보세요.")

###############################################################################
# 메인
###############################################################################
def main():
    st.title("studyhelper")

    # 간단 안내
    st.write("""
    - 파일 업로드 시 자동 분석 (DOCX/PDF/PPTX)
    - GPT 채팅 (대화형)
      - GPT가 질문을 던지면, 별도의 입력 필드를 통해 답변 가능
    - 커뮤니티 (이미지 등록 포함)
    """)

    # 파일 업로드 (자동 분석)
    uploaded_file = st.file_uploader("파일을 업로드하세요 (docx, pdf, pptx)", type=["docx","pdf","pptx"])
    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.md5(file_bytes).hexdigest()
        if ("current_file_hash" not in st.session_state or
            st.session_state.current_file_hash != file_hash):
            st.session_state.current_file_hash = file_hash
            analyze_file(file_bytes, uploaded_file.name)

    st.markdown("---")
    st.header("GPT 채팅 & 질문 답변")
    chat_interface()

    st.markdown("---")
    community_tab()

    st.write("---")
    st.info("GPT 응답은 참고용입니다. 중요한 내용은 직접 검증하세요.")

if __name__ == "__main__":
    main()
