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

# ... (중략) ...

# API 키 로드
dotenv_path = Path(".env")
load_dotenv(dotenv_path=dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("서버에 OPENAI_API_KEY가 설정되지 않았습니다.")
    st.stop()

openai.api_key = OPENAI_API_KEY

# GPT 사용 함수
def ask_gpt(messages, model_name="gpt-4", temperature=0.7):
    try:
        return openai.ChatCompletion.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
        ).choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API 호출 에러: {e}")
        return ""

# ... (이하 생략, 파일 파싱, 탭 구성, main() 함수 등) ...
