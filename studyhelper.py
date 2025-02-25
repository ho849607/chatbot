import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import hashlib
import base64
import random

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import docx2txt
import pdfplumber
from pptx import Presentation

###############################################################################
# NLTK 설정
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
# 환경 변수 로드 & OpenAI API 키
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# GPT 함수
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    try:
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
                text_list.append(page.extract_text() or "")
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
    return "[이미지 파일] OCR 분석 기능 추가 가능"

def analyze_file(fileinfo):
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
# GPT 채팅 탭 (DeepThink 포함)
###############################################################################
def gpt_chat_tab():
    st.header("📌 GPT 채팅")
    # 사용법 안내
    st.info(
        """
        **사용법 안내:**
        1. 아래의 파일 업로드 영역에서 PDF, PPTX, DOCX, JPG, PNG 파일을 선택하여 업로드하면 파일 내용이 자동으로 분석됩니다.
        2. 분석이 완료되면, 채팅 기록에 분석 결과가 표시됩니다.
        3. 하단의 메시지 입력란에 질문을 작성하면 GPT가 응답을 제공합니다.
        """
    )

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # 기존 대화 내용 출력 (메시지 키를 "content"로 사용)
    for msg in st.session_state.chat_messages:
        role, content = msg["role"], msg["content"]
        with st.chat_message(role):
            st.write(content)

    uploaded_files = st.file_uploader(
        "파일을 업로드하세요 (PDF/PPTX/DOCX/이미지 지원)",
        type=["pdf", "pptx", "docx", "jpg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for uf in uploaded_files:
            file_bytes = uf.getvalue()
            fileinfo = {"name": uf.name, "ext": uf.name.split(".")[-1].lower(), "data": file_bytes}
            with st.spinner(f"📖 {fileinfo['name']} 분석 중..."):
                analysis_result = analyze_file(fileinfo)
            st.session_state.chat_messages.append({"role": "system", "content": f"📄 {fileinfo['name']} 분석 완료."})
            st.session_state.chat_messages.append({"role": "assistant", "content": analysis_result})

    user_msg = st.chat_input("메시지를 입력하세요:")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.write(user_msg)

        with st.spinner("GPT 응답 중..."):
            gpt_response = ask_gpt(st.session_state.chat_messages)
        
        st.session_state.chat_messages.append({"role": "assistant", "content": gpt_response})
        with st.chat_message("assistant"):
            st.write(gpt_response)

###############################################################################
# 커뮤니티 탭 (검색 + 유저 댓글 추가)
###############################################################################
def community_tab():
    st.header("🌍 커뮤니티 (문서 공유 및 토론)")
    # 사용법 안내
    st.info(
        """
        **사용법 안내:**
        1. 상단의 검색창에서 제목 또는 내용을 입력하여 기존 게시글을 검색할 수 있습니다.
        2. '새로운 게시글 작성' 영역에서 제목, 내용 및 파일(PDF/PPTX/DOCX/이미지)을 첨부하여 게시글을 등록할 수 있습니다.
        3. 게시글 상세보기 영역에서 댓글을 작성할 수 있으며, 댓글 작성 시 임의의 '유저_숫자'가 부여됩니다.
        """
    )
    
    search_query = st.text_input("🔍 검색 (제목 또는 내용 입력)")

    if "community_posts" not in st.session_state:
        st.session_state.community_posts = []

    st.subheader("📤 새로운 게시글 작성")
    title = st.text_input("제목")
    content = st.text_area("내용")

    uploaded_files = st.file_uploader("📎 파일 업로드", type=["pdf", "pptx", "docx", "jpg", "png"], accept_multiple_files=True)

    if st.button("게시글 등록"):
        if title.strip() and content.strip():
            files_info = (
                [{"name": uf.name, "ext": uf.name.split(".")[-1].lower(), "data": uf.getvalue()} for uf in uploaded_files]
                if uploaded_files else []
            )
            new_post = {"title": title, "content": content, "files": files_info, "comments": []}
            st.session_state.community_posts.append(new_post)
            st.success("✅ 게시글이 등록되었습니다!")

    st.subheader("📜 게시글 목록")
    for idx, post in enumerate(st.session_state.community_posts):
        if search_query.lower() in post["title"].lower() or search_query.lower() in post["content"].lower():
            with st.expander(f"{idx+1}. {post['title']}"):
                st.write(post["content"])
                comment = st.text_input(f"💬 댓글 작성 (작성자: 유저_{random.randint(100,999)})", key=f"comment_{idx}")
                if st.button("댓글 등록", key=f"comment_btn_{idx}"):
                    post["comments"].append(f"📝 유저_{random.randint(100,999)}: {comment}")
                for c in post["comments"]:
                    st.write(c)

###############################################################################
# 메인 실행
###############################################################################
def main():
    st.title("📚 StudyHelper")
    
    # 전체 사용법 안내 (메인 화면 상단)
    st.markdown(
        """
        **StudyHelper 사용법:**
        - **GPT 채팅:** 파일 업로드를 통해 문서를 분석하고, GPT와 대화를 나눌 수 있습니다.
        - **커뮤니티:** 게시글을 작성하고, 문서를 공유하며, 댓글로 의견을 나눌 수 있습니다.
        좌측 사이드바에서 원하는 기능을 선택하여 사용해 보세요.
        """
    )
    
    tab = st.sidebar.radio("🔎 메뉴 선택", ("GPT 채팅", "커뮤니티"))
    if tab == "GPT 채팅":
        gpt_chat_tab()
    else:
        community_tab()

if __name__ == "__main__":
    main()
