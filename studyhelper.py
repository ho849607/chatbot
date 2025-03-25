import os
import streamlit as st
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from authlib.integrations.requests_client import OAuth2Session

import datetime

st.set_page_config(page_title="ThinkHelper - 법률 도우미", layout="centered")

load_dotenv()
LAWGOKR_API_KEY = os.getenv("LAWGOKR_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

REDIRECT_URI = "https://chatbot-3vyflfufldvf7d882bmvgm.streamlit.app"

if "user" not in st.session_state:
    st.session_state["user"] = None
if "favorites" not in st.session_state:
    st.session_state.favorites = {}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


###############################################################################
# Google OAuth 로그인 함수 (code 파라미터 clear 후 st.rerun)
###############################################################################
def google_login():
    oauth = OAuth2Session(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=["openid", "email", "profile"]
    )

    # 쿼리 파라미터 딕셔너리 변환
    query_params = st.query_params.to_dict()

    if "code" not in query_params:
        # 인증 URL 생성 및 로그인 버튼 표시
        auth_url, _ = oauth.create_authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth",
            access_type="offline",
            prompt="consent"
        )
        st.markdown(f"[🔐 구글 로그인]({auth_url})", unsafe_allow_html=True)

    else:
        # code가 있으면 토큰 요청
        code = query_params["code"]
        try:
            token = oauth.fetch_token("https://oauth2.googleapis.com/token", code=code)
            userinfo = oauth.get("https://www.googleapis.com/oauth2/v3/userinfo").json()

            st.session_state["user"] = userinfo
            st.success(f"👋 환영합니다, {userinfo.get('name', '사용자')} 님!")

            # 쿼리 파라미터 초기화 및 앱 재실행
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error("로그인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")


###############################################################################
# 국가법령정보센터 API (법령/판례)
###############################################################################
@st.cache_data(show_spinner=False)
def law_search(keyword: str):
    if not keyword.strip():
        return []
    url = f"https://www.law.go.kr/DRF/lawSearch.do?OC={LAWGOKR_API_KEY}&target=law&type=XML&query={keyword}"
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return [
        {"name": item.findtext("법령명한글"), "id": item.findtext("법령ID")}
        for item in tree.findall("law")
    ]

@st.cache_data(show_spinner=False)
def law_view(law_id: str):
    url = f"https://www.law.go.kr/DRF/lawView.do?OC={LAWGOKR_API_KEY}&target=law&type=XML&ID={law_id}"
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return tree.findtext("조문내용") or "본문 없음"

@st.cache_data(show_spinner=False)
def precedent_search(keyword: str):
    if not keyword.strip():
        return []
    url = f"https://www.law.go.kr/DRF/caseSearch.do?OC={LAWGOKR_API_KEY}&target=case&type=XML&query={keyword}"
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return [
        {"name": item.findtext("판례명"), "id": item.findtext("판례ID")}
        for item in tree.findall("case")
    ]

@st.cache_data(show_spinner=False)
def precedent_view(case_id: str):
    url = f"https://www.law.go.kr/DRF/caseView.do?OC={LAWGOKR_API_KEY}&target=case&type=XML&ID={case_id}"
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    return tree.findtext("판시내용") or "본문 없음"


###############################################################################
# Gemini API
###############################################################################
def call_gemini_api(prompt: str):
    if not GEMINI_API_KEY:
        return "Gemini API Key가 설정되지 않았습니다."
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    url += f"?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        response_data = response.json()
        return (
            response_data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "응답 없음")
        )
    else:
        return f"❌ Gemini API 오류: {response.status_code}"

###############################################################################
# 채팅
###############################################################################
def chat_ui():
    st.subheader("💬 내 사례를 설명해 보세요")
    user_input = st.text_area("사례 입력", key="chat_input")
    if st.button("AI에게 물어보기"):
        if user_input.strip():
            prompt = (
                "다음 사례에 가장 알맞은 법령과 판례를 추천하고 간단히 설명해줘:\n"
                f"{user_input}"
            )
            ai_response = call_gemini_api(prompt)
            st.session_state.chat_history.append(("user", user_input))
            st.session_state.chat_history.append(("bot", ai_response))

    for role, msg in st.session_state.chat_history[::-1]:
        icon = "👤" if role == "user" else "🤖"
        st.markdown(f"{icon} {msg}")

###############################################################################
# 즐겨찾기
###############################################################################
def favorites_ui():
    st.subheader("⭐ 즐겨찾기")
    email = st.session_state["user"].get("email", "")
    favs = st.session_state.favorites.get(email, [])
    if not favs:
        st.info("저장된 즐겨찾기가 없습니다.")
    else:
        for f in favs:
            st.markdown(f"**{f['title']}**")
            st.text_area("내용", f['content'], height=100)

###############################################################################
# 메인
###############################################################################
def main():
    st.title("📚 ThinkHelper")
    google_login()

    if st.session_state["user"] is None:
        st.warning("로그인 후 이용할 수 있습니다.")
        return

    email = st.session_state["user"].get("email", "알수없음")
    st.sidebar.success(f"{email} 님 환영합니다")

    tab = st.sidebar.radio("📂 메뉴", ["AI 사례 추천", "법령 검색", "판례 검색", "즐겨찾기"])

    if tab == "AI 사례 추천":
        chat_ui()

    elif tab == "법령 검색":
        keyword = st.text_input("법령 키워드 입력")
        if st.button("검색 (법령)"):
            results = law_search(keyword)
            if not results:
                st.info("검색 결과가 없습니다.")
            for r in results:
                with st.expander(r["name"]):
                    if st.button("📄 보기", key=f"law_{r['id']}"):
                        content = law_view(r["id"])
                        st.text_area("본문", content, height=250)
                        if st.button("⭐ 저장", key=f"fav_law_{r['id']}"):
                            fav = {"title": r["name"], "content": content}
                            st.session_state.favorites.setdefault(email, []).append(fav)
                            st.success("저장되었습니다.")

    elif tab == "판례 검색":
        keyword = st.text_input("판례 키워드 입력")
        if st.button("검색 (판례)"):
            results = precedent_search(keyword)
            if not results:
                st.info("검색 결과가 없습니다.")
            for r in results:
                with st.expander(r["name"]):
                    if st.button("📄 보기", key=f"case_{r['id']}"):
                        content = precedent_view(r["id"])
                        st.text_area("본문", content, height=250)
                        if st.button("⭐ 저장", key=f"fav_case_{r['id']}"):
                            fav = {"title": r["name"], "content": content}
                            st.session_state.favorites.setdefault(email, []).append(fav)
                            st.success("저장되었습니다.")

    elif tab == "즐겨찾기":
        favorites_ui()


if __name__ == "__main__":
    main()

st.markdown(
    "---\n"
    "**저작권 안내**  \n"
    "- 본 서비스는 [국가법령정보센터](https://www.law.go.kr)의 API를 이용합니다.  \n"
    "- 법령 및 판례 정보는 공공데이터로 제공되며, 최종 판단은 법률 전문가와 상의하세요."
)
