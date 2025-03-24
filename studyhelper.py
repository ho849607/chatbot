import os
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv
import requests
import xml.etree.ElementTree as ET

# 페이지 설정을 최우선으로 실행
st.set_page_config(page_title="ThinkHelper 법령 검색", layout="wide")

# 환경변수 로드
load_dotenv()
LAWGOKR_API_KEY = os.getenv("LAWGOKR_API_KEY")
if not LAWGOKR_API_KEY:
    st.error("LAWGOKR_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

###############################################################################
# 국가법령정보센터 API 함수
###############################################################################
@st.cache_data(show_spinner=False)
def law_search(keyword):
    url = f"https://www.law.go.kr/DRF/lawSearch.do?OC={LAWGOKR_API_KEY}&target=law&type=XML&query={keyword}"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            st.error(f"API 호출 실패: {response.status_code}")
            return []
        tree = ET.fromstring(response.content)
        results = []
        for item in tree.findall("law"):
            law_name = item.findtext("법령명한글")
            law_id = item.findtext("법령ID")
            results.append({"name": law_name, "id": law_id})
        return results
    except Exception as e:
        st.error(f"법령 검색 중 오류 발생: {e}")
        return []

@st.cache_data(show_spinner=False)
def law_view(law_id):
    url = f"https://www.law.go.kr/DRF/lawView.do?OC={LAWGOKR_API_KEY}&target=law&type=XML&ID={law_id}"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return f"API 호출 실패: {response.status_code}"
        tree = ET.fromstring(response.content)
        content = tree.findtext("조문내용") or "본문 없음"
        return content
    except Exception as e:
        return f"법령 본문 조회 중 오류: {e}"

###############################################################################
# Streamlit UI
###############################################################################
def main():
    st.title("📚 ThinkHelper - 국가법령정보센터 API 연동")
    st.markdown("""
    **ThinkHelper 법령검색 도우미**는 국가법령정보센터의 API를 활용해
    법률 문서를 빠르게 검색하고 열람할 수 있는 서비스입니다.

    - 법령명을 키워드로 검색해보세요 (예: 개인정보보호법, 산업안전보건법 등)
    - API를 통해 최신 법령 본문을 바로 확인할 수 있습니다.
    """)

    tab = st.sidebar.radio("🧭 메뉴", ["법령 검색"])

    if tab == "법령 검색":
        st.header("🔍 법령 검색")
        keyword = st.text_input("법령 키워드 입력", placeholder="예: 근로기준법, 민법")

        if st.button("검색"):
            if not keyword.strip():
                st.warning("검색어를 입력해주세요.")
            else:
                with st.spinner("검색 중..."):
                    results = law_search(keyword)

                if results:
                    st.success(f"총 {len(results)}개의 검색 결과가 있습니다.")
                    for idx, r in enumerate(results):
                        with st.expander(f"{idx+1}. {r['name']}"):
                            if st.button("📄 본문 보기", key=f"view_{r['id']}"):
                                with st.spinner("본문 불러오는 중..."):
                                    content = law_view(r["id"])
                                st.text_area("법령 본문", content, height=300)
                else:
                    st.info("검색 결과가 없습니다.")

if __name__ == "__main__":
    main()

st.markdown("""
---
**저작권 안내**
- 본 서비스는 [국가법령정보센터](https://www.law.go.kr)의 API를 이용하며,
  법령 정보는 공공데이터로 제공됩니다.
- 저작권 및 서비스 이용에 대한 책임은 사용자에게 있습니다.
""")
