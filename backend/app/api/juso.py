import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

# 행정안전부 도로명주소 팝업은 주소를 고르면 returnUrl로 결과를 POST(폼 전송)한다.
# 정적 파일은 POST를 받지 못해 "Method Not Allowed"가 나므로, 같은 주소로 POST를 받아
# 결과를 부모창(window.opener.fillJusoAddress)에 넘기고 팝업을 닫는 페이지를 돌려준다.
RETURN_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>주소 선택</title></head>
<body><script>
const result = __RESULT__;
if (window.opener && typeof window.opener.fillJusoAddress === 'function') {
    window.opener.fillJusoAddress(result);
}
window.close();
</script></body></html>"""


@router.post("/pages/juso_popup_return.html", response_class=HTMLResponse, include_in_schema=False)
async def juso_popup_return(request: Request):
    form = await request.form()
    result = {k: str(v) for k, v in form.items()}
    payload = json.dumps(result, ensure_ascii=False).replace("</", "<\/")
    return RETURN_PAGE.replace("__RESULT__", payload)
