'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import LoginPage from './login/page';
import DashboardPage from './dashboard/page';

export default function Home() {
  const { isLoggedIn, isLoading } = useAuth();
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return isLoggedIn ? <DashboardPage /> : <LoginPage />;
}
