'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { authAPI } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState('caregiver@dolbomcare.com');
  const [password, setPassword] = useState('password123');
  const [role, setRole] = useState('caregiver');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await authAPI.login(email, password);
      const { access_token, user } = response.data;

      login(user, access_token);
      router.push('/');
      router.refresh();
    } catch (err: any) {
      setError(
        err.response?.data?.detail || '로그인 실패. 이메일과 비밀번호를 확인하세요.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md">
        {/* 헤더 */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-blue-600 dark:text-blue-400 mb-2">
            돌봄케어
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            요양원 통합관리 플랫폼
          </p>
        </div>

        {/* 역할 선택 */}
        <div className="mb-6">
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            역할 선택
          </label>
          <div className="flex gap-3">
            {[
              { value: 'caregiver', label: '요양사' },
              { value: 'center_manager', label: '센터장' },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setRole(opt.value)}
                className={`flex-1 py-3 px-4 rounded-lg font-medium transition-all ${
                  role === opt.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* 폼 */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              이메일
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              placeholder="이메일을 입력하세요"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              placeholder="비밀번호를 입력하세요"
            />
          </div>

          {error && (
            <div className="p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        {/* 테스트 계정 정보 */}
        <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
          <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
            📝 테스트 계정:
          </p>
          <div className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
            <p>
              <span className="font-medium">요양사:</span> caregiver@dolbomcare.com
            </p>
            <p>
              <span className="font-medium">센터장:</span> manager@dolbomcare.com
            </p>
            <p>
              <span className="font-medium">비밀번호:</span> password123
            </p>
          </div>
        </div>

        {/* API 상태 */}
        <div className="mt-4 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg text-xs text-gray-600 dark:text-gray-400 text-center">
          Backend API: {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}
        </div>
      </div>
    </div>
  );
}
