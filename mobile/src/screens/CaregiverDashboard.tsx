import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
} from 'react-native';

export default function CaregiverDashboard({ navigation, onLogout }) {
  return (
    <ScrollView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>돌봄케어</Text>
        <TouchableOpacity onPress={onLogout}>
          <Text style={styles.logoutText}>로그아웃</Text>
        </TouchableOpacity>
      </View>

      {/* Today's Summary */}
      <View style={styles.summaryCard}>
        <Text style={styles.summaryTitle}>오늘의 업무</Text>
        <View style={styles.summaryRow}>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>담당 어르신</Text>
            <Text style={styles.summaryValue}>12명</Text>
          </View>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>완료한 기록</Text>
            <Text style={styles.summaryValue}>8명</Text>
          </View>
        </View>
      </View>

      {/* Quick Actions */}
      <View style={styles.actionsContainer}>
        <TouchableOpacity
          style={styles.actionButton}
          onPress={() => navigation.navigate('DailyRecord')}
        >
          <Text style={styles.actionIcon}>🎤</Text>
          <Text style={styles.actionLabel}>음성 기록</Text>
          <Text style={styles.actionDesc}>음성으로 빠르게 기록</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.actionButton}>
          <Text style={styles.actionIcon}>📸</Text>
          <Text style={styles.actionLabel}>사진 등록</Text>
          <Text style={styles.actionDesc}>활동 사진 첨부</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.actionButton}>
          <Text style={styles.actionIcon}>📋</Text>
          <Text style={styles.actionLabel}>체크리스트</Text>
          <Text style={styles.actionDesc}>일일 체크항목</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.actionButton}>
          <Text style={styles.actionIcon}>💰</Text>
          <Text style={styles.actionLabel}>급여 확인</Text>
          <Text style={styles.actionDesc}>월급 내역</Text>
        </TouchableOpacity>
      </View>

      {/* Recent Records */}
      <View style={styles.recentSection}>
        <Text style={styles.sectionTitle}>최근 기록</Text>

        {[
          { name: '김영희님', time: '오늘 14:30', status: '✓' },
          { name: '이순신님', time: '오늘 13:45', status: '✓' },
          { name: '박문수님', time: '어제 15:20', status: '✓' },
        ].map((record, idx) => (
          <View key={idx} style={styles.recordItem}>
            <View>
              <Text style={styles.recordName}>{record.name}</Text>
              <Text style={styles.recordTime}>{record.time}</Text>
            </View>
            <Text style={styles.recordStatus}>{record.status}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F5F5',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    backgroundColor: '#FFF',
    borderBottomWidth: 1,
    borderBottomColor: '#EEE',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#007AFF',
  },
  logoutText: {
    fontSize: 14,
    color: '#007AFF',
  },
  summaryCard: {
    margin: 16,
    padding: 16,
    backgroundColor: '#FFF',
    borderRadius: 12,
    borderLeftWidth: 4,
    borderLeftColor: '#007AFF',
  },
  summaryTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
    color: '#333',
  },
  summaryRow: {
    flexDirection: 'row',
    gap: 16,
  },
  summaryItem: {
    flex: 1,
  },
  summaryLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  summaryValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#007AFF',
  },
  actionsContainer: {
    paddingHorizontal: 16,
    gap: 12,
  },
  actionButton: {
    backgroundColor: '#FFF',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  actionIcon: {
    fontSize: 32,
  },
  actionLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    flex: 1,
  },
  actionDesc: {
    fontSize: 12,
    color: '#999',
    position: 'absolute',
    bottom: 12,
    left: 52,
  },
  recentSection: {
    marginTop: 20,
    paddingHorizontal: 16,
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
    color: '#333',
  },
  recordItem: {
    backgroundColor: '#FFF',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  recordName: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
  },
  recordTime: {
    fontSize: 12,
    color: '#999',
    marginTop: 4,
  },
  recordStatus: {
    fontSize: 16,
    color: '#34C759',
  },
});
