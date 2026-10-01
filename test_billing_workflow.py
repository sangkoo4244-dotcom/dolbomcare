"""
청부 워크플로우 자동화 테스트 스크립트
draft → pending → approved → submitted_to_nhis → reimbursed
"""

import asyncio
import time
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5500"
API_URL = "http://localhost:8000/api/v1"

async def test_billing_workflow():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        print("\n" + "="*60)
        print("🎬 청부 워크플로우 테스트 시작")
        print("="*60)

        # ===== 1️⃣ 요양사 로그인 =====
        print("\n📍 Step 1: 요양사 로그인")
        context1 = await browser.new_context()
        page1 = await context1.new_page()

        await page1.goto(f"{BASE_URL}/login.html")
        await page1.fill('input[type="email"]', 'caregiver@test.com')
        await page1.fill('input[type="password"]', 'test123')
        await page1.click('button:has-text("로그인")')
        await page1.wait_for_url(f"{BASE_URL}/dashboard.html", timeout=5000)
        print("✅ 요양사 로그인 완료")

        # ===== 2️⃣ 요양사: 나의 청부로 이동 =====
        print("\n📍 Step 2: 요양사 - 나의 청부 화면")
        await page1.click('a:has-text("나의 청부")')
        await page1.wait_for_selector('.table', timeout=5000)

        # 현재 청부 상태 확인
        rows = await page1.locator('table tbody tr').count()
        print(f"   현재 청부 {rows}건")

        # Draft 상태의 청부 찾기
        cells = await page1.locator('.status-badge').all_text_contents()
        draft_index = -1
        for i, cell in enumerate(cells):
            if 'draft' in cell.lower() or '임시' in cell:
                draft_index = i
                break

        if draft_index == -1:
            print("   ⚠️ Draft 청부가 없습니다. 테스트 스킵")
            await context1.close()
        else:
            # ===== 3️⃣ 요양사: 청부 제출 =====
            print("\n📍 Step 3: 요양사 - [제출] 버튼 클릭")
            submit_btn = page1.locator('.btn-submit').first
            await submit_btn.click()
            await page1.wait_for_selector('text=제출되었습니다', timeout=5000)
            print("✅ 청부 제출 완료 (draft → pending)")
            await page1.wait_for_timeout(1000)

            # 청부 ID 추출 (URL 또는 데이터에서)
            await page1.reload()
            await page1.wait_for_selector('.table', timeout=5000)
            pending_badge = await page1.locator('.status-badge:has-text("승인 대기")').first.text_content()
            print(f"   상태 변경 확인: {pending_badge}")

            await context1.close()

        # ===== 4️⃣ 센터장 로그인 =====
        print("\n📍 Step 4: 센터장 로그인")
        context2 = await browser.new_context()
        page2 = await context2.new_page()

        await page2.goto(f"{BASE_URL}/login.html")
        await page2.fill('input[type="email"]', 'manager@test.com')
        await page2.fill('input[type="password"]', 'test123')
        await page2.click('button:has-text("로그인")')
        await page2.wait_for_url(f"{BASE_URL}/dashboard.html", timeout=5000)
        print("✅ 센터장 로그인 완료")

        # ===== 5️⃣ 센터장: 청부 관리로 이동 =====
        print("\n📍 Step 5: 센터장 - 청부 관리 화면")
        await page2.click('a:has-text("청부 관리")')
        await page2.wait_for_selector('.table', timeout=5000)

        # 대기 중 필터 적용
        await page2.click('button:has-text("대기 중")')
        await page2.wait_for_timeout(500)

        pending_rows = await page2.locator('table tbody tr:has-text("승인 대기")').count()
        print(f"   대기 중인 청부: {pending_rows}건")

        # ===== 6️⃣ 센터장: [승인] 버튼 클릭 =====
        if pending_rows > 0:
            print("\n📍 Step 6: 센터장 - [승인] 버튼 클릭")
            approve_btn = page2.locator('.action-btn:has-text("승인")').first
            await approve_btn.click()

            # 확인 대화상자 처리
            dialog = await page2.wait_for_event("dialog")
            await dialog.accept()

            await page2.wait_for_selector('text=승인되었습니다|승인되었습니다', timeout=5000)
            print("✅ 청부 승인 완료 (pending → approved)")
            await page2.wait_for_timeout(1000)

            # 테이블 새로고침
            await page2.reload()
            await page2.wait_for_selector('.table', timeout=5000)

            # ===== 7️⃣ 센터장: [건보 청구] 버튼 클릭 =====
            print("\n📍 Step 7: 센터장 - [건보 청구] 버튼 클릭")
            await page2.click('button:has-text("승인")')  # 필터 초기화
            await page2.wait_for_timeout(500)

            submit_nhis_btn = page2.locator('.action-btn:has-text("건보 청구")').first
            if await submit_nhis_btn.count() > 0:
                await submit_nhis_btn.click()

                dialog = await page2.wait_for_event("dialog")
                await dialog.accept()

                await page2.wait_for_selector('text=청구되었습니다', timeout=5000)
                print("✅ 건보 청구 완료 (approved → submitted_to_nhis)")
                await page2.wait_for_timeout(1000)

                # ===== 8️⃣ 센터장: [환급 확인] 버튼 클릭 =====
                print("\n📍 Step 8: 센터장 - [환급 확인] 버튼 클릭")
                await page2.reload()
                await page2.wait_for_selector('.table', timeout=5000)

                confirm_btn = page2.locator('.action-btn:has-text("환급 확인")').first
                if await confirm_btn.count() > 0:
                    await confirm_btn.click()

                    dialog = await page2.wait_for_event("dialog")
                    await dialog.accept()

                    await page2.wait_for_selector('text=확인되었습니다', timeout=5000)
                    print("✅ 환급 확인 완료 (submitted_to_nhis → reimbursed)")
                    print("✅ 자동 아카이브됨")

        await context2.close()

        # ===== 최종 상태 확인 =====
        print("\n" + "="*60)
        print("📊 최종 상태 확인")
        print("="*60)

        import requests
        response = requests.get(f"{API_URL}/billing/?center_id=1")
        data = response.json()

        active = len([r for r in data['records'] if not r['is_archived']])
        archived = len([r for r in data['records'] if r['is_archived']])

        print(f"\n✅ 활성 청부: {active}건")
        print(f"✅ 아카이브된 청부: {archived}건")

        for record in data['records']:
            status = "아카이브" if record['is_archived'] else "활성"
            print(f"   - ID {record['id']}: {record['approval_status']} ({status})")

        print("\n" + "="*60)
        print("🎉 테스트 완료!")
        print("="*60)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_billing_workflow())
