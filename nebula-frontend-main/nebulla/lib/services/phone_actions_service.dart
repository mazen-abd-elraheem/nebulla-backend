import 'dart:io';
import 'package:android_intent_plus/android_intent.dart';
import 'package:android_intent_plus/flag.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/models.dart';
import 'nebula_repository.dart';

class PhoneActionsService {
  PhoneActionsService._();
  static PhoneActionsService? _instance;
  static PhoneActionsService get instance =>
      _instance ??= PhoneActionsService._();

  final _repo = NebulaRepository.instance;

  // ── Permissions ─────────────────────────────────────────────────────────────

  /// Check whether contacts permission is already granted
  Future<bool> hasContactsPermission() async {
    if (kIsWeb) return false;
    final status = await Permission.contacts.status;
    return status.isGranted;
  }

  /// Request contacts and phone permissions
  Future<bool> requestContactsPermission() async {
    if (kIsWeb) return false;

    // Use FlutterContacts permission flow or PermissionHandler
    final permission = await FlutterContacts.requestPermission(readonly: false);
    if (!permission) {
      final status = await Permission.contacts.request();
      return status.isGranted;
    }
    return true;
  }

  /// Request phone calling permission
  Future<bool> requestCallPermission() async {
    if (kIsWeb || !Platform.isAndroid) return true;
    final status = await Permission.phone.request();
    return status.isGranted;
  }

  /// Request SMS permission
  Future<bool> requestSmsPermission() async {
    if (kIsWeb || !Platform.isAndroid) return true;
    final status = await Permission.sms.request();
    return status.isGranted;
  }

  // ── Device Contacts Fetching ───────────────────────────────────────────────

  /// Fetch contacts from device address book
  Future<List<Contact>> fetchDeviceContacts({bool withPhotos = false}) async {
    final granted = await hasContactsPermission();
    if (!granted) {
      final req = await requestContactsPermission();
      if (!req) return [];
    }

    try {
      final contacts = await FlutterContacts.getContacts(
        withProperties: true,
        withPhoto: withPhotos,
        withThumbnail: withPhotos,
      );
      // Filter out contacts without any phone numbers
      return contacts.where((c) => c.phones.isNotEmpty).toList();
    } catch (e) {
      debugPrint('Error fetching device contacts: $e');
      return [];
    }
  }

  // ── Native Phone Actions (Calls, SMS, WhatsApp) ───────────────────────────

  /// Clean phone number for dialing
  String cleanPhoneNumber(String raw) {
    return raw.replaceAll(RegExp(r'[\s\-\(\)]'), '').trim();
  }

  /// Trigger native dialer / phone call
  Future<bool> makePhoneCall(String phoneNumber) async {
    final cleaned = cleanPhoneNumber(phoneNumber);
    if (cleaned.isEmpty) return false;

    final uri = Uri.parse('tel:$cleaned');
    try {
      if (await canLaunchUrl(uri)) {
        return await launchUrl(uri);
      }
      return false;
    } catch (e) {
      debugPrint('Failed to launch phone call: $e');
      return false;
    }
  }

  /// Trigger native SMS app with optional pre-filled text
  Future<bool> sendSms(String phoneNumber, [String message = '']) async {
    final cleaned = cleanPhoneNumber(phoneNumber);
    if (cleaned.isEmpty) return false;

    final uri = Uri.parse(
        'sms:$cleaned${message.isNotEmpty ? '?body=${Uri.encodeComponent(message)}' : ''}');
    try {
      if (await canLaunchUrl(uri)) {
        return await launchUrl(uri);
      }
      return false;
    } catch (e) {
      debugPrint('Failed to launch SMS: $e');
      return false;
    }
  }

  /// Launch WhatsApp with recipient and message
  Future<bool> sendWhatsApp(String phoneNumber, [String message = '']) async {
    final cleaned = cleanPhoneNumber(phoneNumber).replaceAll('+', '');
    if (cleaned.isEmpty) return false;

    final uri = Uri.parse(
        'https://wa.me/$cleaned${message.isNotEmpty ? '?text=${Uri.encodeComponent(message)}' : ''}');
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      debugPrint('Failed to launch WhatsApp: $e');
      return false;
    }
  }

  // ── Universal App Launching & Intent Dispatch ─────────────────────────────

  bool get isAndroid => !kIsWeb && Platform.isAndroid;

  Future<bool> _launchIntent({
    required String action,
    String? package,
    String? componentName,
    String? data,
    String? type,
    String? category,
    List<int>? flags,
    Map<String, dynamic>? arguments,
  }) async {
    if (!isAndroid) return false;
    try {
      final intent = AndroidIntent(
        action: action,
        package: package,
        componentName: componentName,
        data: data,
        type: type,
        category: category,
        flags: flags ?? [Flag.FLAG_ACTIVITY_NEW_TASK],
        arguments: arguments,
      );
      await intent.launch();
      return true;
    } catch (e) {
      debugPrint('Failed to launch Android Intent ($action): $e');
      return false;
    }
  }

  Future<bool> _launchUrlUri(String url,
      {LaunchMode mode = LaunchMode.externalApplication}) async {
    try {
      final uri = Uri.parse(url);
      if (await canLaunchUrl(uri)) {
        return await launchUrl(uri, mode: mode);
      }
      return false;
    } catch (e) {
      debugPrint('Failed to launch URL ($url): $e');
      return false;
    }
  }

  /// Launch any phone application by ID with optional search / playback query
  Future<bool> launchApp(String appId, {String? query}) async {
    final cleanApp = appId.toLowerCase().trim();
    final cleanQuery = query?.trim();

    switch (cleanApp) {
      case 'maps':
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          final qEnc = Uri.encodeComponent(cleanQuery);
          final intentSuccess = await _launchIntent(
            action: 'android.intent.action.VIEW',
            data: 'geo:0,0?q=$qEnc',
            package: 'com.google.android.apps.maps',
          );
          if (intentSuccess) return true;
          return await _launchUrlUri(
              'https://www.google.com/maps/search/?api=1&query=$qEnc');
        } else {
          final intentSuccess = await _launchIntent(
            action: 'android.intent.action.VIEW',
            data: 'geo:0,0',
            package: 'com.google.android.apps.maps',
          );
          if (intentSuccess) return true;
          return await _launchUrlUri('https://maps.google.com');
        }

      case 'youtube':
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          final qEnc = Uri.encodeComponent(cleanQuery);
          final intentSuccess = await _launchIntent(
            action: 'android.intent.action.VIEW',
            data: 'https://www.youtube.com/results?search_query=$qEnc',
            package: 'com.google.android.youtube',
          );
          if (intentSuccess) return true;
          return await _launchUrlUri(
              'https://www.youtube.com/results?search_query=$qEnc');
        } else {
          final intentSuccess = await _launchIntent(
            action: 'android.intent.action.MAIN',
            category: 'android.intent.category.LAUNCHER',
            package: 'com.google.android.youtube',
          );
          if (intentSuccess) return true;
          return await _launchUrlUri('https://www.youtube.com');
        }

      case 'spotify':
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          final qEnc = Uri.encodeComponent(cleanQuery);
          final uriSuccess = await _launchUrlUri('spotify:search:$qEnc');
          if (uriSuccess) return true;
          return await _launchUrlUri('https://open.spotify.com/search/$qEnc');
        } else {
          final uriSuccess = await _launchUrlUri('spotify:');
          if (uriSuccess) return true;
          final intentSuccess = await _launchIntent(
            action: 'android.intent.action.MAIN',
            category: 'android.intent.category.LAUNCHER',
            package: 'com.spotify.music',
          );
          if (intentSuccess) return true;
          return await _launchUrlUri('https://open.spotify.com');
        }

      case 'anghami':
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          final qEnc = Uri.encodeComponent(cleanQuery);
          final uriSuccess = await _launchUrlUri('anghami:search:$qEnc');
          if (uriSuccess) return true;
          return await _launchUrlUri('https://play.anghami.com/search/$qEnc');
        } else {
          final uriSuccess = await _launchUrlUri('anghami:');
          if (uriSuccess) return true;
          final intentSuccess = await _launchIntent(
            action: 'android.intent.action.MAIN',
            category: 'android.intent.category.LAUNCHER',
            package: 'com.anghami',
          );
          if (intentSuccess) return true;
          return await _launchUrlUri('https://play.anghami.com');
        }

      case 'whatsapp':
        final uriSuccess = await _launchUrlUri('whatsapp://');
        if (uriSuccess) return true;
        final intentSuccess = await _launchIntent(
          action: 'android.intent.action.MAIN',
          category: 'android.intent.category.LAUNCHER',
          package: 'com.whatsapp',
        );
        if (intentSuccess) return true;
        return await _launchUrlUri('https://web.whatsapp.com');

      case 'telegram':
        final uriSuccess = await _launchUrlUri('tg://resolve');
        if (uriSuccess) return true;
        final intentSuccess = await _launchIntent(
          action: 'android.intent.action.MAIN',
          category: 'android.intent.category.LAUNCHER',
          package: 'org.telegram.messenger',
        );
        if (intentSuccess) return true;
        return await _launchUrlUri('https://web.telegram.org');

      case 'facebook':
        final uriSuccess = await _launchUrlUri(
            'fb://facewebmodal/f?href=https://facebook.com');
        if (uriSuccess) return true;
        final intentSuccess = await _launchIntent(
          action: 'android.intent.action.MAIN',
          category: 'android.intent.category.LAUNCHER',
          package: 'com.facebook.katana',
        );
        if (intentSuccess) return true;
        return await _launchUrlUri('https://facebook.com');

      case 'instagram':
        final uriSuccess = await _launchUrlUri('instagram://app');
        if (uriSuccess) return true;
        final intentSuccess = await _launchIntent(
          action: 'android.intent.action.MAIN',
          category: 'android.intent.category.LAUNCHER',
          package: 'com.instagram.android',
        );
        if (intentSuccess) return true;
        return await _launchUrlUri('https://instagram.com');

      case 'tiktok':
        final uriSuccess = await _launchUrlUri('snssdk1128://');
        if (uriSuccess) return true;
        final intentSuccess = await _launchIntent(
          action: 'android.intent.action.MAIN',
          category: 'android.intent.category.LAUNCHER',
          package: 'com.zhiliaoapp.musically',
        );
        if (intentSuccess) return true;
        return await _launchUrlUri('https://www.tiktok.com');

      case 'twitter':
        final uriSuccess = await _launchUrlUri('twitter://');
        if (uriSuccess) return true;
        final intentSuccess = await _launchIntent(
          action: 'android.intent.action.MAIN',
          category: 'android.intent.category.LAUNCHER',
          package: 'com.twitter.android',
        );
        if (intentSuccess) return true;
        return await _launchUrlUri('https://x.com');

      case 'camera':
        return await _launchIntent(
              action: 'android.media.action.STILL_IMAGE_CAMERA',
            ) ||
            await _launchIntent(
              action: 'android.media.action.IMAGE_CAPTURE',
            );

      case 'gallery':
        return await _launchIntent(
              action: 'android.intent.action.VIEW',
              type: 'image/*',
            ) ||
            await _launchIntent(
              action: 'android.intent.action.MAIN',
              category: 'android.intent.category.APP_GALLERY',
            );

      case 'clock':
        return await _launchIntent(
              action: 'android.intent.action.SHOW_ALARMS',
            ) ||
            await _launchIntent(
              action: 'android.intent.action.MAIN',
              category: 'android.intent.category.LAUNCHER',
              package: 'com.google.android.deskclock',
            );

      case 'calculator':
        return await _launchIntent(
              action: 'android.intent.action.MAIN',
              category: 'android.intent.category.APP_CALCULATOR',
            ) ||
            await _launchIntent(
              action: 'android.intent.action.MAIN',
              category: 'android.intent.category.LAUNCHER',
              package: 'com.google.android.calculator',
            );

      case 'calendar':
        return await _launchIntent(
              action: 'android.intent.action.VIEW',
              data: 'content://com.android.calendar/time',
            ) ||
            await _launchIntent(
              action: 'android.intent.action.MAIN',
              category: 'android.intent.category.LAUNCHER',
              package: 'com.google.android.calendar',
            );

      case 'browser':
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          final qEnc = Uri.encodeComponent(cleanQuery);
          return await _launchUrlUri('https://www.google.com/search?q=$qEnc');
        } else {
          return await _launchUrlUri('https://www.google.com');
        }

      case 'email':
        return await _launchUrlUri('mailto:');

      case 'weather':
        final term = (cleanQuery != null && cleanQuery.isNotEmpty)
            ? 'الطقس $cleanQuery'
            : 'الطقس اليوم';
        return await _launchUrlUri(
            'https://www.google.com/search?q=${Uri.encodeComponent(term)}');

      case 'settings':
        return await _launchIntent(
          action: 'android.settings.SETTINGS',
        );

      case 'files':
        return await _launchIntent(
          action: 'android.intent.action.GET_CONTENT',
          type: '*/*',
        );

      case 'music':
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          return await launchApp('youtube', query: cleanQuery);
        } else {
          return await launchApp('spotify');
        }

      default:
        if (cleanQuery != null && cleanQuery.isNotEmpty) {
          return await _launchUrlUri(
              'https://www.google.com/search?q=${Uri.encodeComponent('$cleanApp $cleanQuery')}');
        }
        return await _launchUrlUri('$cleanApp://');
    }
  }

  // ── Bulk Sync from Phone to Backend ───────────────────────────────────────

  /// Sync contacts directly to Nebula backend
  Future<List<ContactModel>> syncDeviceContactsToBackend({
    List<Contact>? selectedContacts,
    bool replaceExisting = false,
  }) async {
    final list = selectedContacts ?? await fetchDeviceContacts();
    if (list.isEmpty) return [];

    final bulkItems = <ContactBulkSyncItem>[];

    for (final contact in list) {
      final name = contact.displayName.trim();
      if (name.isEmpty || contact.phones.isEmpty) continue;

      final primaryPhone = contact.phones.first.number.trim();
      if (primaryPhone.isEmpty) continue;

      // Detect smart relationship from Arabic names
      String? relationship;
      final lowerName = name.toLowerCase();
      if (lowerName.contains('ماما') ||
          lowerName.contains('امي') ||
          lowerName.contains('أمي') ||
          lowerName.contains('mom') ||
          lowerName.contains('mother')) {
        relationship = 'ماما';
      } else if (lowerName.contains('بابا') ||
          lowerName.contains('ابوي') ||
          lowerName.contains('أبي') ||
          lowerName.contains('dad') ||
          lowerName.contains('father')) {
        relationship = 'بابا';
      } else if (lowerName.contains('أخ') ||
          lowerName.contains('اخو') ||
          lowerName.contains('brother')) {
        relationship = 'أخ';
      } else if (lowerName.contains('أخت') ||
          lowerName.contains('اخت') ||
          lowerName.contains('sister')) {
        relationship = 'أخت';
      }

      bulkItems.add(
        ContactBulkSyncItem(
          name: name,
          phoneNumber: primaryPhone,
          aliases: relationship ?? '',
          relationship: relationship,
          isAllowlisted: true,
          requiresConfirmation: true,
          requiredLevel: 1,
          notifyOnMissed: false,
        ),
      );
    }

    if (bulkItems.isEmpty) return [];

    return await _repo.syncContacts(
      contacts: bulkItems,
      replaceExisting: replaceExisting,
    );
  }
}

