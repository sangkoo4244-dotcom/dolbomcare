import React, { useState, useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import AsyncStorage from '@react-native-async-storage/async-storage';

import LoginScreen from './screens/LoginScreen';
import CaregiverDashboard from './screens/CaregiverDashboard';
import DailyRecordScreen from './screens/DailyRecordScreen';
import CenterManagerScreen from './screens/CenterManagerScreen';

const Stack = createNativeStackNavigator();

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userRole, setUserRole] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const token = await AsyncStorage.getItem('access_token');
      const role = await AsyncStorage.getItem('user_role');

      if (token && role) {
        setIsLoggedIn(true);
        setUserRole(role);
      }
    } catch (error) {
      console.log('Auth check error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = (role: string) => {
    setIsLoggedIn(true);
    setUserRole(role);
  };

  const handleLogout = async () => {
    await AsyncStorage.removeItem('access_token');
    await AsyncStorage.removeItem('user_role');
    setIsLoggedIn(false);
    setUserRole(null);
  };

  if (loading) {
    return null;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!isLoggedIn ? (
          <Stack.Screen
            name="Login"
            options={{ animationEnabled: false }}
          >
            {props => <LoginScreen {...props} onLogin={handleLogin} />}
          </Stack.Screen>
        ) : userRole === 'caregiver' ? (
          <>
            <Stack.Screen
              name="CaregiverDashboard"
              options={{ animationEnabled: false }}
            >
              {props => <CaregiverDashboard {...props} onLogout={handleLogout} />}
            </Stack.Screen>
            <Stack.Screen name="DailyRecord" component={DailyRecordScreen} />
          </>
        ) : (
          <Stack.Screen
            name="CenterManager"
            options={{ animationEnabled: false }}
          >
            {props => <CenterManagerScreen {...props} onLogout={handleLogout} />}
          </Stack.Screen>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
