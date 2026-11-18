import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../core/constants.dart';
import 'storage_service.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

class ApiService {
  ApiService._();
  static ApiService? _instance;
  static ApiService get instance => _instance ??= ApiService._();

  String get _base {
    final raw = StorageService.instance.getBaseUrl();
    if (Platform.isAndroid &&
        (raw.contains('localhost') || raw.contains('127.0.0.1'))) {
      return raw
          .replaceAll('localhost', '10.0.2.2')
          .replaceAll('127.0.0.1', '10.0.2.2');
    }
    return raw.replaceAll('localhost', '127.0.0.1');
  }
  String? get _token => StorageService.instance.getToken();

  String get _deviceType {
    if (Platform.isAndroid || Platform.isIOS) return 'mobile';
    return 'desktop';
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'X-Device-Type': _deviceType,
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Uri _uri(String path, [Map<String, dynamic>? params]) {
    final uri = Uri.parse('$_base$path');
    if (params != null && params.isNotEmpty) {
      return uri.replace(
          queryParameters:
              params.map((k, v) => MapEntry(k, v.toString())));
    }
    return uri;
  }

  Future<dynamic> get(String path, [Map<String, dynamic>? params]) async {
    final response = await http
        .get(_uri(path, params), headers: _headers)
        .timeout(const Duration(seconds: 15));
    return _handle(response);
  }

  Future<dynamic> post(String path, [Map<String, dynamic>? body]) async {
    final response = await http
        .post(_uri(path),
            headers: _headers, body: body != null ? jsonEncode(body) : null)
        .timeout(const Duration(seconds: 30));
    return _handle(response);
  }

  Future<dynamic> patch(String path, Map<String, dynamic> body) async {
    final response = await http
        .patch(_uri(path),
            headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));
    return _handle(response);
  }

  Future<dynamic> put(String path, Map<String, dynamic> body) async {
    final response = await http
        .put(_uri(path), headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));
    return _handle(response);
  }

  Future<void> delete(String path) async {
    final response = await http
        .delete(_uri(path), headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 204 && response.statusCode != 200) {
      _handle(response);
    }
  }

  /// Multipart POST for file uploads
  Future<dynamic> postMultipart(
    String path,
    Map<String, String> fields,
    File file,
    String fileField,
  ) async {
    final request =
        http.MultipartRequest('POST', _uri(path));
    if (_token != null) {
      request.headers['Authorization'] = 'Bearer $_token';
    }
    fields.forEach((k, v) => request.fields[k] = v);
    request.files
        .add(await http.MultipartFile.fromPath(fileField, file.path));
    final streamed = await request.send().timeout(const Duration(seconds: 180));
    final response = await http.Response.fromStream(streamed);
    return _handle(response);
  }

  /// Multipart POST with optional file upload (for recreate/regenerate flows)
  Future<dynamic> postMultipartOptionalFile(
    String path,
    Map<String, String> fields, {
    File? file,
    String fileField = 'file',
  }) async {
    final request = http.MultipartRequest('POST', _uri(path));
    if (_token != null) {
      request.headers['Authorization'] = 'Bearer $_token';
    }
    fields.forEach((k, v) => request.fields[k] = v);
    if (file != null) {
      request.files.add(await http.MultipartFile.fromPath(fileField, file.path));
    }
    final streamed = await request.send().timeout(const Duration(seconds: 180));
    final response = await http.Response.fromStream(streamed);
    return _handle(response);
  }

  String resolveUrl(String pathOrUrl) {
    if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
      return pathOrUrl.replaceAll('localhost', '127.0.0.1');
    }
    final rawBase = _base.replaceAll('localhost', '127.0.0.1');
    final base = rawBase.endsWith('/') ? rawBase.substring(0, rawBase.length - 1) : rawBase;
    final cleanPath = pathOrUrl.startsWith('/') ? pathOrUrl : '/$pathOrUrl';
    return '$base$cleanPath';
  }

  String _cleanValidationMessage(String raw) {
    var text = raw.trim();
    for (final prefix in [
      'Value error, ',
      'Value error:',
      'Assertion failed, ',
      'Assertion failed:',
    ]) {
      if (text.startsWith(prefix)) {
        text = text.substring(prefix.length).trim();
      }
    }

    final lower = text.toLowerCase();
    if (lower.contains('not a valid email')) {
      return 'صيغة البريد الإلكتروني غير صحيحة.';
    }
    if (lower.contains('at least 8 characters')) {
      return 'كلمة المرور لازم تكون 8 خانات على الأقل.';
    }
    if (lower.contains('at least 6 characters')) {
      return 'كلمة المرور لازم تكون 6 خانات على الأقل.';
    }
    if (lower.contains('at least 2 characters')) {
      return 'الاسم لازم يكون حرفين على الأقل.';
    }
    if (lower.contains('field required')) {
      return 'يرجى ملء جميع الحقول المطلوبة.';
    }
    if (lower.contains('string should have at most')) {
      return 'النص المدخل أطول من الحد المسموح.';
    }
    return text;
  }

  String _extractReadableError(dynamic detail, int statusCode) {
    if (detail is String && detail.trim().isNotEmpty) {
      return _cleanValidationMessage(detail);
    }

    if (detail is List && detail.isNotEmpty) {
      final messages = <String>[];
      for (final item in detail) {
        if (item is Map) {
          String? extracted;
          final ctx = item['ctx'];
          if (ctx is Map && ctx['error'] != null) {
            extracted = ctx['error'].toString();
          } else if (item['msg'] != null) {
            extracted = item['msg'].toString();
          }
          if (extracted != null && extracted.trim().isNotEmpty) {
            final clean = _cleanValidationMessage(extracted);
            if (!messages.contains(clean)) {
              messages.add(clean);
            }
          }
        } else if (item != null) {
          final clean = _cleanValidationMessage(item.toString());
          if (clean.isNotEmpty && !messages.contains(clean)) {
            messages.add(clean);
          }
        }
      }
      if (messages.isNotEmpty) {
        return messages.join('\n');
      }
    }

    if (statusCode == 401) {
      return 'انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى.';
    }
    if (statusCode == 403) {
      return 'ليس لديك صلاحية لتنفيذ هذا الإجراء.';
    }
    if (statusCode == 404) {
      return 'العنصر المطلوب غير موجود.';
    }
    if (statusCode >= 500) {
      return 'حدث خطأ مؤقت في الخادم، حاول مرة أخرى.';
    }
    return 'حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى.';
  }

  dynamic _handle(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(utf8.decode(response.bodyBytes));
    }
    String msg;
    try {
      final rawText = utf8.decode(response.bodyBytes);
      final body = jsonDecode(rawText);
      if (body is Map<String, dynamic>) {
        msg = _extractReadableError(
          body['detail'] ?? body['message'],
          response.statusCode,
        );
      } else {
        msg = _extractReadableError(body, response.statusCode);
      }
    } catch (_) {
      msg = _extractReadableError(null, response.statusCode);
    }
    if (response.statusCode == 401) {
      StorageService.instance.clearToken();
    }
    throw ApiException(response.statusCode, msg);
  }

  Future<bool> ping() async {
    try {
      await http
          .get(_uri(AppConstants.health))
          .timeout(const Duration(seconds: 5));
      return true;
    } catch (_) {
      return false;
    }
  }
}
