/// App-wide constants
class AppConstants {
  AppConstants._();

  static const String appName = 'نيبولا';
  static const String defaultBaseUrl = 'http://localhost:8000';
  static const String prefBaseUrl = 'base_url';
  static const String prefToken = 'auth_token';
  static const String prefDeviceName = 'device_name';

  // WebSocket paths
  static String wsPhone(String base) =>
      '${base.replaceFirst('http', 'ws')}/ws/phone';

  // API paths
  static const String authToken = '/api/v1/auth/token';
  static const String authMe = '/api/v1/auth/me';
  static const String deviceStatus = '/api/v1/devices/status';
  static const String devices = '/api/v1/devices/';
  static const String personalities = '/api/v1/personalities/';
  static const String memories = '/api/v1/memories/';
  static const String memoriesSearch = '/api/v1/memories/search';
  static const String conversations = '/api/v1/conversations/';
  static const String chat = '/api/v1/conversations/chat';
  static const String signals = '/api/v1/signals/';
  static const String calibration = '/api/v1/calibration/';
  static const String calibrationReset = '/api/v1/calibration/reset';
  static const String voiceCloneSamples = '/api/v1/voice-clone/samples';
  static const String voiceCloneSynthesize = '/api/v1/voice-clone/synthesize';
  static const String voiceCloneTest = '/api/v1/voice-clone/test';
  static const String settings = '/api/v1/settings/';
  static const String settingsProviders = '/api/v1/settings/providers';
  static const String diagnosticsStatus = '/api/v1/diagnostics/status';
  static const String diagnosticsServoTest = '/api/v1/diagnostics/servo/test';
  static const String diagnosticsServoHomeAll =
      '/api/v1/diagnostics/servo/home-all';
  static const String diagnosticsMotorTest = '/api/v1/diagnostics/motor/test';
  static const String diagnosticsLed = '/api/v1/diagnostics/led';
  static const String diagnosticsSensorDistance =
      '/api/v1/diagnostics/sensor/distance';
  static const String diagnosticsEmergencyStop =
      '/api/v1/diagnostics/emergency-stop';
  static const String facesRegister = '/api/v1/faces/register';
  static const String health = '/health';
}
