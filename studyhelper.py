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
# NLTK 설정 (불용어, punkt, averaged_perceptron_tagger 자동 다운로드)
###############################################################################
nltk_data_dir = "/tmp/nltk_data"
os.makedirs(nltk_data_dir, exist_ok=True)
nltk.data.path.append(nltk_data_dir)

try:
    stopwords.words("english")
except LookupError:
    nltk.download("stopwords", download_dir=nltk_data_dir)

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', download_dir=nltk_data_dir)

try:
    nltk.data.find('taggers/averaged_perceptron_tagger')
except LookupError:
    nltk.download('averaged_perceptron_tagger', download_dir=nltk_data_dir)

korean_stopwords = ["이", "그", "저", "것", "수", "등", "들", "및", "더"]
english_stopwords = set(stopwords.words("english"))
final_stopwords = english_stopwords.union(set(korean_stopwords))

###############################################################################
# 환경 변수 & OpenAI API 설정
###############################################################################
if not os.getenv("OPENAI_API_KEY"):
    dotenv_path = Path(".env")
    load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("🚨 OpenAI API 키가 설정되지 않았습니다. 로컬에서는 .env 파일을, Streamlit Cloud에서는 'Settings'에서 환경 변수를 추가하세요.")
    st.stop()

openai.api_key = OPENAI_API_KEY

###############################################################################
# GPT API 호출 함수
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
        st.error(f"🚨 OpenAI API 호출 에러: {e}")
        return ""

###############################################################################
# 문서 분석 함수 (PDF, PPTX, DOCX)
###############################################################################
def parse_docx(file_bytes):
    try:
        return docx2txt.process(BytesIO(file_bytes))
    except Exception:
        return "📄 DOCX 파일 분석 오류"

def parse_pdf(file_bytes):
    text_list = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text_list.append(page.extract_text() or "")
        return "\n".join(text_list)
    except Exception:
        return "📄 PDF 파일 분석 오류"

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
        return "📄 PPTX 파일 분석 오류"

def analyze_file(fileinfo):
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
# 중요 단어 추출 함수
###############################################################################
def extract_important_words(text, top_n=10):
    words = word_tokenize(text.lower())
    words = [word for word in words if word.isalnum() and word not in final_stopwords]
    tagged = nltk.pos_tag(words)
    nouns = [word for word, pos in tagged if pos.startswith('N')]
    freq_dist = nltk.FreqDist(nouns)
    return [word for word, _ in freq_dist.most_common(top_n)]

###############################################################################
# GPT 문서 분석 함수
###############################################################################
def gpt_document_review(text):
    summary_prompt = [
        {"role": "system", "content": "주어진 문서를 요약하고 주요 내용을 정리하세요."},
        {"role": "user", "content": text}
    ]
    summary = ask_gpt(summary_prompt)

    question_prompt = [
        {"role": "system", "content": "주어진 문서를 검토하고, 사용자가 수정하거나 고려해야 할 질문을 3가지 제시하세요."},
        {"role": "user", "content": text}
    ]
    questions = ask_gpt(question_prompt)

    correction_prompt = [
        {"role": "system", "content": "이 문서에서 맞춤법과 문법 오류를 수정하고, 수정한 부분을 강조하세요."},
        {"role": "user", "content": text}
    ]
    corrections = ask_gpt(correction_prompt)

    return summary, questions, corrections

###############################################################################
# 대화형 채팅 기능 (파일 업로드 시 자동 표시)
###############################################################################
def show_interactive_chat(document_text):
    if 'conversation' not in st.session_state:
        st.session_state.conversation = []
    
    st.info("문서에 대해 질문하세요. GPT가 문서 내용을 바탕으로 답변하며, 필요 시 질문을 던지고 근거를 제공합니다.")
    
    # 대화 기록 표시
    for msg in st.session_state.conversation:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # 사용자 입력 처리
    user_input = st.chat_input("여기에 메시지를 입력하세요...")
    if user_input:
        st.session_state.conversation.append({"role": "user", "content": user_input})
        system_prompt = {
            "role": "system",
            "content": "You are an assistant helping with document analysis. Answer the user's questions based on the provided document. Include direct quotes from the document as evidence when possible. If the user's question is unclear, ask a clarifying question."
        }
        messages = [system_prompt, {"role": "user", "content": f"Here is the document: {document_text}"}] + st.session_state.conversation
        response = ask_gpt(messages)
        st.session_state.conversation.append({"role": "assistant", "content": response})
    
    # 대화 초기화 버튼
    if st.button("대화 초기화"):
        st.session_state.conversation = []
        st.experimental_rerun()

###############################################################################
# 메인 실행
###############################################################################
def main():
    st.title("📚 ThinHelper - 생각도우미")

    st.markdown("""
    **이 앱은 파일 업로드와 GPT 기반 문서 분석 기능을 제공합니다.**
    
    - **파일 업로드:** PDF, PPTX, DOCX 파일을 업로드하세요.
    - **문서 분석:** 문서 요약, 중요 단어, 수정 제안, 질문을 제공합니다.
    - **대화형 채팅:** 파일 업로드 시 자동으로 채팅창이 나타나며, 문서에 대해 질문하고 GPT의 답변을 받습니다.
    - **커뮤니티:** 게시글 등록, 검색, 댓글 기능을 통해 문서를 공유하고 토론합니다.
    """)

    # 세션 상태 초기화
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'document_text' not in st.session_state:
        st.session_state.document_text = None

    # 파일 업로드
    uploaded_file = st.file_uploader("📎 문서를 업로드하세요 (PDF/PPTX/DOCX 지원)", type=["pdf", "pptx", "docx"])

    if uploaded_file:
        if st.session_state.uploaded_file != uploaded_file:
            st.session_state.uploaded_file = uploaded_file
            file_bytes = uploaded_file.getvalue()
            fileinfo = {
                "name": uploaded_file.name,
                "ext": uploaded_file.name.split(".")[-1].lower(),
                "data": file_bytes
            }
            with st.spinner(f"📖 {fileinfo['name']} 분석 중..."):
                st.session_state.document_text = analyze_file(fileinfo)

    # 탭 선택
    tab = st.sidebar.radio("🔎 메뉴 선택", ("GPT 문서 분석", "커뮤니티"))

    if tab == "GPT 문서 분석":
        if st.session_state.document_text:
            # 문서 분석 결과 표시
            summary, questions, corrections = gpt_document_review(st.session_state.document_text)
            important_words = extract_important_words(st.session_state.document_text)
            st.subheader("📌 중요 단어")
            st.write(", ".join(important_words))
            st.subheader("📌 문서 요약")
            st.write(summary)
            st.subheader("💡 고려해야 할 질문")
            st.write(questions)
            st.subheader("✍️ 맞춤법 및 문장 수정")
            st.write(corrections)
            
            # 파일 업로드 시 자동으로 대화형 채팅창 표시
            st.subheader("💬 대화형 채팅")
            show_interactive_chat(st.session_state.document_text)
        else:
            st.info("먼저 문서를 업로드하세요.")
    else:
        community_tab()

if __name__ == "__main__":
    main()

###############################################################################
# 커뮤니티 탭 (기존 코드 유지)
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
# 저작권 주의 문구 (Copyright Notice)
###############################################################################
"""
파일 업로드 시 저작권에 유의해야 하며, 우리는 이 코드의 사용 또는 업로드된 파일로 인해 발생하는 어떠한 손해, 오용, 저작권 침해 문제에 대해 책임을 지지 않습니다.

This source code is protected by copyright law. Unauthorized reproduction, distribution, modification, or commercial use is prohibited. 
It may only be used for personal, non-commercial purposes, and the source must be clearly credited upon use. 
Users must be mindful of copyright when uploading files, and we are not responsible for any damages, misuse, or copyright infringement issues arising from the use of this code or uploaded files.
"""
