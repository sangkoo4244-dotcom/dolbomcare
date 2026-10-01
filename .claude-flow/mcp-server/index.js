#!/usr/bin/env node
/**
 * dolbomcare MCP Server for RUflo
 * Connects dolbomcare Backend API with RUflo agents
 */

const http = require('http');
const https = require('https');

// Environment
const API_URL = process.env.DOLBOMCARE_API_URL || 'http://localhost:8000/api/v1';
const JWT_SECRET = process.env.DOLBOMCARE_JWT_SECRET || 'your-secret-key';

class DolbomcareMCPServer {
  constructor() {
    this.client = null;
    this.jwtToken = null;
  }

  // ============ Auth Tools ============
  async getAuthToken(email, password) {
    try {
      const response = await this.apiCall('POST', '/users/login', {
        email,
        password
      });
      this.jwtToken = response.access_token;
      return {
        success: true,
        token: response.access_token,
        user: response
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  }

  // ============ Voice Record Tools ============
  async createVoiceRecord(residentId, audioFile, serviceType, notes) {
    const formData = new FormData();
    formData.append('resident_id', residentId);
    formData.append('audio_file', audioFile);
    formData.append('service_type', serviceType);
    formData.append('notes', notes || '');

    return await this.apiCall('POST', '/records/voice', formData);
  }

  async getVoiceRecords(options = {}) {
    const params = new URLSearchParams();
    if (options.resident_id) params.append('resident_id', options.resident_id);
    if (options.status) params.append('status', options.status);
    if (options.date_range) {
      params.append('start_date', options.date_range.start);
      params.append('end_date', options.date_range.end);
    }

    const query = params.toString() ? `?${params.toString()}` : '';
    return await this.apiCall('GET', `/records/voice${query}`);
  }

  async archiveVoiceRecord(voiceId) {
    return await this.apiCall('PUT', `/records/voice/${voiceId}/archive`, {});
  }

  // ============ Billing Tools ============
  async createBillingFromVoice(voiceId, options = {}) {
    const payload = {
      voice_id: voiceId,
      auto_approve: options.auto_approve || false,
      override_amount: options.override_amount || null
    };

    return await this.apiCall('POST', '/billing/auto-create-from-voice', payload);
  }

  async approveBilling(billingId, notes, overrideAmount) {
    const payload = {
      status: 'approved',
      center_manager_notes: notes || '',
      override_amount: overrideAmount || null,
      approved_at: new Date().toISOString()
    };

    return await this.apiCall('PUT', `/billing/${billingId}`, payload);
  }

  async rejectBilling(billingId, reason) {
    const payload = {
      status: 'pending',  // 상태 되돌리기
      center_manager_notes: `거절: ${reason}`,
      rejected_at: new Date().toISOString()
    };

    return await this.apiCall('PUT', `/billing/${billingId}`, payload);
  }

  async getBillings(options = {}) {
    const params = new URLSearchParams();
    if (options.status) params.append('status', options.status);
    if (options.caregiver_id) params.append('caregiver_id', options.caregiver_id);
    if (options.date_range) {
      params.append('start_date', options.date_range.start);
      params.append('end_date', options.date_range.end);
    }

    const query = params.toString() ? `?${params.toString()}` : '';
    return await this.apiCall('GET', `/billing${query}`);
  }

  async submitBillingToNHIS(billingIds) {
    return await this.apiCall('POST', '/billing/submit-to-nhis', {
      billing_ids: billingIds
    });
  }

  // ============ Resident Tools ============
  async getResidents(centerId) {
    const query = centerId ? `?center_id=${centerId}` : '';
    return await this.apiCall('GET', `/residents${query}`);
  }

  async getResident(residentId) {
    return await this.apiCall('GET', `/residents/${residentId}`);
  }

  async updateResident(residentId, data) {
    return await this.apiCall('PUT', `/residents/${residentId}`, data);
  }

  // ============ Caregiver Tools ============
  async getCaregivers(centerId) {
    const query = centerId ? `?center_id=${centerId}` : '';
    return await this.apiCall('GET', `/users${query}`);
  }

  async getCaregiverPerformance(caregiverId, month) {
    const query = month ? `?month=${month}` : '';
    return await this.apiCall('GET', `/users/${caregiverId}/performance${query}`);
  }

  // ============ Analytics Tools ============
  async getDailySummary(date, centerId) {
    const params = new URLSearchParams();
    if (date) params.append('date', date);
    if (centerId) params.append('center_id', centerId);

    const query = params.toString() ? `?${params.toString()}` : '';
    return await this.apiCall('GET', `/records/today${query}`);
  }

  async getMonthlyReport(month, include = ['billing', 'voice', 'residents']) {
    const payload = {
      month,
      include
    };

    return await this.apiCall('POST', '/reports/monthly', payload);
  }

  async detectAnomalies(dataType, threshold = 0.9) {
    return await this.apiCall('POST', '/analytics/anomalies', {
      data_type: dataType,
      threshold
    });
  }

  // ============ Notification Tools ============
  async sendPushNotification(userId, title, body, data) {
    return await this.apiCall('POST', '/notifications/push', {
      user_id: userId,
      title,
      body,
      data: data || {}
    });
  }

  async sendEmail(to, subject, template, variables) {
    return await this.apiCall('POST', '/notifications/email', {
      to,
      subject,
      template,
      variables: variables || {}
    });
  }

  // ============ Internal API Call ============
  async apiCall(method, endpoint, body) {
    return new Promise((resolve, reject) => {
      const url = new URL(API_URL + endpoint);
      const protocol = url.protocol === 'https:' ? https : http;

      const options = {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': this.jwtToken ? `Bearer ${this.jwtToken}` : ''
        }
      };

      const req = protocol.request(url, options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(JSON.parse(data));
            } catch {
              resolve(data);
            }
          } else {
            reject(new Error(`API Error: ${res.statusCode} ${data}`));
          }
        });
      });

      req.on('error', reject);

      if (body && method !== 'GET') {
        req.write(JSON.stringify(body));
      }

      req.end();
    });
  }
}

// Initialize and start server
const server = new DolbomcareMCPServer();

// MCP Protocol Handler
process.stdin.on('data', async (buffer) => {
  try {
    const message = JSON.parse(buffer.toString());

    // Route to appropriate handler
    const result = await routeMessage(message, server);

    process.stdout.write(JSON.stringify(result) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({
      error: error.message
    }) + '\n');
  }
});

async function routeMessage(message, server) {
  const { method, params } = message;

  // Billing operations
  if (method === 'dolbomcare/billing/auto_create') {
    return await server.createBillingFromVoice(params.voice_id, params);
  }
  if (method === 'dolbomcare/billing/approve') {
    return await server.approveBilling(params.billing_id, params.notes, params.override_amount);
  }
  if (method === 'dolbomcare/billing/reject') {
    return await server.rejectBilling(params.billing_id, params.reason);
  }
  if (method === 'dolbomcare/billing/list') {
    return await server.getBillings(params);
  }

  // Voice operations
  if (method === 'dolbomcare/voice/create') {
    return await server.createVoiceRecord(
      params.resident_id,
      params.audio_file,
      params.service_type,
      params.notes
    );
  }
  if (method === 'dolbomcare/voice/list') {
    return await server.getVoiceRecords(params);
  }
  if (method === 'dolbomcare/voice/archive') {
    return await server.archiveVoiceRecord(params.voice_id);
  }

  // Resident operations
  if (method === 'dolbomcare/residents/list') {
    return await server.getResidents(params.center_id);
  }
  if (method === 'dolbomcare/residents/get') {
    return await server.getResident(params.resident_id);
  }

  // Analytics
  if (method === 'dolbomcare/analytics/daily_summary') {
    return await server.getDailySummary(params.date, params.center_id);
  }
  if (method === 'dolbomcare/analytics/monthly_report') {
    return await server.getMonthlyReport(params.month, params.include);
  }

  // Notifications
  if (method === 'dolbomcare/notifications/push') {
    return await server.sendPushNotification(
      params.user_id,
      params.title,
      params.body,
      params.data
    );
  }

  return { error: 'Unknown method: ' + method };
}

console.error('[dolbomcare-mcp] Server started');
console.error(`[dolbomcare-mcp] API URL: ${API_URL}`);
