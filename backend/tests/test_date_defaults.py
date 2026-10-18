"""화면의 날짜 기본값은 한국 시간 새벽에도 오늘을 가리켜야 한다.
new Date().toISOString().slice(0, 10)은 UTC 날짜라서 자정~오전 9시에 어제를 돌려준다. 그래서 날짜 기본값은 todayLocal()을 쓴다."""
from pathlib import Path

PAGES = Path(__file__).resolve().parents[1] / "static" / "pages"
FORBIDDEN = ("toISOString().slice(0, 10)", "toISOString().slice(0, 7)")


def test_no_page_derives_a_date_from_utc():
    offenders = []
    for path in sorted(PAGES.glob("*.html")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(f in line for f in FORBIDDEN):
                offenders.append(f"{path.name}:{n}")
    assert offenders == [], f"UTC 기준 날짜 기본값이 남아 있습니다: {offenders}"


def test_pages_that_use_the_helper_load_menu_js():
    for path in sorted(PAGES.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        if "todayLocal(" in text:
            assert "menu.js" in text, f"{path.name}는 todayLocal을 쓰지만 menu.js를 불러오지 않습니다"
