"""운영 DB 점검 도구 (읽기 전용): 모델에 정의된 테이블·컬럼이 실제 DB에 있는지 확인한다.

사용법 (DB 주소는 DATABASE_URL 환경변수, 없으면 로컬 SQLite):
    venv\Scripts\python.exe -m app.schema_check
없는 것이 있으면 종료 코드 1을 돌려준다. 이 도구는 아무것도 만들거나 바꾸지 않는다.
"""
import sys

from sqlalchemy import inspect

import app.models  # noqa: F401  모델을 Base에 등록한다
from app.database import Base, engine


def missing_schema(eng) -> dict:
    insp = inspect(eng)
    existing_tables = set(insp.get_table_names())
    missing_tables, missing_columns = [], []
    for table in Base.metadata.tables.values():
        if table.name not in existing_tables:
            missing_tables.append(table.name)
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                missing_columns.append((table.name, col.name))
    return {"missing_tables": missing_tables, "missing_columns": missing_columns}


def main() -> int:
    try:
        result = missing_schema(engine)
    except Exception as e:  # 연결 실패는 원인 문구가 인코딩 때문에 깨질 수 있어 종류만 알려 준다
        print(f"DB 연결 실패 ({type(e).__name__}). 주소, 포트, 비밀번호와 DB 서버 실행 여부를 확인하세요.")
        return 2
    print(f"DB: {engine.url.render_as_string(hide_password=True)}")
    print(f"모델 테이블 {len(Base.metadata.tables)}개 중 없는 테이블: {len(result['missing_tables'])}개")
    for name in result["missing_tables"]:
        print(f"  - 테이블 없음: {name}")
    print(f"없는 컬럼: {len(result['missing_columns'])}개")
    for table, col in result["missing_columns"]:
        print(f"  - {table}.{col}")
    ok = not result["missing_tables"] and not result["missing_columns"]
    print("결과: 정상" if ok else "결과: 마이그레이션 확인 필요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
