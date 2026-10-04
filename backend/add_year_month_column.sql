-- PostgreSQL 마이그레이션: billing_records 테이블에 year_month 컬럼 추가
-- 2026-10-03

-- Step 1: year_month 컬럼이 없으면 추가
ALTER TABLE public.billing_records
ADD COLUMN IF NOT EXISTS year_month VARCHAR;

-- Step 2: 기존 데이터의 year_month 채우기
-- recorded_date에서 YYYY-MM 추출
UPDATE public.billing_records
SET year_month = TO_CHAR(recorded_date, 'YYYY-MM')
WHERE year_month IS NULL AND recorded_date IS NOT NULL;

-- Step 3: 인덱스 추가 (조회 성능)
CREATE INDEX IF NOT EXISTS idx_billing_records_year_month
ON public.billing_records(year_month);

-- Step 4: 검증
SELECT
    COUNT(*) as total_records,
    COUNT(year_month) as records_with_year_month,
    COUNT(*) - COUNT(year_month) as null_count
FROM public.billing_records;

-- Step 5: 샘플 데이터 확인
SELECT id, recorded_date, year_month, amount
FROM public.billing_records
LIMIT 5;
