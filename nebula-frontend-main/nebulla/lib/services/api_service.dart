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
  String toString() => 'ApiException($statusCode): $message';
}

class ApiService {
  ApiService._();
  static ApiService? _instance;
  static ApiService get instance => _instance ??= ApiService._();

  String get _base => StorageService.instance.getBaseUrl();
  String? get _token => StorageService.instance.getToken();

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
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
    final streamed = await request.send().timeout(const Duration(seconds: 60));
    final response = await http.Response.fromStream(streamed);
    return _handle(response);
  }

  dynamic _handle(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(utf8.decode(response.bodyBytes));
    }
    String msg;
    try {
      final body = jsonDecode(response.body);
      msg = body['detail']?.toString() ?? response.body;
    } catch (_) {
      msg = response.body;
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
