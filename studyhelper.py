import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
from pathlib import Path
import docx2txt
import pdfplumber
from pptx import Presentation
import nltk
from nltk.corpus import stopwords
import google.generativeai as genai
import PIL.Image
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# 환경변수 로드
dotenv_path = ".env"
load_dotenv(dotenv_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# 캐싱을 이용한 성능 개선
@st.cache_data(show_spinner=False)
def parse_docx(file_bytes):
    import docx2txt
    return docx2txt.process(file_bytes)

@st.cache_data(show_spinner=False)
def parse_pdf(file_bytes):
    import pdfplumber
    with pdfplumber.open(file_bytes) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages)

@st.cache_data(show_spinner=False)
def parse_ppt(file_bytes):
    from pptx import Presentation
    prs = Presentation(file_bytes)
    return "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame)

@st.cache_data(show_spinner=False)
def analyze_image(file_bytes):
    image = PIL.Image.open(file_bytes)
    image.thumbnail((512, 512))
    response = genai.GenerativeModel('gemini-1.5-flash').generate_content(
        ["Describe this image.", image],
        generation_config={"temperature": 0.2}
    )
    return response.text

def analyze_file(file):
    ext = file.name.split('.')[-1].lower()
    file_bytes = file.getvalue()
    if ext == "docx":
        return parse_docx(BytesIO(file_bytes))
    elif ext == "pdf":
        return parse_pdf(BytesIO(file_bytes))
    elif ext == "pptx":
        return parse_ppt(BytesIO(file_bytes))
    elif ext in ["png", "jpg", "jpeg"]:
        return analyze_image(BytesIO(file_bytes))
    return "❌ 지원하지 않는 파일 형식입니다."

@st.cache_data(show_spinner=False)
def gemini_chat(prompt):
    response = genai.GenerativeModel('gemini-1.5-flash').generate_content(
        prompt,
        generation_config={"temperature": 0.2}
    )
    return response.text.strip()

# 파일 처리
@st.cache_data(show_spinner=False)
def merge_documents(file_list):
    def process_file(file):
        return analyze_file({
            "name": file.name,
            "ext": file.name.split(".")[-1].lower(),
            "data": file.getvalue()
        })

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(process_file, file_list)
    return "\n\n".join(results)

# Streamlit UI 구성
def main():
    st.title("📚 Thinkhelper")

    st.markdown("""
    **Thinkhelper**는 AI 기반 파일(문서 및 이미지) 분석과 자유로운 대화를 지원합니다.

    **사용법:**
    - 파일을 업로드하면 문서 및 이미지 분석 결과를 바로 볼 수 있습니다.
    - 파일 없이도 자유롭게 질문하고 답변을 받을 수 있습니다.
    - 커뮤니티 탭에서 익명으로 게시글 및 댓글을 통해 협업과 토론이 가능합니다.
    """)

    tab = st.sidebar.radio("🔎 메뉴 선택", ("파일 분석 & GPT 채팅", "커뮤니티"))

    if tab == "파일 분석 & GPT 채팅":
        st.info("파일을 업로드하거나 직접 질문을 입력하여 AI와 대화하세요.")
        uploaded_files = st.file_uploader(
            "📎 파일 업로드 (PDF, PPTX, DOCX, 이미지)",
            type=["pdf", "pptx", "docx", "png", "jpg", "jpeg"],
            accept_multiple_files=True
        )

        if uploaded_files:
            with st.spinner("파일 분석 중..."):
                analysis_result = merge_documents(uploaded_files)
                st.session_state.analysis_result = analysis_result

            st.subheader("📌 분석 결과")
            st.write(st.session_state.analysis_result)

        st.subheader("💬 GPT와 대화하기")
        user_input = st.text_input("질문 입력")

        if st.button("전송"):
            if user_input:
                prompt_context = st.session_state.get('analysis_result', '')
                prompt = f"파일 내용: {prompt_context}\n사용자 질문: {user_input}"
                response = gemini_chat(prompt)
                st.write(f"AI: {response}")

    elif tab == "커뮤니티":
        st.info("커뮤니티 기능은 익명으로 게시글과 댓글을 작성할 수 있습니다.")
        # 여기에 커뮤니티 기능 추가 구현 가능

if __name__ == "__main__":
    main()

st.markdown("""
---
**저작권 주의 문구**
- 본 코드와 서비스 사용 시 발생하는 저작권 문제에 대한 책임은 사용자에게 있습니다.
- 개인적, 비상업적 용도로만 사용할 수 있습니다.
""")
