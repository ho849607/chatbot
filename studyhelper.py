import streamlit as st
import pdfplumber
from pptx import Presentation
import docx2txt
from io import BytesIO

# 파일 분석 함수
def analyze_file(file):
    file_ext = file.name.split(".")[-1].lower()
    file_bytes = file.getvalue()

    with st.spinner(f"📖 {file.name} 분석 중..."):  # 분석 중 동그라미 표시
        if file_ext == "pdf":
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                total_pages = len(pdf.pages)
                text = ""
                for i, page in enumerate(pdf.pages):
                    st.write(f"📄 페이지 {i+1}/{total_pages} 분석 중...")  # 페이지별 진행 상황
                    text += page.extract_text() or ""
                return text
        elif file_ext == "pptx":
            prs = Presentation(BytesIO(file_bytes))
            total_slides = len(prs.slides)
            text = ""
            for i, slide in enumerate(prs.slides):
                st.write(f"📄 슬라이드 {i+1}/{total_slides} 분석 중...")  # 슬라이드별 진행 상황
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        text += shape.text + "\n"
            return text
        elif file_ext == "docx":
            text = docx2txt.process(BytesIO(file_bytes))
            st.write("📄 DOCX 파일 분석 중...")  # DOCX 진행 상황
            return text
        else:
            return "❌ 지원하지 않는 파일 형식입니다."

# 메인 앱
st.title("파일 분석기")
uploaded_file = st.file_uploader("파일 업로드 (PDF/PPTX/DOCX)", type=["pdf", "pptx", "docx"])

if uploaded_file:
    document_text = analyze_file(uploaded_file)
    st.subheader("📜 파일 내용 미리보기")
    st.write(document_text[:200])  # 첫 200자 미리보기
    st.subheader("📌 전체 내용")
    st.write(document_text)  # 전체 내용 표시 (필요 시 생략 가능)
