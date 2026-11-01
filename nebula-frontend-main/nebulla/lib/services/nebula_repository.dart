import 'dart:io';
import '../core/constants.dart';
import '../models/models.dart';
import 'api_service.dart';
import 'storage_service.dart';

class NebulaRepository {
  NebulaRepository._();
  static NebulaRepository? _instance;
  static NebulaRepository get instance =>
      _instance ??= NebulaRepository._();

  final _api = ApiService.instance;
  final _store = StorageService.instance;

  // ── Auth ──────────────────────────────────────────────────────────────────

  Future<UserModel> login({
    required String email,
    required String password,
    bool rememberMe = false,
  }) async {
    final data = await _api.post(AppConstants.authLogin, {
      'email': email.trim().toLowerCase(),
      'password': password,
      'remember_me': rememberMe,
    });
    final resp = TokenResponse.fromJson(data as Map<String, dynamic>);
    await _store.setToken(resp.accessToken);
    await _store.setRememberMe(rememberMe);
    if (rememberMe) {
      await _store.setSavedEmail(email.trim().toLowerCase());
    } else {
      await _store.setSavedEmail('');
    }

    // Hydrate current active user profile via /auth/me
    UserModel user;
    if (resp.user != null) {
      user = resp.user!;
      await _store.setUser(user);
    } else {
      user = await getMe();
    }
    return user;
  }

  Future<UserModel> register({
    required String fullName,
    required String email,
    required String password,
    required String confirmPassword,
  }) async {
    final data = await _api.post(AppConstants.authRegister, {
      'full_name': fullName.trim(),
      'email': email.trim().toLowerCase(),
      'password': password,
      'confirm_password': confirmPassword,
      'terms_accepted': true,
    });
    final resp = TokenResponse.fromJson(data as Map<String, dynamic>);
    await _store.setToken(resp.accessToken);

    UserModel user;
    if (resp.user != null) {
      user = resp.user!;
      await _store.setUser(user);
    } else {
      user = await getMe();
    }
    return user;
  }

  Future<UserModel> loginBiometric({
    required String email,
    required File faceImage,
  }) async {
    final data = await _api.postMultipart(
      AppConstants.authBiometric,
      {'email': email.trim().toLowerCase()},
      faceImage,
      'file',
    );
    final resp = TokenResponse.fromJson(data as Map<String, dynamic>);
    await _store.setToken(resp.accessToken);

    UserModel user;
    if (resp.user != null) {
      user = resp.user!;
      await _store.setUser(user);
    } else {
      user = await getMe();
    }
    return user;
  }

  Future<UserModel> getMe() async {
    final data = await _api.get(AppConstants.authMe);
    final user = UserModel.fromJson(data as Map<String, dynamic>);
    await _store.setUser(user);
    return user;
  }

  Future<String> forgotPassword(String email) async {
    final data = await _api.post(AppConstants.authForgotPassword, {
      'email': email.trim().toLowerCase(),
    });
    final map = data as Map<String, dynamic>;
    return map['message'] as String? ?? 'تم إرسال تعليمات الاستعادة.';
  }

  Future<String> resetPassword({
    required String token,
    required String newPassword,
    required String confirmPassword,
  }) async {
    final data = await _api.post(AppConstants.authResetPassword, {
      'token': token.trim(),
      'new_password': newPassword,
      'confirm_password': confirmPassword,
    });
    final map = data as Map<String, dynamic>;
    return map['message'] as String? ?? 'تمت إعادة تعيين كلمة المرور بنجاح.';
  }

  /// Legacy pairing code login for backwards compatibility with hardware devices
  Future<TokenResponse> loginWithPairingCode(String pairingCode) async {
    final data = await _api.post(AppConstants.authToken, {
      'pairing_code': pairingCode,
      'device_name': _store.getDeviceName(),
    });
    final resp = TokenResponse.fromJson(data as Map<String, dynamic>);
    await _store.setToken(resp.accessToken);
    return resp;
  }

  Future<void> logout() async {
    await _store.clearToken();
  }

  bool get isLoggedIn => _store.getToken() != null;

  // ── Devices ───────────────────────────────────────────────────────────────

  Future<DeviceStatus> getDeviceStatus() async {
    final data = await _api.get(AppConstants.deviceStatus);
    return DeviceStatus.fromJson(data as Map<String, dynamic>);
  }

  // ── Personalities ─────────────────────────────────────────────────────────

  Future<List<Personality>> getPersonalities() async {
    final data = await _api.get(AppConstants.personalities);
    return (data as List)
        .map((e) => Personality.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Personality> createPersonality(Personality p) async {
    final data = await _api.post(AppConstants.personalities, p.toJson());
    return Personality.fromJson(data as Map<String, dynamic>);
  }

  Future<Personality> updatePersonality(int id, Map<String, dynamic> body) async {
    final data = await _api.patch('${AppConstants.personalities}$id', body);
    return Personality.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deletePersonality(int id) async {
    await _api.delete('${AppConstants.personalities}$id');
  }

  Future<void> activatePersonality(int id) async {
    await _api.post('${AppConstants.personalities}$id/activate');
  }

  // ── Memories ──────────────────────────────────────────────────────────────

  Future<List<Memory>> getMemories([int? personalityId]) async {
    final params = personalityId != null
        ? {'personality_id': personalityId.toString()}
        : null;
    final data = await _api.get(AppConstants.memories, params);
    return (data as List)
        .map((e) => Memory.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Memory> addMemory(
      String content, int personalityId, int importance) async {
    final data = await _api.post(AppConstants.memories, {
      'content': content,
      'personality_id': personalityId,
      'importance': importance,
      'source': 'manual',
    });
    return Memory.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteMemory(int id) async {
    await _api.delete('${AppConstants.memories}$id');
  }

  Future<List<Memory>> searchMemories(String query,
      [int? personalityId]) async {
    final params = <String, String>{'q': query};
    if (personalityId != null) {
      params['personality_id'] = personalityId.toString();
    }
    final data = await _api.get(AppConstants.memoriesSearch, params);
    return (data as List)
        .map((e) => Memory.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ── Chat ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> chat(String message,
      {String? sessionId, int? personalityId}) async {
    final body = <String, dynamic>{'message': message, 'stream': false};
    if (sessionId != null) body['session_id'] = sessionId;
    if (personalityId != null) body['personality_id'] = personalityId;
    return (await _api.post(AppConstants.chat, body)) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getConversations([int limit = 20]) async {
    final data = await _api.get(AppConstants.conversations, {'limit': limit});
    return data as List;
  }

  Future<List<dynamic>> getConversationMessages(int cid) async {
    final data = await _api.get('${AppConstants.conversations}$cid/messages');
    return data as List;
  }

  // ── Signals ───────────────────────────────────────────────────────────────

  Future<List<Signal>> getSignals() async {
    final data = await _api.get(AppConstants.signals);
    return (data as List)
        .map((e) => Signal.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Signal> createSignal(Signal s) async {
    final data = await _api.post(AppConstants.signals, s.toJson());
    return Signal.fromJson(data as Map<String, dynamic>);
  }

  Future<void> fireSignal(String name) async {
    await _api.post('${AppConstants.signals}$name/fire');
  }

  Future<void> deleteSignal(int id) async {
    await _api.delete('${AppConstants.signals}$id');
  }

  // ── Calibration ───────────────────────────────────────────────────────────

  Future<List<CalibrationEntry>> getCalibrations() async {
    final data = await _api.get(AppConstants.calibration);
    return (data as List)
        .map((e) => CalibrationEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> upsertCalibration(int servoId, Map<String, dynamic> body) async {
    await _api.put('${AppConstants.calibration}$servoId', body);
  }

  Future<void> resetCalibration() async {
    await _api.post(AppConstants.calibrationReset);
  }

  // ── Voice Clone ───────────────────────────────────────────────────────────

  Future<void> uploadVoiceSample(int personalityId, File file) async {
    await _api.postMultipart(
      '/api/v1/voice-clone/upload/$personalityId',
      {},
      file,
      'file',
    );
  }

  Future<List<dynamic>> getVoiceSamples() async {
    final data = await _api.get(AppConstants.voiceCloneSamples);
    return data as List;
  }

  // ── Diagnostics ───────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getDiagnosticsStatus() async {
    return (await _api.get(AppConstants.diagnosticsStatus))
        as Map<String, dynamic>;
  }

  Future<void> testServo(int servoId,
      {double angle = 90.0, int speedMs = 500}) async {
    await _api.post(AppConstants.diagnosticsServoTest, {
      'servo_id': servoId,
      'angle': angle,
      'speed_ms': speedMs,
    });
  }

  Future<void> homeAllServos() async {
    await _api.post(AppConstants.diagnosticsServoHomeAll);
  }

  Future<void> testMotors(
      {int left = 128, int right = 128, int durationMs = 1000}) async {
    await _api.post(AppConstants.diagnosticsMotorTest, {
      'left': left,
      'right': right,
      'duration_ms': durationMs,
    });
  }

  Future<void> setLed(String state) async {
    await _api.post(AppConstants.diagnosticsLed, {'state': state});
  }

  Future<Map<String, dynamic>> getSensorDistance() async {
    return (await _api.get(AppConstants.diagnosticsSensorDistance))
        as Map<String, dynamic>;
  }

  Future<void> emergencyStop() async {
    await _api.post(AppConstants.diagnosticsEmergencyStop);
  }

  // ── Settings ──────────────────────────────────────────────────────────────

  Future<AppSettings> getSettings() async {
    final data = await _api.get(AppConstants.settings);
    return AppSettings.fromJson(data as Map<String, dynamic>);
  }

  Future<AppSettings> updateProviders(Map<String, dynamic> providers) async {
    final data = await _api.patch(AppConstants.settingsProviders, providers);
    return AppSettings.fromJson(data as Map<String, dynamic>);
  }

  // ── Faces ─────────────────────────────────────────────────────────────────

  Future<void> registerFace(String name, File imageFile) async {
    await _api.postMultipart(
      AppConstants.facesRegister,
      {'name': name},
      imageFile,
      'file',
    );
  }
}
