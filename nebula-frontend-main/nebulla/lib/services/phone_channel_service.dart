import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../core/constants.dart';
import 'storage_service.dart';
import 'phone_actions_service.dart';

class PhoneChannelService {
  PhoneChannelService._();
  static PhoneChannelService? _instance;
  static PhoneChannelService get instance =>
      _instance ??= PhoneChannelService._();

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  bool _isConnecting = false;
  bool _isConnected = false;

  final _connectionController = StreamController<bool>.broadcast();
  Stream<bool> get connectionStream => _connectionController.stream;
  bool get isConnected => _isConnected;

  final _actions = PhoneActionsService.instance;
  final _store = StorageService.instance;

  void connect() {
    if (_isConnected || _isConnecting) return;
    _isConnecting = true;

    final baseUrl = _store.getBaseUrl();
    final pairingCode = _store.getPairingCode();
    final wsUrl = '${AppConstants.wsPhone(baseUrl)}?pairing_code=${Uri.encodeComponent(pairingCode)}';

    debugPrint('Connecting to Phone WebSocket: $wsUrl');

    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));

      _subscription = _channel!.stream.listen(
        (data) {
          if (!_isConnected) {
            _isConnected = true;
            _isConnecting = false;
            _connectionController.add(true);
            debugPrint('Phone WebSocket connected successfully.');
          }
          _handleIncomingMessage(data);
        },
        onError: (err) {
          debugPrint('Phone WebSocket error: $err');
          _handleDisconnect();
        },
        onDone: () {
          debugPrint('Phone WebSocket closed.');
          _handleDisconnect();
        },
        cancelOnError: true,
      );
    } catch (e) {
      debugPrint('Exception while connecting Phone WebSocket: $e');
      _handleDisconnect();
    }
  }

  void _handleDisconnect() {
    _isConnected = false;
    _isConnecting = false;
    _connectionController.add(false);
    _subscription?.cancel();
    _subscription = null;
    _channel = null;

    // Schedule auto-reconnect if token still exists
    if (_store.getToken() != null) {
      _reconnectTimer?.cancel();
      _reconnectTimer = Timer(const Duration(seconds: 4), () {
        if (!_isConnected && _store.getToken() != null) {
          connect();
        }
      });
    }
  }

  void disconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _subscription?.cancel();
    _subscription = null;
    try {
      _channel?.sink.close();
    } catch (_) {}
    _channel = null;
    _isConnected = false;
    _isConnecting = false;
    _connectionController.add(false);
  }

  Future<void> _handleIncomingMessage(dynamic raw) async {
    if (raw is! String) return; // Binary frames are camera/audio handled elsewhere

    try {
      final data = jsonDecode(raw);
      if (data is! Map<String, dynamic>) return;

      final type = data['t'] as String?;
      final actionId = data['id'] as int?;

      if (type == 'call' && actionId != null) {
        final number = data['number'] as String? ?? '';
        final success = await _actions.makePhoneCall(number);
        _sendActionResult(actionId, success);
      } else if (type == 'msg' && actionId != null) {
        final app = data['app'] as String? ?? 'sms';
        final number = data['number'] as String? ?? '';
        final text = data['text'] as String? ?? '';

        bool success = false;
        if (app == 'whatsapp') {
          success = await _actions.sendWhatsApp(number, text);
        } else {
          success = await _actions.sendSms(number, text);
        }
        _sendActionResult(actionId, success);
      } else if (type == 'app' && actionId != null) {
        final cmd = data['cmd'] as String? ?? 'open';
        final app = data['app'] as String? ?? '';
        final q = data['q'] as String?;

        if (cmd == 'open' && app.isNotEmpty) {
          final success = await _actions.launchApp(app, query: q);
          _sendActionResult(
              actionId, success, success ? null : 'failed_to_launch_app');
        } else {
          _sendActionResult(actionId, true);
        }
      }
    } catch (e) {
      debugPrint('Error handling phone WS message: $e');
    }
  }

  void _sendActionResult(int actionId, bool ok, [String? error]) {
    if (!_isConnected || _channel == null) return;
    try {
      final payload = <String, dynamic>{
        't': 'action_result',
        'id': actionId,
        'ok': ok,
      };
      if (error != null) {
        payload['error'] = error;
      }
      _channel!.sink.add(jsonEncode(payload));
    } catch (e) {
      debugPrint('Failed to send action result: $e');
    }
  }

  void sendCallState(String state) {
    if (!_isConnected || _channel == null) return;
    try {
      final payload = {
        't': 'call_state',
        'state': state, // 'idle', 'ringing', 'active', 'ended'
      };
      _channel!.sink.add(jsonEncode(payload));
    } catch (e) {
      debugPrint('Failed to send call state: $e');
    }
  }
}
