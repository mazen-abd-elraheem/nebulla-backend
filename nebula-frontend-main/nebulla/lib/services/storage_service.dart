import 'package:shared_preferences/shared_preferences.dart';
import '../core/constants.dart';

class StorageService {
  StorageService._();
  static StorageService? _instance;
  static StorageService get instance => _instance ??= StorageService._();

  SharedPreferences? _prefs;

  Future<void> init() async {
    _prefs ??= await SharedPreferences.getInstance();
  }

  Future<void> setToken(String token) async {
    await _prefs?.setString(AppConstants.prefToken, token);
  }

  String? getToken() => _prefs?.getString(AppConstants.prefToken);

  Future<void> clearToken() async {
    await _prefs?.remove(AppConstants.prefToken);
  }

  Future<void> setBaseUrl(String url) async {
    await _prefs?.setString(AppConstants.prefBaseUrl, url);
  }

  String getBaseUrl() =>
      _prefs?.getString(AppConstants.prefBaseUrl) ??
      AppConstants.defaultBaseUrl;

  Future<void> setDeviceName(String name) async {
    await _prefs?.setString(AppConstants.prefDeviceName, name);
  }

  String getDeviceName() =>
      _prefs?.getString(AppConstants.prefDeviceName) ?? 'nebula-app';
}
