// Models for Nebula API responses

class TokenResponse {
  final String accessToken;
  final String tokenType;
  final int expiresIn;

  TokenResponse({
    required this.accessToken,
    required this.tokenType,
    required this.expiresIn,
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
        accessToken: json['access_token'] as String,
        tokenType: json['token_type'] as String? ?? 'bearer',
        expiresIn: json['expires_in'] as int? ?? 28800,
      );
}

class Personality {
  final int id;
  final String name;
  final String? description;
  final String systemPrompt;
  final String dialect;
  final String languageMix;
  final String? voiceSamplePath;
  final bool isActive;

  Personality({
    required this.id,
    required this.name,
    this.description,
    required this.systemPrompt,
    required this.dialect,
    required this.languageMix,
    this.voiceSamplePath,
    required this.isActive,
  });

  factory Personality.fromJson(Map<String, dynamic> json) => Personality(
        id: json['id'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        systemPrompt: json['system_prompt'] as String? ?? '',
        dialect: json['dialect'] as String? ?? 'cairo',
        languageMix: json['language_mix'] as String? ?? 'ar_en',
        voiceSamplePath: json['voice_sample_path'] as String?,
        isActive: json['is_active'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'description': description,
        'system_prompt': systemPrompt,
        'dialect': dialect,
        'language_mix': languageMix,
      };
}

class Memory {
  final int id;
  final String content;
  final int personalityId;
  final String source;
  final int importance;
  final String? createdAt;

  Memory({
    required this.id,
    required this.content,
    required this.personalityId,
    required this.source,
    required this.importance,
    this.createdAt,
  });

  factory Memory.fromJson(Map<String, dynamic> json) => Memory(
        id: json['id'] as int,
        content: json['content'] as String,
        personalityId: json['personality_id'] as int,
        source: json['source'] as String? ?? 'manual',
        importance: json['importance'] as int? ?? 5,
        createdAt: json['created_at'] as String?,
      );
}

class ChatMessage {
  final String role; // 'user' or 'assistant'
  final String content;
  final String? emotion;
  final double? latencyMs;

  ChatMessage({
    required this.role,
    required this.content,
    this.emotion,
    this.latencyMs,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        role: json['role'] as String? ?? 'assistant',
        content: json['content'] as String? ?? '',
        emotion: json['emotion'] as String?,
        latencyMs: (json['llm_latency_ms'] as num?)?.toDouble(),
      );
}

class DeviceStatus {
  final bool phoneConnected;
  final bool deskConnected;
  final bool esp32Connected;

  DeviceStatus({
    required this.phoneConnected,
    required this.deskConnected,
    required this.esp32Connected,
  });

  factory DeviceStatus.fromJson(Map<String, dynamic> json) {
    final channels = json['channels'] as Map<String, dynamic>? ?? {};
    return DeviceStatus(
      phoneConnected: channels['phone'] == 'connected',
      deskConnected: channels['desk'] == 'connected',
      esp32Connected: channels['esp32'] == 'connected',
    );
  }
}

class Signal {
  final int id;
  final String name;
  final String? description;
  final String jointCommandsJson;
  final String? emotionTag;

  Signal({
    required this.id,
    required this.name,
    this.description,
    required this.jointCommandsJson,
    this.emotionTag,
  });

  factory Signal.fromJson(Map<String, dynamic> json) => Signal(
        id: json['id'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        jointCommandsJson: json['joint_commands_json'] as String? ?? '[]',
        emotionTag: json['emotion_tag'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'description': description,
        'joint_commands_json': jointCommandsJson,
        'emotion_tag': emotionTag,
      };
}

class CalibrationEntry {
  final int servoId;
  final String? label;
  final double? minAngle;
  final double? maxAngle;
  final double? homeAngle;

  CalibrationEntry({
    required this.servoId,
    this.label,
    this.minAngle,
    this.maxAngle,
    this.homeAngle,
  });

  factory CalibrationEntry.fromJson(Map<String, dynamic> json) =>
      CalibrationEntry(
        servoId: json['servo_id'] as int,
        label: json['label'] as String?,
        minAngle: (json['min_angle'] as num?)?.toDouble(),
        maxAngle: (json['max_angle'] as num?)?.toDouble(),
        homeAngle: (json['home_angle'] as num?)?.toDouble(),
      );
}

class AppSettings {
  final String? sttProvider;
  final String? ttsProvider;
  final String? llmProvider;
  final String? llmModel;
  final String? llmBaseUrl;

  AppSettings({
    this.sttProvider,
    this.ttsProvider,
    this.llmProvider,
    this.llmModel,
    this.llmBaseUrl,
  });

  factory AppSettings.fromJson(Map<String, dynamic> json) => AppSettings(
        sttProvider: json['stt_provider'] as String?,
        ttsProvider: json['tts_provider'] as String?,
        llmProvider: json['llm_provider'] as String?,
        llmModel: json['llm_model'] as String?,
        llmBaseUrl: json['llm_base_url'] as String?,
      );

  Map<String, dynamic> toJson() => {
        if (sttProvider != null) 'stt_provider': sttProvider,
        if (ttsProvider != null) 'tts_provider': ttsProvider,
        if (llmProvider != null) 'llm_provider': llmProvider,
        if (llmModel != null) 'llm_model': llmModel,
        if (llmBaseUrl != null) 'llm_base_url': llmBaseUrl,
      };
}
