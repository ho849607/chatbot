import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import hashlib
import base64
import random
import subprocess

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import docx2txt
import pdfplumber
from pptx import Presentation

###############################################################################
# NLTK 설정 (필요 시)
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

korean_stopwords = ["이", "그", "저", "것", "수", "등", "들", "및", "더"]
english_stopwords = set(stopwords.words("english"))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# 환경 변수 로드 & OpenAI API 키 설정
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # .env 파일에서 KEY를 가져옴
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다.")
    st.stop()

# 최신 OpenAI 라이브러리 방식 - 전역으로 API 키 설정
openai.api_key = OPENAI_API_KEY

###############################################################################
# (선택) OpenAI 구버전 마이그레이션 함수
###############################################################################
def migrate_openai_api():
    """
    'no longer supported' 오류 발생 시 'openai migrate' 명령을 시도해 보는 함수.
    보통 openai>=1.0.0 환경에서는 사용 안 함.
    """
    try:
        subprocess.run(["openai", "migrate"], capture_output=True, text=True, check=True)
        st.info("OpenAI API 마이그레이션 완료. 앱을 재시작해 주세요.")
        st.stop()
    except Exception as e:
        st.error(f"API 마이그레이션 실패: {e}\n'openai migrate' 명령을 터미널에서 직접 실행해 보세요.")
        st.stop()

###############################################################################
# GPT 함수 (ChatCompletion)
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    """
    OpenAI ChatCompletion API를 통해 GPT 모델에게 메시지를 전달하고 응답을 받는 함수.
    """
    try:
        resp = openai.ChatCompletion.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        error_message = str(e)
        if "no longer supported" in error_message:
            migrate_openai_api()
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 파일 분석 로직 (PDF, PPTX, DOCX, 이미지)
###############################################################################
def parse_docx(file_bytes):
    try:
        return docx2txt.process(BytesIO(file_bytes))
    except Exception:
        return "DOCX 파일 분석 오류"

def parse_pdf(file_bytes):
    text_list = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                text_list.append(text)
        return "\n".join(text_list)
    except Exception:
        return "PDF 파일 분석 오류"

def parse_ppt(file_bytes):
    text_list = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text_list.append(shape.text)
        return "\n".join(text_list)
    except Exception:
        return "PPTX 파일 분석 오류"

def parse_image(file_bytes):
    """이미지 파일에 대한 OCR 분석 로직 (현재는 단순 안내만 반환)"""
    return "[이미지 파일] OCR 분석 기능 추가 가능"

def analyze_file(fileinfo):
    """
    업로드된 파일의 확장자를 확인한 뒤,
    해당 파일에 맞는 파싱 함수를 호출해 텍스트를 추출.
    """
    ext = fileinfo["ext"]
    data = fileinfo["data"]

    if ext == "docx":
        return parse_docx(data)
    elif ext == "pdf":
        return parse_pdf(data)
    elif ext == "pptx":
        return parse_ppt(data)
    elif ext in ["jpg", "jpeg", "png"]:
        return parse_image(data)
    else:
        return "지원하지 않는 파일 형식입니다."

###############################################################################
# GPT 채팅 탭
###############################################################################
def gpt_chat_tab():
    st.header("📌 GPT 채팅")
    st.info("""
    **[GPT 채팅 사용법]**
    1. 아래의 파일 업로드 영역에서 PDF/PPTX/DOCX/이미지(JPG/PNG) 파일을 선택하면 자동으로 분석됩니다.
    2. 분석 결과는 채팅 형식으로 표시됩니다.
    3. 메시지 입력란에 질문을 작성하면 GPT가 답변을 제공합니다.
    """)

    # 채팅 메시지 세션 초기화
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # 기존 메시지 출력
    for msg in st.session_state.chat_messages:
        role, content = msg["role"], msg["content"]
        with st.chat_message(role):
            st.write(content)

    # 파일 업로드 후 분석
    uploaded_files = st.file_uploader(
        "파일을 업로드하세요 (PDF/PPTX/DOCX/JPG/PNG)",
        type=["pdf", "pptx", "docx", "jpg", "png"],
        accept_multiple_files=True
    )
    if uploaded_files:
        for uf in uploaded_files:
            file_bytes = uf.getvalue()
            fileinfo = {
                "name": uf.name,
                "ext": uf.name.split(".")[-1].lower(),
                "data": file_bytes
            }
            with st.spinner(f"📖 {fileinfo['name']} 분석 중..."):
                analysis_result = analyze_file(fileinfo)

            # 분석 결과를 채팅 기록에 추가
            st.session_state.chat_messages.append({"role": "system", "content": f"📄 {fileinfo['name']} 분석 완료."})
            st.session_state.chat_messages.append({"role": "assistant", "content": analysis_result})

    # 사용자 입력
    user_msg = st.chat_input("메시지를 입력하세요:")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.write(user_msg)

        # GPT 응답 호출
        with st.spinner("GPT 응답 중..."):
            gpt_response = ask_gpt(st.session_state.chat_messages)

        st.session_state.chat_messages.append({"role": "assistant", "content": gpt_response})
        with st.chat_message("assistant"):
            st.write(gpt_response)

###############################################################################
# 커뮤니티 탭
###############################################################################
def community_tab():
    st.header("🌍 커뮤니티 (문서 공유 및 토론)")
    st.info("""
    **[커뮤니티 사용법]**
    1. 상단의 검색창에서 제목 또는 내용을 입력하여 기존 게시글을 검색할 수 있습니다.
    2. '새로운 게시글 작성' 영역에서 제목, 내용 및 파일(PDF/PPTX/DOCX/JPG/PNG)을 첨부하여 게시글을 등록할 수 있습니다.
    3. 게시글 상세보기 영역에서 댓글을 작성할 수 있으며, 댓글 작성 시 임의의 '유저_숫자'가 부여됩니다.
    """)

    # 검색 기능
    search_query = st.text_input("🔍 검색 (제목 또는 내용 입력)")

    # 커뮤니티 게시글 초기화
    if "community_posts" not in st.session_state:
        st.session_state.community_posts = []

    st.subheader("📤 새로운 게시글 작성")
    title = st.text_input("제목")
    content = st.text_area("내용")
    uploaded_files = st.file_uploader(
        "📎 파일 업로드 (PDF/PPTX/DOCX/JPG/PNG)",
        type=["pdf", "pptx", "docx", "jpg", "png"],
        accept_multiple_files=True
    )

    # 게시글 등록
    if st.button("게시글 등록"):
        if title.strip() and content.strip():
            files_info = [
                {
                    "name": uf.name,
                    "ext": uf.name.split(".")[-1].lower(),
                    "data": uf.getvalue()
                }
                for uf in uploaded_files
            ] if uploaded_files else []
            new_post = {
                "title": title,
                "content": content,
                "files": files_info,
                "comments": []
            }
            st.session_state.community_posts.append(new_post)
            st.success("✅ 게시글이 등록되었습니다!")

    st.subheader("📜 게시글 목록")
    for idx, post in enumerate(st.session_state.community_posts):
        # 검색 조건
        if search_query.lower() in post["title"].lower() or search_query.lower() in post["content"].lower():
            with st.expander(f"{idx+1}. {post['title']}"):
                st.write(post["content"])

                # 댓글 작성
                comment_key = f"comment_box_{idx}"
                comment_btn_key = f"comment_btn_{idx}"
                comment = st.text_input(
                    f"💬 댓글 작성 (작성자: 유저_{random.randint(100,999)})",
                    key=comment_key
                )
                if st.button("댓글 등록", key=comment_btn_key):
                    post["comments"].append(
                        f"📝 유저_{random.randint(100,999)}: {comment}"
                    )

                # 댓글 목록
                for c in post["comments"]:
                    st.write(c)

###############################################################################
# 메인 실행
###############################################################################
def main():
    st.title("📚 StudyHelper")

    st.markdown("""
    ## StudyHelper 사용법 안내
    - **GPT 채팅:** 파일을 업로드하여 AI가 문서 내용을 분석해주며, 바로 AI와 대화를 나눌 수 있습니다.
    - **커뮤니티:** 자유롭게 게시글을 작성하고, 서로 의견을 주고받으며 토론할 수 있습니다.
    
    **주의사항**
    - **저작권 안내:** 업로드하신 파일 및 콘텐츠는 저작권 보호 대상일 수 있습니다.
      본 플랫폼은 자료에 대한 저작권 책임을 지지 않으므로, 업로드 전 관련 법규를 준수해 주세요.
    - **중요 정보 확인:** ChatGPT의 답변은 참고용이며, 오류나 부정확한 내용이 있을 수 있습니다.
      중요한 결정을 내릴 때는 반드시 추가 확인이 필요합니다.
    """)

    # 사이드바 메뉴
    tab = st.sidebar.radio("🔎 메뉴 선택", ("GPT 채팅", "커뮤니티"))
    if tab == "GPT 채팅":
        gpt_chat_tab()
    else:
        community_tab()

if __name__ == "__main__":
    main()
