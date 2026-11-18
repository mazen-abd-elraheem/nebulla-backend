class AvatarLandmarks {
  final List<double> leftEye;
  final List<double> rightEye;
  final List<double> nose;
  final List<double> mouth;
  final double eyeWidth;
  final double mouthWidth;

  const AvatarLandmarks({
    this.leftEye = const [0.38, 0.42],
    this.rightEye = const [0.62, 0.42],
    this.nose = const [0.50, 0.56],
    this.mouth = const [0.50, 0.72],
    this.eyeWidth = 0.11,
    this.mouthWidth = 0.22,
  });

  factory AvatarLandmarks.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const AvatarLandmarks();
    List<double> pair(dynamic v, List<double> fallback) {
      if (v is List && v.length >= 2) {
        return [(v[0] as num).toDouble(), (v[1] as num).toDouble()];
      }
      return fallback;
    }

    return AvatarLandmarks(
      leftEye: pair(json['left_eye'], const [0.38, 0.42]),
      rightEye: pair(json['right_eye'], const [0.62, 0.42]),
      nose: pair(json['nose'], const [0.50, 0.56]),
      mouth: pair(json['mouth'], const [0.50, 0.72]),
      eyeWidth: (json['eye_width'] as num?)?.toDouble() ?? 0.11,
      mouthWidth: (json['mouth_width'] as num?)?.toDouble() ?? 0.22,
    );
  }
}

class AvatarProfileModel {
  final int id;
  final int? userId;
  final int? personalityId;
  final String? name;
  final String engine;
  final String style;
  final String status; // 'pending_review' | 'approved' | 'rejected'
  final bool isActive;
  final int attemptNumber;
  final String? rejectionReason;
  final String previewUrl;
  final String sourcePhotoUrl;
  final Map<String, String> sprites;
  final Map<String, List<String>> mouthFrames;
  final String? blinkSpriteUrl;
  final AvatarLandmarks landmarks;
  final String? updatedAt;

  const AvatarProfileModel({
    required this.id,
    this.userId,
    this.personalityId,
    this.name,
    required this.engine,
    required this.style,
    required this.status,
    required this.isActive,
    required this.attemptNumber,
    this.rejectionReason,
    required this.previewUrl,
    required this.sourcePhotoUrl,
    this.sprites = const {},
    this.mouthFrames = const {},
    this.blinkSpriteUrl,
    this.landmarks = const AvatarLandmarks(),
    this.updatedAt,
  });

  bool get isGagAvatar =>
      previewUrl.isNotEmpty &&
      (engine == 'gagavatar' ||
          engine == 'gagavatar_remote' ||
          engine == 'local_face_3d' ||
          engine == 'user_portrait');

  String withCacheBust(String path) {
    if (path.isEmpty) return path;
    final tag = Uri.encodeQueryComponent('${attemptNumber}_${updatedAt ?? id}');
    final sep = path.contains('?') ? '&' : '?';
    return '$path${sep}v=$tag';
  }

  /// Pick the exact backend-rendered frame URL for expression, jaw opening level (0..3), or blink.
  String frameForState({
    required String emotion,
    int mouthLevel = 0,
    bool blinking = false,
  }) {
    if (blinking) {
      final blink = blinkSpriteUrl ?? sprites['blink'];
      if (blink != null && blink.isNotEmpty) return withCacheBust(blink);
    }
    if (mouthLevel > 0 && mouthFrames.isNotEmpty) {
      final levels = mouthFrames[emotion] ?? mouthFrames['neutral'];
      if (levels != null && levels.isNotEmpty) {
        final idx = mouthLevel.clamp(0, levels.length - 1);
        return withCacheBust(levels[idx]);
      }
    }
    return withCacheBust(sprites[emotion] ?? sprites['neutral'] ?? previewUrl);
  }

  factory AvatarProfileModel.fromUrl(String url, {String name = 'المستخدم'}) {
    final match = RegExp(r'/avatar/(\d+)').firstMatch(url);
    final id = match != null ? int.tryParse(match.group(1)!) ?? 1 : 1;
    final prefix = '/api/v1/avatar/$id';

    const expressions = [
      'neutral',
      'happy',
      'laugh',
      'love',
      'sad',
      'surprised',
      'angry',
      'thinking',
      'wink',
      'sleepy',
      'wave',
      'like',
    ];

    final sprites = <String, String>{
      'blink': '$prefix/sprite/blink',
    };
    final mouthFrames = <String, List<String>>{};

    for (final exp in expressions) {
      sprites[exp] = '$prefix/sprite/$exp';
      mouthFrames[exp] = [
        '$prefix/mouth/$exp/0',
        '$prefix/mouth/$exp/1',
        '$prefix/mouth/$exp/2',
        '$prefix/mouth/$exp/3',
      ];
    }

    return AvatarProfileModel(
      id: id,
      name: name,
      engine: 'local_face_3d',
      style: 'realistic',
      status: 'approved',
      isActive: true,
      attemptNumber: 1,
      previewUrl: url.isNotEmpty ? url : '$prefix/preview',
      sourcePhotoUrl: '$prefix/source',
      sprites: sprites,
      mouthFrames: mouthFrames,
      blinkSpriteUrl: '$prefix/sprite/blink',
    );
  }

  factory AvatarProfileModel.fromJson(Map<String, dynamic> json) {
    final rawSprites = json['sprites'];
    final sprites = <String, String>{};
    if (rawSprites is Map) {
      rawSprites.forEach((k, v) {
        if (v != null) sprites[k.toString()] = v.toString();
      });
    }

    final rawMouthFrames = json['mouth_frames'];
    final mouthFrames = <String, List<String>>{};
    if (rawMouthFrames is Map) {
      rawMouthFrames.forEach((k, v) {
        if (v is List) {
          mouthFrames[k.toString()] = v.map((e) => e.toString()).toList();
        }
      });
    }

    return AvatarProfileModel(
      id: (json['id'] as num).toInt(),
      userId: (json['user_id'] as num?)?.toInt(),
      personalityId: (json['personality_id'] as num?)?.toInt(),
      name: json['name'] as String?,
      engine: (json['engine'] as String?) ?? 'gagavatar',
      style: (json['style'] as String?) ?? 'realistic',
      status: (json['status'] as String?) ?? 'pending_review',
      isActive: (json['is_active'] as bool?) ?? false,
      attemptNumber: (json['attempt_number'] as num?)?.toInt() ?? 1,
      rejectionReason: json['rejection_reason'] as String?,
      previewUrl: (json['preview_url'] as String?) ?? '',
      sourcePhotoUrl: (json['source_photo_url'] as String?) ?? '',
      sprites: sprites,
      mouthFrames: mouthFrames,
      blinkSpriteUrl: (json['blink_sprite_url'] as String?) ?? sprites['blink'],
      landmarks: AvatarLandmarks.fromJson(
        json['landmarks'] is Map<String, dynamic>
            ? json['landmarks'] as Map<String, dynamic>
            : null,
      ),
      updatedAt: json['updated_at'] as String?,
    );
  }
}

