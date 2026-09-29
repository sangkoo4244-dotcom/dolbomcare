'use client';

import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function DashboardPage() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push('/');
    router.refresh();
  };

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div>로딩 중...</div>
      </div>
    );
  }

  const roleLabel = user.role === 'caregiver' ? '요양사' : '센터장';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* 헤더 */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold text-blue-600 dark:text-blue-400">
                돌봄케어 대시보드
              </h1>
              <p className="text-gray-600 dark:text-gray-400 mt-1">
                {user.full_name} 님, 환영합니다! ({roleLabel})
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors"
            >
              로그아웃
            </button>
          </div>
        </div>
      </header>

      {/* 메인 컨텐츠 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* 카드 1: 오늘의 업무 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-l-4 border-blue-600">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                📋 오늘의 업무
              </h2>
            </div>
            <div className="space-y-2 text-gray-600 dark:text-gray-400">
              <p>할당된 이용자: <span className="font-bold text-gray-900 dark:text-white">3명</span></p>
              <p>완료된 기록: <span className="font-bold text-gray-900 dark:text-white">2건</span></p>
              <p>대기 중: <span className="font-bold text-gray-900 dark:text-white">1건</span></p>
            </div>
          </div>

          {/* 카드 2: 음성 기록 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-l-4 border-green-600">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                🎙️ 음성 기록
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              이용자의 일일 상태를 음성으로 기록하세요.
            </p>
            <button className="w-full py-2 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors">
              + 새 기록 시작
            </button>
          </div>

          {/* 카드 3: 건강 지표 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-l-4 border-orange-600">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                ❤️ 건강 지표
              </h2>
            </div>
            <div className="space-y-2 text-gray-600 dark:text-gray-400">
              <p>정상: <span className="font-bold text-green-600">8명</span></p>
              <p>주의: <span className="font-bold text-yellow-600">2명</span></p>
              <p>위험: <span className="font-bold text-red-600">0명</span></p>
            </div>
          </div>

          {/* 카드 4: 이용자 관리 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-l-4 border-purple-600">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                👥 이용자 관리
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              센터 내 이용자를 관리하세요.
            </p>
            <button className="w-full py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors">
              이용자 관리
            </button>
          </div>

          {/* 카드 5: 보고서 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-l-4 border-indigo-600">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                📊 보고서
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              월별 통계 및 현황을 확인하세요.
            </p>
            <button className="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors">
              보고서 조회
            </button>
          </div>

          {/* 카드 6: 설정 */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-l-4 border-gray-600">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                ⚙️ 설정
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              계정 설정 및 개인 정보를 관리하세요.
            </p>
            <button className="w-full py-2 px-4 bg-gray-600 hover:bg-gray-700 text-white font-medium rounded-lg transition-colors">
              설정 열기
            </button>
          </div>
        </div>

        {/* 최근 활동 */}
        <div className="mt-8 bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
            최근 활동
          </h2>
          <div className="space-y-3 text-gray-600 dark:text-gray-400 text-sm">
            <p>• 김요양사가 이용자 "홍길동"의 기록을 추가했습니다. (2024-01-15 14:30)</p>
            <p>• 건강 지표 "이순신"이 주의 상태로 변경되었습니다. (2024-01-15 10:15)</p>
            <p>• 센터 보고서가 생성되었습니다. (2024-01-14 18:00)</p>
          </div>
        </div>
      </main>
    </div>
  );
}
