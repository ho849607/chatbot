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
# Streamlit 페이지 설정
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
def ask_gpt(messages, model_name="gpt-4", temperature=0.0):
    """
    messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
    """
    try:
        import openai
        resp = openai.ChatCompletion.create(
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
    """
    1) 문서를 청크로 분할해 부분 요약
    2) 최종 요약 + 중요문장 + 질문 + 핵심단어 + 관련근거(가상의 예시)
    3) highlights(밑줄/색상)과 images_info(이미지 관련 메모)를 추가로 GPT에게 전달
    """
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
    # 최종 분석 프롬프트
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

    위 내용을 종합하여, 다음을 수행해 주세요:
    1) 문서 전체 요약
    2) 이 문서에서 가장 중요한 문장 3개
    3) 사용자에게 묻고 싶은 질문 2개 (Clarifying Questions)
    4) 이 문서의 핵심 단어(Keywords) 5개
    5) 관련 근거(References)를 2~3개 만들어 제시 (가상 가능)
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
    """pdfplumber 이용하여 페이지별 텍스트 추출 및 이미지 정보 수집."""
    text_list = []
    images_info = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                # 텍스트
                page_text = page.extract_text() or ""
                text_list.append(page_text)
                # 이미지
                # pdfplumber에서 이미지 자체를 추출하기 위해선 .to_image() 등 활용
                # 여기서는 단순히 좌표만 예시로 표시
                if page.images:
                    for img in page.images:
                        # img = {"x0", "y0", "x1", "y1", "width", "height"}
                        images_info.append(f"PDF Page {i+1} 이미지: {img}")
    except Exception as e:
        st.error(f"PDF 파일 처리 오류: {e}")
    return "\n".join(text_list), images_info

def parse_ppt(file_bytes):
    """python-pptx를 이용하여 PPT 텍스트 + (밑줄/색상) + 이미지 정보를 추출."""
    highlights = []
    images_info = []
    text_runs = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide_idx, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                # 텍스트 상자/플레이스홀더
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run_text = run.text
                            if run.font.underline:
                                # 밑줄 처리된 텍스트
                                highlights.append(
                                    f"[슬라이드 {slide_idx+1}] 밑줄: {run_text}"
                                )
                            if run.font.color and run.font.color.rgb:
                                # 색상이 있는 텍스트
                                color_str = run.font.color.rgb
                                highlights.append(
                                    f"[슬라이드 {slide_idx+1}] 색상({color_str}): {run_text}"
                                )
                            # 전체 텍스트 수집
                            text_runs.append(run_text)

                # 이미지(Picture)
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and isinstance(shape, Picture):
                    # shape.image.blob 등으로 접근 가능
                    width = shape.width
                    height = shape.height
                    images_info.append(f"[슬라이드 {slide_idx+1}] 이미지(Picture) 크기: {width}x{height}")
    except Exception as e:
        st.error(f"PPT 파일 처리 오류: {e}")

    # PPT 전체 텍스트
    full_text = "\n".join(text_runs)
    # 밑줄, 색상 정보
    highlight_str = "\n".join(highlights)

    return full_text, highlight_str, images_info

###############################################################################
# GPT 채팅 인터페이스 (기존)
###############################################################################
def chat_interface():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for chat in st.session_state.chat_history:
        role = chat["role"]
        content = chat["message"]
        with st.chat_message(role):
            st.write(content)

    user_chat_input = st.chat_input("메시지를 입력하세요:")
    if user_chat_input:
        st.session_state.chat_history.append({"role": "user", "message": user_chat_input})
        with st.chat_message("user"):
            st.write(user_chat_input)

        with st.spinner("GPT가 응답 중입니다..."):
            response = ask_gpt([
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": user_chat_input}
            ], model_name="gpt-4")

        st.session_state.chat_history.append({"role": "assistant", "message": response})
        with st.chat_message("assistant"):
            st.write(response)

###############################################################################
# 커뮤니티 탭 (이미지 등록 유지)
###############################################################################
def community_tab():
    st.header("커뮤니티 (문제 공유 및 해결책 모색)")
    if "community_ideas" not in st.session_state:
        st.session_state.community_ideas = []

    st.subheader("새로운 문제/아이디어 제안하기")
    idea_title = st.text_input("제목", "")
    idea_content = st.text_area("내용 (간략 소개)", "")

    # 여러 이미지를 업로드 가능
    image_files = st.file_uploader("이미지를 등록하세요 (선택사항)", type=["png","jpg","jpeg"], accept_multiple_files=True)

    if st.button("등록"):
        if idea_title.strip() and idea_content.strip():
            images_data = []
            if image_files:
                for img in image_files:
                    images_data.append(img.getvalue())  # 바이트로 저장

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
        st.write("아직 등록된 문제/아이디어가 없습니다.")
    else:
        for idx, idea in enumerate(st.session_state.community_ideas):
            with st.expander(f"{idx+1}. {idea['title']}"):
                st.write(f"**내용**: {idea['content']}")

                # 이미지 표시
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

                comment_text = st.text_input(f"댓글 달기 (#{idx+1})", key=f"comment_input_{idx}")
                if st.button(f"댓글 등록 (#{idx+1})"):
                    if comment_text.strip():
                        idea["comments"].append(comment_text.strip())
                        st.success("댓글이 등록되었습니다!")
                        st.experimental_rerun()
                    else:
                        st.warning("댓글 내용을 입력하세요.")
                st.write("---")

###############################################################################
# 확장된 DOCS(파일) 분석 탭
# 1) docx, ppt, pdf 모두 지원
# 2) 이미지 / 밑줄 / 색상 강조 / 핵심단어 / Clarifying questions 등
###############################################################################
def docs_analysis_tab():
    st.subheader("파일 분석 (DOCX / PDF / PPT)")

    if "processed_result" not in st.session_state:
        st.session_state.processed_result = ""

    uploaded_file = st.file_uploader("파일을 업로드하세요 (docx, pdf, pptx)", type=["docx","pdf","pptx"])
    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.md5(file_bytes).hexdigest()

        # 매번 새 파일 업로드 시 처리 리셋
        if ("uploaded_file_hash" not in st.session_state or
            st.session_state.uploaded_file_hash != file_hash):
            st.session_state.uploaded_file_hash = file_hash
            st.session_state.processed_result = ""
            st.session_state.processed = False

        if not st.session_state.get("processed"):
            extension = uploaded_file.name.split(".")[-1].lower()

            # 공통 분석할 텍스트, 하이라이트, 이미지 정보
            merged_text = ""
            highlight_text = ""
            images_info = ""

            with st.spinner("파일 분석 중..."):
                if extension == "docx":
                    raw_text = parse_docx(file_bytes)
                    merged_text = raw_text
                elif extension == "pdf":
                    raw_text, pdf_images = parse_pdf(file_bytes)
                    merged_text = raw_text
                    images_info = "\n".join(str(i) for i in pdf_images)
                elif extension == "pptx":
                    ppt_text, ppt_highlights, ppt_images = parse_ppt(file_bytes)
                    merged_text = ppt_text
                    highlight_text = ppt_highlights
                    images_info = "\n".join(str(i) for i in ppt_images)
                else:
                    st.error("지원하지 않는 파일 형식입니다.")
                    return

                # 실제 텍스트가 있으면 GPT에 보냄
                if merged_text.strip():
                    final_summary = advanced_document_processing(
                        full_text=merged_text,
                        highlights=highlight_text,
                        images_info=images_info
                    )
                    st.session_state.processed_result = final_summary
                    st.session_state.processed = True
                else:
                    st.error("문서 텍스트를 추출할 수 없습니다.")
                    st.session_state.processed = True

        # 처리된 결과 표시
        if st.session_state.get("processed") and st.session_state.processed_result:
            st.write("## 분석 결과")
            st.write(st.session_state.processed_result)

###############################################################################
# 메인 함수
###############################################################################
def main():
    st.title("studyhelper (Extended)")
    st.write("""
    GPT 채팅 / DOCX + PDF + PPT 분석 / 커뮤니티(이미지 등록) 기능을 제공합니다. (GPT-4)
    - 밑줄 / 색상 강조 / 이미지 정보도 함께 GPT에 전달 (PPT, PDF)
    - GPT가 요약, Clarifying Questions, 핵심단어, 가상의 References 등 생성
    """)

    tab = st.sidebar.radio("메뉴 선택", ("GPT 채팅", "파일 분석", "커뮤니티"))

    if tab == "GPT 채팅":
        st.subheader("GPT 채팅")
        chat_interface()

    elif tab == "파일 분석":
        docs_analysis_tab()

    elif tab == "커뮤니티":
        st.subheader("커뮤니티")
        community_tab()

    st.write("---")
    st.info("GPT 응답은 실제 정보를 보장하지 않을 수 있으니, 참고용으로만 활용하세요.")

if __name__ == "__main__":
    main()
