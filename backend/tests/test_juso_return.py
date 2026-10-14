from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import juso


def client():
    app = FastAPI()
    app.include_router(juso.router)
    return TestClient(app)


def test_popup_result_posted_to_return_page_is_handed_to_opener():
    r = client().post("/pages/juso_popup_return.html", data={"roadFullAddr": "서울특별시 송파구 올림픽로 300", "addrDetail": "101동 </script>"})
    assert r.status_code == 200
    assert "서울특별시 송파구 올림픽로 300" in r.text
    assert "window.opener.fillJusoAddress(result)" in r.text
    assert "</script>" not in r.text.split("const result")[1].split("if (window.opener")[0]  # 입력값이 스크립트를 끝내지 못함
