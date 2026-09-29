import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';

const API_URL = 'http://localhost:8000/api/v1';

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('caregiver@dolbomcare.com');
  const [password, setPassword] = useState('password123');
  const [role, setRole] = useState('caregiver');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert('Error', 'Please enter email and password');
      return;
    }

    setLoading(true);
    console.log('🔍 로그인 시도:', email);
    try {
      console.log('📡 API 요청:', `${API_URL}/auth/login`);
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      console.log('📊 응답 상태:', response.status);
      const data = await response.json();
      console.log('📦 응답 데이터:', data);

      if (response.ok) {
        await AsyncStorage.setItem('access_token', data.access_token);
        await AsyncStorage.setItem('user_role', role);
        await AsyncStorage.setItem('user_id', data.user.id.toString());

        Alert.alert('Success', `로그인 성공! 역할: ${data.user.role}`);

        if (data.user.role === 'caregiver') {
          router.replace('/dashboard');
        } else {
          router.replace('/manager');
        }
      } else {
        Alert.alert('Error', data.detail || 'Login failed');
      }
    } catch (error) {
      console.error('❌ 에러:', error);
      Alert.alert('Error', `Network error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>돌봄케어</Text>
        <Text style={styles.subtitle}>요양원 통합관리 플랫폼</Text>
      </View>

      <View style={styles.roleContainer}>
        <Text style={styles.label}>역할 선택</Text>
        <View style={styles.roleButtons}>
          <TouchableOpacity
            style={[
              styles.roleButton,
              role === 'caregiver' && styles.roleButtonActive,
            ]}
            onPress={() => setRole('caregiver')}
          >
            <Text style={styles.roleButtonText}>요양사</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.roleButton,
              role === 'center_manager' && styles.roleButtonActive,
            ]}
            onPress={() => setRole('center_manager')}
          >
            <Text style={styles.roleButtonText}>센터장</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.form}>
        <TextInput
          style={styles.input}
          placeholder="이메일"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          editable={!loading}
        />
        <TextInput
          style={styles.input}
          placeholder="비밀번호"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          editable={!loading}
        />

        <TouchableOpacity
          style={[styles.loginButton, loading && styles.loginButtonDisabled]}
          onPress={handleLogin}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.loginButtonText}>로그인</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>테스트 계정:</Text>
        <Text style={styles.footerSmall}>이메일: caregiver@dolbomcare.com</Text>
        <Text style={styles.footerSmall}>비밀번호: password123</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 20,
    justifyContent: 'center',
    backgroundColor: '#F5F5F5',
  },
  header: {
    marginBottom: 40,
    alignItems: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#007AFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
  },
  roleContainer: {
    marginBottom: 30,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 12,
    color: '#333',
  },
  roleButtons: {
    flexDirection: 'row',
    gap: 12,
  },
  roleButton: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: '#DDD',
    alignItems: 'center',
  },
  roleButtonActive: {
    borderColor: '#007AFF',
    backgroundColor: '#E8F4FF',
  },
  roleButtonText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
  },
  form: {
    gap: 16,
    marginBottom: 30,
  },
  input: {
    borderWidth: 1,
    borderColor: '#DDD',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 14,
    backgroundColor: '#FFF',
  },
  loginButton: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  loginButtonDisabled: {
    opacity: 0.6,
  },
  loginButtonText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    paddingTop: 20,
    borderTopWidth: 1,
    borderTopColor: '#DDD',
  },
  footerText: {
    fontSize: 12,
    color: '#666',
    marginBottom: 4,
  },
  footerSmall: {
    fontSize: 11,
    color: '#999',
    marginBottom: 2,
  },
});
