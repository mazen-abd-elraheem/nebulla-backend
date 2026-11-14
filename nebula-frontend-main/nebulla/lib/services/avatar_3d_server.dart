import 'dart:io';
import 'package:flutter/services.dart';

/// Lightweight embedded localhost HTTP server for streaming 3D GLB models and Three.js
/// assets into the WebView without CORS or file permission restrictions.
class Avatar3DServer {
  Avatar3DServer._();
  static final Avatar3DServer instance = Avatar3DServer._();

  HttpServer? _server;
  int? _port;
  bool _starting = false;

  int? get port => _port;
  String get baseUrl => _port != null ? 'http://127.0.0.1:$_port' : '';

  Future<void> ensureStarted() async {
    if (_server != null || _starting) return;
    _starting = true;
    try {
      _server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      _port = _server!.port;

      _server!.listen((HttpRequest request) async {
        final path = request.uri.path;
        request.response.headers.add('Access-Control-Allow-Origin', '*');
        request.response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS');

        if (request.method == 'OPTIONS') {
          request.response.statusCode = HttpStatus.ok;
          await request.response.close();
          return;
        }

        try {
          // Normalize requested asset path
          String assetKey;
          String contentType = 'application/octet-stream';

          if (path == '/' || path.endsWith('avatar_3d.html')) {
            assetKey = 'assets/3d/avatar_3d.html';
            contentType = 'text/html; charset=utf-8';
          } else if (path.endsWith('three.min.js')) {
            assetKey = 'assets/3d/three.min.js';
            contentType = 'application/javascript; charset=utf-8';
          } else if (path.endsWith('GLTFLoader.js')) {
            assetKey = 'assets/3d/GLTFLoader.js';
            contentType = 'application/javascript; charset=utf-8';
          } else if (path.endsWith('female_avatar.glb')) {
            assetKey = 'assets/models/female_avatar.glb';
            contentType = 'model/gltf-binary';
          } else {
            // Trim leading slash
            assetKey = path.startsWith('/') ? path.substring(1) : path;
          }

          // Try loading from Flutter Asset Bundle or local disk
          Uint8List bytes;
          final localFile = File(assetKey);
          if (await localFile.exists()) {
            bytes = await localFile.readAsBytes();
          } else {
            final data = await rootBundle.load(assetKey);
            bytes = data.buffer.asUint8List();
          }

          request.response.headers.contentType = ContentType.parse(contentType);
          request.response.statusCode = HttpStatus.ok;
          request.response.add(bytes);
          await request.response.close();
        } catch (_) {
          request.response.statusCode = HttpStatus.notFound;
          await request.response.close();
        }
      });
    } catch (_) {
    } finally {
      _starting = false;
    }
  }

  void stop() {
    _server?.close(force: true);
    _server = null;
    _port = null;
  }
}

