import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';

/// Canonical GAGAvatar visual styles shared across Home Studio and Profile Studio.
const List<Map<String, String>> kAvatarStyles = [
  {'id': 'realistic', 'label': 'واقعي 3D'},
  {'id': 'studio_3d', 'label': 'إضاءة استوديو'},
  {'id': 'stylized', 'label': 'كرتون ناعم'},
];

/// Canonical face-emoji test prompts used to exercise GAGAvatar neural expressions + mouth motion.
const List<Map<String, String>> kAvatarEmojiTests = [
  {'emoji': '😊', 'expr': 'happy', 'sample': 'أهلاً بيك، مبسوط إني معاك النهاردة!'},
  {'emoji': '😂', 'expr': 'laugh', 'sample': 'هههه دي نكتة جامدة جداً الصراحة!'},
  {'emoji': '😍', 'expr': 'love', 'sample': 'سعيد جداً إني بكلمك وبنسمع صوتك.'},
  {'emoji': '😮', 'expr': 'surprised', 'sample': 'معقولة؟ ده خبر مفاجئ بجد!'},
  {'emoji': '😢', 'expr': 'sad', 'sample': 'حزين شوية عشان الموضوع ده، بس كله هيتحل.'},
  {'emoji': '😡', 'expr': 'angry', 'sample': 'لا ده موضوع محتاج واقفة جد فعلاً!'},
  {'emoji': '🤔', 'expr': 'thinking', 'sample': 'خليني أفكر معاك لحظة في أحسن حل.'},
  {'emoji': '😉', 'expr': 'wink', 'sample': 'طيب يا سيدي، متفقين على طول!'},
  {'emoji': '😴', 'expr': 'sleepy', 'sample': 'اليوم كان طويل شوية، بس معاك صاحي.'},
];

/// Cross-platform photo picker that supports mobile Camera/Gallery and Windows Desktop file chooser.
Future<File?> pickAvatarPhotoFile({
  bool preferCamera = false,
  ImagePicker? picker,
}) async {
  final isDesktop = Platform.isWindows || Platform.isLinux || Platform.isMacOS;
  if (!isDesktop) {
    final activePicker = picker ?? ImagePicker();
    try {
      final picked = await activePicker.pickImage(
        source: preferCamera ? ImageSource.camera : ImageSource.gallery,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 90,
      );
      if (picked != null) return File(picked.path);
      return null;
    } catch (_) {
      // Fall through to FilePicker if camera delegate isn't available on host
    }
  }

  final res = await FilePicker.pickFiles(
    type: FileType.image,
    dialogTitle: 'اختر صورة واضحة للوجه (GAGAvatar)',
  );
  if (res.isEmpty) return null;
  final path = res.first.path;
  if (path == null || path.isEmpty) return null;
  return File(path);
}
