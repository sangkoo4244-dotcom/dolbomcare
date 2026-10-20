"""새 모델을 만들면 운영 DB에 테이블이 생기도록 run_migrations의 생성 목록에 넣었는지 확인한다.

비품·관찰일지·교육 수료증이 이 목록에서 빠져 운영 DB에 테이블이 없을 수 있었던 일이 있었다.
아래 허용 목록은 과거에 create_all 등으로 이미 만들어진 테이블만 담는다. 새 모델은 여기 넣지 말고 생성 목록에 넣는다."""
import re
import warnings

from app import models  # noqa: F401  모델을 Base에 등록한다
from app.database import Base

LEGACY_TABLES = {"Center", "User", "MonthlySummary", "Salary", "HealthMetric", "ResidentChangeRequest",
                 "BillingRecord", "VoiceRecord"}


def test_every_model_table_is_created_on_startup_or_is_legacy():
    src = open("app/migrations.py", encoding="utf-8").read()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        classes = {t.name: next(c for c in vars(models).values()
                                if isinstance(c, type) and getattr(c, "__tablename__", None) == t.name)
                   for t in Base.metadata.sorted_tables}
    not_created = {c.__name__ for c in classes.values() if not re.search(r"\b" + c.__name__ + r"\b", src)}
    assert not_created <= LEGACY_TABLES, f"생성 목록(run_migrations)에 없는 새 모델: {sorted(not_created - LEGACY_TABLES)}"
