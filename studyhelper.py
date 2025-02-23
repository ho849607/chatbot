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
# GPT 함수
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
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
# 파일 파싱 함수 (docx, pdf, pptx)
###############################################################################
def parse_docx(file_bytes: bytes) -> str:
    try:
        text = docx2txt.process(BytesIO(file_bytes))
        return text if text else ""
    except Exception as e:
        st.error(f"DOCX 파일 처리 오류: {e}")
        return ""

def parse_pdf(file_bytes: bytes):
    text_list = []
    images_info = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                text_list.append(page_text)
                # 이미지 메타데이터 예시
                if page.images:
                    for img in page.images:
                        images_info.append(f"PDF Page {i+1} 이미지: {img}")
    except Exception as e:
        st.error(f"PDF 파일 처리 오류: {e}")
    return "\n".join(text_list), images_info

def parse_ppt(file_bytes: bytes):
    highlights = []
    images_info = []
    text_runs = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide_idx, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                # 텍스트 상자
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
                # 이미지
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and isinstance(shape, Picture):
                    width, height = shape.width, shape.height
                    images_info.append(f"[슬라이드 {slide_idx+1}] 이미지 크기: {width}x{height}")
    except Exception as e:
        st.error(f"PPT 파일 처리 오류: {e}")

    return "\n".join(text_runs), "\n".join(highlights), "\n".join(images_info)

###############################################################################
# 자동 분석 + 요약 + 핵심단어 + GPT가 사용자에게 질문 등
###############################################################################
def analyze_file(file_bytes: bytes, filename: str):
    """
    파일 업로드 시 자동 호출. 문서 내용을 파싱하고,
    요약/핵심단어/근거/추가 질문(혹은 퀴즈) 등 GPT 메시지를 구성.
    """
    extension = filename.split(".")[-1].lower()

    raw_text = ""
    highlight_text = ""
    images_info = []

    # 파일 파싱
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
        st.warning("문서에서 텍스트를 추출할 수 없습니다.")
        return

    # GPT에 넘길 추가정보 (밑줄, 색상, 이미지)
    images_str = "\n".join(images_info)
    # 간단히 요청 프롬프트
    prompt = f"""
    다음은 업로드된 문서의 텍스트입니다:
    ---
    {raw_text}
    ---
    밑줄/색상 정보:
    {highlight_text}

    이미지 정보:
    {images_str}

    위 문서를 분석해 주세요.
    1) 문서 요약
    2) 핵심단어 5개
    3) 관련 근거(References) 2~3개 (가상의 예시 가능)
    4) 사용자에게 묻고 싶은 질문(혹은 퀴즈 형식) 2~3개
    모두 한국어로 답해 주세요.
    """
    # 메시지로 chat_history에 추가 + GPT 답변 받기
    st.session_state.chat_history.append({
        "role": "system",
        "message": "업로드된 파일을 분석합니다."
    })

    with st.spinner("GPT가 문서를 분석 중입니다..."):
        response = ask_gpt([
            {"role": "system", "content": "당신은 유용한 AI 비서입니다."},
            {"role": "user", "content": prompt.strip()}
        ], model_name="gpt-4", temperature=0.7)

    # 결과를 Chat 메시지로 추가
    st.session_state.chat_history.append({
        "role": "assistant",
        "message": response
    })

###############################################################################
# GPT 채팅창
###############################################################################
def chat_interface():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 채팅 UI: 기존 chat_history 출력
    for chat in st.session_state.chat_history:
        role = chat["role"]
        content = chat["message"]
        with st.chat_message(role):
            st.write(content)

    # 사용자가 새로 입력
    user_chat_input = st.chat_input("메시지를 입력하세요:")
    if user_chat_input:
        # 채팅 히스토리에 사용자 메시지 추가
        st.session_state.chat_history.append({
            "role": "user",
            "message": user_chat_input
        })
        with st.chat_message("user"):
            st.write(user_chat_input)

        # GPT 응답
        with st.spinner("GPT가 응답 중..."):
            response = ask_gpt([
                {"role": "system", "content": "당신은 유용한 AI 비서입니다."},
                *[
                    {"role": msg["role"], "content": msg["message"]}
                    for msg in st.session_state.chat_history
                    if msg["role"] in ("user", "assistant")
                ],
            ], model_name="gpt-4")

        st.session_state.chat_history.append({
            "role": "assistant",
            "message": response
        })
        with st.chat_message("assistant"):
            st.write(response)

###############################################################################
# 커뮤니티 탭
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
        st.write("아직 등록된 문제/아이디어가 없습니다.")
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
# 메인
###############################################################################
def main():
    st.title("studyhelper (자동 분석 + GPT 채팅 + 커뮤니티)")

    # 간단 안내
    st.write("""
    - **파일 업로드**: 업로드하는 즉시 문서 내용 분석 + GPT가 자동 요약/질문/퀴즈 제시
    - **GPT 채팅**: 문서 관련 추가 질문이나 일반 대화 가능
    - **커뮤니티**: 다른 사용자와 문제/아이디어 공유
    """)

    # 파일 업로드 (자동 분석)
    uploaded_file = st.file_uploader("파일을 업로드하세요 (docx, pdf, pptx)", type=["docx","pdf","pptx"])
    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.md5(file_bytes).hexdigest()
        # 이전에 처리한 파일과 다르면 새로 분석
        if ("current_file_hash" not in st.session_state or 
            st.session_state.current_file_hash != file_hash):
            st.session_state.current_file_hash = file_hash
            # chat_history 초기화 혹은 유지 여부 결정
            # 여기서는 유지하지만, 완전히 새로 시작하려면 chat_history = []로 세팅
            analyze_file(file_bytes, uploaded_file.name)
            st.success("문서 분석 완료! 아래 GPT 채팅 영역에서 대화를 이어가 보세요.")

    # GPT 채팅 인터페이스
    st.markdown("---")
    st.header("GPT 채팅")
    chat_interface()

    # 커뮤니티
    st.markdown("---")
    community_tab()

    st.write("---")
    st.info("GPT 응답은 실제 정보를 보장하지 않을 수 있습니다. 반드시 중요 내용은 검증하세요.")

if __name__ == "__main__":
    main()
