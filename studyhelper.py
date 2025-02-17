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

# PPTX 모듈 설치 확인
try:
    from pptx import Presentation
    PPTX_ENABLED = True
except ImportError:
    st.error("pptx 모듈이 설치되어 있지 않습니다. 'python-pptx' 패키지를 설치해 주세요.")
    st.stop()

# 구글 OAuth 라이브러리
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests

###############################################################################
# NLTK 설정 (생략)
###############################################################################
# ... (기존 NLTK 다운로드, stopwords 설정 코드) ...

###############################################################################
# .env 로드 및 OpenAI API 키 설정 (생략)
###############################################################################
# ... (기존 load_dotenv, OPENAI_API_KEY 설정 코드) ...

###############################################################################
# 구글 OAuth 설정
###############################################################################
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["openid", "email", "profile"]
REDIRECT_URI = "http://localhost:8501"

if "user_email" not in st.session_state:
    st.session_state["user_email"] = None

def create_flow():
    flow = Flow.from_client_secrets_file(
        client_secrets_file=CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return flow

def google_login_flow():
    """
    자동 리디렉션으로 Google 로그인 페이지로 이동
    """
    flow = create_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    
    # 자동 리디렉션 HTML
    redirect_html = f"""
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url={auth_url}" />
      </head>
      <body>
        <p>Redirecting to Google login...</p>
      </body>
    </html>
    """
    st.components.v1.html(redirect_html, height=100)

###############################################################################
# GPT 함수, DOCX 분석, 채팅, 커뮤니티 등 (생략)
###############################################################################
# ... (기존 함수들: ask_gpt, docx_to_text, docx_advanced_processing, chat_interface, community_tab) ...

###############################################################################
# 메인 함수
###############################################################################
def main():
    st.title("studyhelper")
    st.write("이 앱은 구글 로그인으로 인증 후, GPT 채팅 / DOCS 분석 / 커뮤니티 기능을 제공합니다.")
    st.warning("저작권에 유의하여 파일을 업로드하세요. GPT는 부정확할 수 있으니 중요한 정보는 검증하세요.")
    
    # (A) 구글 로그인 여부 체크
    if not st.session_state.get("user_email"):
        st.info("구글 로그인을 먼저 진행해 주세요.")
        google_login_flow()
        return
    else:
        st.success(f"로그인됨: {st.session_state['user_email']}")
        if st.button("로그아웃"):
            st.session_state["user_email"] = None
            st.experimental_rerun()
    
    # (B) 로그인 후 메뉴 표시
    tab = st.sidebar.radio("메뉴 선택", ("GPT 채팅", "DOCS 분석", "커뮤니티"))
    
    if tab == "GPT 채팅":
        st.subheader("GPT 채팅")
        chat_interface()
    elif tab == "DOCS 분석":
        st.subheader("DOCS 분석 (DOCX 고급 분석 예시)")
        # ... (DOCX 업로드 및 분석 로직) ...
    elif tab == "커뮤니티":
        st.subheader("커뮤니티")
        community_tab()
    
    st.write("---")

if __name__ == "__main__":
    main()
