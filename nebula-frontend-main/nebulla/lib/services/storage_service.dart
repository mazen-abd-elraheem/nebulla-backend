import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/constants.dart';
import '../models/models.dart';

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
    await _prefs?.remove(AppConstants.prefUser);
  }

  Future<void> setUser(UserModel user) async {
    final str = jsonEncode(user.toJson());
    await _prefs?.setString(AppConstants.prefUser, str);
  }

  UserModel? getUser() {
    final str = _prefs?.getString(AppConstants.prefUser);
    if (str == null || str.isEmpty) return null;
    try {
      final map = jsonDecode(str) as Map<String, dynamic>;
      return UserModel.fromJson(map);
    } catch (_) {
      return null;
    }
  }

  Future<void> setSavedEmail(String email) async {
    await _prefs?.setString(AppConstants.prefSavedEmail, email);
  }

  String? getSavedEmail() => _prefs?.getString(AppConstants.prefSavedEmail);

  Future<void> setRememberMe(bool val) async {
    await _prefs?.setBool(AppConstants.prefRememberMe, val);
  }

  bool getRememberMe() =>
      _prefs?.getBool(AppConstants.prefRememberMe) ?? false;

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
