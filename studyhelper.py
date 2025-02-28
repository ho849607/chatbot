import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import openai
from pathlib import Path
import docx2txt
import pdfplumber
from pptx import Presentation
import random
import subprocess

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords

###############################################################################
# NLTK 설정 (불용어 자동 다운로드)
###############################################################################
nltk_data_dir = "/tmp/nltk_data"
os.makedirs(nltk_data_dir, exist_ok=True)
nltk.data.path.append(nltk_data_dir)

try:
    stopwords.words("english")
except LookupError:
    nltk.download("stopwords", download_dir=nltk_data_dir)

korean_stopwords = ["이", "그", "저", "것", "수", "등", "들", "및", "더"]
english_stopwords = set(stopwords.words("english"))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# 환경 변수 & OpenAI API 설정
###############################################################################
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("🚨 OpenAI API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# OpenAI API 마이그레이션 (예전 버전 호환 - 필요 시)
###############################################################################
def migrate_openai_api():
    try:
        subprocess.run(["openai", "migrate"], capture_output=True, text=True, check=True)
        st.info("OpenAI API 마이그레이션 완료. 앱 재시작 후 사용하세요.")
        st.stop()
    except Exception as e:
        st.error(f"API 마이그레이션 실패: {e}")
        st.stop()

###############################################################################
# GPT API 호출 함수 (문서 분석 & 질문 & 맞춤법 수정)
###############################################################################
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    """GPT 모델과 대화하는 함수"""
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
        st.error(f"🚨 OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 문서 분석 함수 (PDF, PPTX, DOCX)
###############################################################################
def parse_docx(file_bytes):
    """DOCX 파일에서 텍스트 추출"""
    try:
        return docx2txt.process(BytesIO(file_bytes))
    except Exception:
        return "📄 DOCX 파일 분석 오류"

def parse_pdf(file_bytes):
    """PDF 파일에서 텍스트 추출"""
    text_list = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text_list.append(page.extract_text() or "")
        return "\n".join(text_list)
    except Exception:
        return "📄 PDF 파일 분석 오류"

def parse_ppt(file_bytes):
    """PPTX 파일에서 텍스트 추출"""
    text_list = []
    try:
        prs = Presentation(BytesIO(file_bytes))
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text_list.append(shape.text)
        return "\n".join(text_list)
    except Exception:
        return "📄 PPTX 파일 분석 오류"

def analyze_file(fileinfo):
    """업로드된 파일을 분석"""
    ext = fileinfo["ext"]
    data = fileinfo["data"]
    if ext == "docx":
        return parse_docx(data)
    elif ext == "pdf":
        return parse_pdf(data)
    elif ext == "pptx":
        return parse_ppt(data)
    else:
        return "❌ 지원하지 않는 파일 형식입니다."

###############################################################################
# GPT 문서 분석 & 질문 & 수정 기능
###############################################################################
def gpt_document_review(text):
    """GPT가 문서를 분석하여 요약, 질문 및 수정"""
    # 1. 문서 요약 요청
    summary_prompt = [
        {"role": "system", "content": "주어진 문서를 요약하고 주요 내용을 정리하세요."},
        {"role": "user", "content": text}
    ]
    summary = ask_gpt(summary_prompt)

    # 2. 사용자에게 질문 던지기
    question_prompt = [
        {"role": "system", "content": "주어진 문서를 검토하고, 사용자가 수정하거나 고려해야 할 질문을 3가지 제시하세요."},
        {"role": "user", "content": text}
    ]
    questions = ask_gpt(question_prompt)

    # 3. 맞춤법 및 문장 수정 요청
    correction_prompt = [
        {"role": "system", "content": "이 문서에서 맞춤법과 문법 오류를 수정하고, 수정한 부분을 강조하세요."},
        {"role": "user", "content": text}
    ]
    corrections = ask_gpt(correction_prompt)

    return summary, questions, corrections

###############################################################################
# GPT 채팅 + 문서 분석 탭
###############################################################################
def gpt_chat_tab():
    # 사용법 안내 부분 수정: 상단에 "사용법"만 표시하고, 아래에 부연 설명을 추가합니다.
    st.info("""
**사용법**

1️⃣ PDF/PPTX/DOCX 파일을 업로드하면 AI가 자동으로 분석합니다.
2️⃣ 문서의 요약, 수정할 부분, 그리고 개선을 위한 질문을 제공합니다.
3️⃣ GPT가 맞춤법과 문법을 수정하여 개선된 문서를 제시합니다.
    """)

    uploaded_files = st.file_uploader(
        "📎 문서를 업로드하세요 (PDF/PPTX/DOCX 지원)",
        type=["pdf", "pptx", "docx"],
        accept_multiple_files=False
    )

    if uploaded_files:
        file_bytes = uploaded_files.getvalue()
        fileinfo = {
            "name": uploaded_files.name,
            "ext": uploaded_files.name.split(".")[-1].lower(),
            "data": file_bytes
        }
        with st.spinner(f"📖 {fileinfo['name']} 분석 중..."):
            document_text = analyze_file(fileinfo)
            # GPT 문서 분석 실행
            summary, questions, corrections = gpt_document_review(document_text)
            st.subheader("📌 문서 요약")
            st.write(summary)
            st.subheader("💡 고려해야 할 질문")
            st.write(questions)
            st.subheader("✍️ 맞춤법 및 문장 수정")
            st.write(corrections)

###############################################################################
# 커뮤니티 탭
###############################################################################
def community_tab():
    st.header("🌍 커뮤니티 (문서 공유 및 토론)")
    st.info("""
    **[커뮤니티 사용법]**
    1. 상단의 검색창에서 제목 또는 내용을 입력하여 기존 게시글을 검색할 수 있습니다.
    2. '새로운 게시글 작성' 영역에서 제목, 내용 및 파일(PDF/PPTX/DOCX 지원)을 첨부하여 게시글을 등록할 수 있습니다.
    3. 게시글 상세보기 영역에서 댓글을 작성할 수 있으며, 댓글 작성 시 임의의 '유저_숫자'가 부여됩니다.
    """)
    
    search_query = st.text_input("🔍 검색 (제목 또는 내용 입력)")

    if "community_posts" not in st.session_state:
        st.session_state.community_posts = []

    st.subheader("📤 새로운 게시글 작성")
    title = st.text_input("제목")
    content = st.text_area("내용")
    uploaded_files = st.file_uploader("📎 파일 업로드", type=["pdf", "pptx", "docx"], accept_multiple_files=True)

    if st.button("✅ 게시글 등록"):
        if title.strip() and content.strip():
            files_info = []
            if uploaded_files:
                for uf in uploaded_files:
                    file_bytes = uf.getvalue()
                    ext = uf.name.split(".")[-1].lower()
                    files_info.append({"name": uf.name, "ext": ext, "data": file_bytes})
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
    st.title("📚 ThinHelper - 생각도우미")

    st.markdown("""
    **이 앱은 파일 업로드와 GPT 기반 문서 분석 기능을 제공합니다.**
    
    - **GPT 문서 분석 탭:**  
      1. PDF/PPTX/DOCX 파일을 업로드하면 AI가 자동으로 문서를 분석합니다.  
      2. 문서 요약, 수정할 부분, 그리고 개선을 위한 질문을 제공합니다.  
      3. GPT가 맞춤법과 문법을 수정하여 개선된 문서를 제시합니다.
    - **커뮤니티 탭:**  
      게시글 등록, 검색, 댓글 기능을 통해 문서를 공유하고 토론합니다.
    """)

    tab = st.sidebar.radio("🔎 메뉴 선택", ("GPT 문서 분석", "커뮤니티"))
    if tab == "GPT 문서 분석":
        gpt_chat_tab()
    else:
        community_tab()

if __name__ == "__main__":
    main()

###############################################################################
# 저작권 주의 문구 (Copyright Notice)
###############################################################################
"""
파일 업로드 시 저작권에 유의해야 하며, 우리는 이 코드의 사용 또는 업로드된 파일로 인해 발생하는 어떠한 손해, 오용, 저작권 침해 문제에 대해 책임을 지지 않습니다.

This source code is protected by copyright law. Unauthorized reproduction, distribution, modification, or commercial use is prohibited. 
It may only be used for personal, non-commercial purposes, and the source must be clearly credited upon use. 
Users must be mindful of copyright when uploading files, and we are not responsible for any damages, misuse, or copyright infringement issues arising from the use of this code or uploaded files.
"""
