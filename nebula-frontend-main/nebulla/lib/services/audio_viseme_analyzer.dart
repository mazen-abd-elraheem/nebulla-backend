import 'dart:math';
import 'dart:typed_data';

/// The target visual shape of the mouth (Viseme) derived from acoustic features.
enum VisemeType {
  rest, // Mouth at rest / silent
  aa,   // Open jaw, wide (ah, aa, ha, ka)
  oo,   // Rounded lips, small aperture (o, oo, u, w)
  ee,   // Wide stretched lips, small vertical gap (ee, i, s, z)
  mbp,  // Bilabial closure (m, b, p)
  fv,   // Labiodental tuck (f, v)
}

/// Instantaneous mouth deformation parameters for rendering realistic lip motion.
class VisemeFrame {
  final VisemeType type;
  final double openness;     // 0.0 (closed) to 1.0 (fully open jaw)
  final double widthRatio;    // 0.8 (puckered) to 1.25 (wide smile)
  final double pucker;        // 0.0 (flat) to 1.0 (rounded circle)
  final double teethVisible;  // 0.0 to 1.0 visibility of upper teeth
  final double jawDrop;       // 0.0 to 1.0 physical jaw displacement

  const VisemeFrame({
    this.type = VisemeType.rest,
    this.openness = 0.0,
    this.widthRatio = 1.0,
    this.pucker = 0.0,
    this.teethVisible = 0.0,
    this.jawDrop = 0.0,
  });

  static const VisemeFrame neutral = VisemeFrame();

  /// Linearly interpolates between two viseme frames for smooth 60 FPS transitions.
  static VisemeFrame lerp(VisemeFrame a, VisemeFrame b, double t) {
    final clampedT = t.clamp(0.0, 1.0);
    return VisemeFrame(
      type: clampedT > 0.5 ? b.type : a.type,
      openness: a.openness + (b.openness - a.openness) * clampedT,
      widthRatio: a.widthRatio + (b.widthRatio - a.widthRatio) * clampedT,
      pucker: a.pucker + (b.pucker - a.pucker) * clampedT,
      teethVisible: a.teethVisible + (b.teethVisible - a.teethVisible) * clampedT,
      jawDrop: a.jawDrop + (b.jawDrop - a.jawDrop) * clampedT,
    );
  }
}

/// Client-side Audio DSP analyzer that converts raw audio bytes into
/// time-synchronized viseme animation frames without modifying backend.
class AudioVisemeAnalyzer {
  AudioVisemeAnalyzer._();
  static final AudioVisemeAnalyzer instance = AudioVisemeAnalyzer._();

  /// Analyzes audio bytes (WAV PCM or synthesized chunks) and generates
  /// a continuous timeline of visemes sampled at 20ms intervals (50 Hz).
  List<VisemeFrame> analyzeAudioTrack(Uint8List audioBytes, int durationMs) {
    if (audioBytes.isEmpty || durationMs <= 0) {
      return const [VisemeFrame.neutral];
    }

    final frameCount = max(1, durationMs ~/ 20); // 20ms steps
    final frames = <VisemeFrame>[];

    // Attempt to extract PCM samples if WAV format
    List<double> energyTrack = [];
    List<double> frequencyTrack = [];

    if (_isWavHeader(audioBytes)) {
      _extractWavFeatures(audioBytes, frameCount, energyTrack, frequencyTrack);
    }

    // If not raw WAV or extraction failed, generate acoustic simulation from duration
    if (energyTrack.length < frameCount) {
      _generateSyntheticFeatures(frameCount, energyTrack, frequencyTrack);
    }

    // Map acoustic energy and frequency to visemes
    for (int i = 0; i < frameCount; i++) {
      final energy = energyTrack[i];
      final freq = frequencyTrack[i];

      if (energy < 0.06) {
        frames.add(VisemeFrame.neutral);
        continue;
      }

      // Classify phoneme family based on spectral centroid and energy
      VisemeType type;
      double openness;
      double widthRatio;
      double pucker;
      double teeth;

      if (freq > 0.65) {
        // High frequency consonants / sibilants / front vowels (ee, s, t)
        type = VisemeType.ee;
        openness = (energy * 0.45).clamp(0.15, 0.55);
        widthRatio = 1.15 + (energy * 0.12);
        pucker = 0.0;
        teeth = 0.85;
      } else if (freq < 0.35) {
        // Low frequency back vowels / labials (oo, u, w, o)
        type = VisemeType.oo;
        openness = (energy * 0.7).clamp(0.2, 0.75);
        widthRatio = 0.84 - (energy * 0.08);
        pucker = 0.85;
        teeth = 0.2;
      } else if (energy > 0.55) {
        // High amplitude open vowels (aa, ah)
        type = VisemeType.aa;
        openness = (energy * 0.95).clamp(0.3, 1.0);
        widthRatio = 1.02;
        pucker = 0.1;
        teeth = 0.7;
      } else if (i % 6 == 0 && energy < 0.25) {
        // Bilabial closure between syllables (m, b, p)
        type = VisemeType.mbp;
        openness = 0.02;
        widthRatio = 0.96;
        pucker = 0.05;
        teeth = 0.0;
      } else {
        // Mid vowel / conversational articulation
        type = VisemeType.aa;
        openness = (energy * 0.65).clamp(0.2, 0.7);
        widthRatio = 1.0;
        pucker = 0.2;
        teeth = 0.45;
      }

      frames.add(VisemeFrame(
        type: type,
        openness: openness,
        widthRatio: widthRatio,
        pucker: pucker,
        teethVisible: teeth,
        jawDrop: openness * 0.75,
      ));
    }

    return frames;
  }

  bool _isWavHeader(Uint8List bytes) {
    if (bytes.length < 44) return false;
    return bytes[0] == 0x52 && bytes[1] == 0x49 && bytes[2] == 0x46 && bytes[3] == 0x46; // "RIFF"
  }

  void _extractWavFeatures(
    Uint8List bytes,
    int targetFrames,
    List<double> outEnergy,
    List<double> outFrequency,
  ) {
    try {
      final pcmStart = 44;
      final pcmLength = bytes.length - pcmStart;
      if (pcmLength <= 0) return;

      final samplesPerFrame = pcmLength ~/ targetFrames;
      if (samplesPerFrame < 2) return;

      final byteData = ByteData.sublistView(bytes, pcmStart);

      for (int f = 0; f < targetFrames; f++) {
        final startOffset = f * samplesPerFrame;
        final endOffset = min(pcmLength - 2, startOffset + samplesPerFrame);

        double sumSq = 0.0;
        int zeroCrossings = 0;
        int prevSample = 0;
        int count = 0;

        for (int b = startOffset; b < endOffset; b += 2) {
          if (b + 1 >= byteData.lengthInBytes) break;
          final sample = byteData.getInt16(b, Endian.little);
          sumSq += sample * sample;

          if (count > 0 && ((sample >= 0 && prevSample < 0) || (sample < 0 && prevSample >= 0))) {
            zeroCrossings++;
          }
          prevSample = sample;
          count++;
        }

        if (count > 0) {
          final rms = sqrt(sumSq / count);
          final normRms = (rms / 32768.0 * 2.8).clamp(0.0, 1.0);
          final zcr = (zeroCrossings / count).clamp(0.0, 1.0);

          outEnergy.add(normRms);
          outFrequency.add(zcr);
        } else {
          outEnergy.add(0.0);
          outFrequency.add(0.5);
        }
      }
    } catch (_) {
      outEnergy.clear();
      outFrequency.clear();
    }
  }

  void _generateSyntheticFeatures(
    int frameCount,
    List<double> outEnergy,
    List<double> outFrequency,
  ) {
    outEnergy.clear();
    outFrequency.clear();
    final random = Random(42);

    for (int i = 0; i < frameCount; i++) {
      final t = i * 0.02; // seconds
      // Syllable rate ~ 3.6 Hz with pauses every 1.4s
      final isPause = (t % 1.6) > 1.25;
      if (isPause) {
        outEnergy.add(0.0);
        outFrequency.add(0.4);
        continue;
      }

      final syllable = 0.5 + 0.5 * sin(2 * pi * 3.6 * t);
      final consonant = 0.3 * sin(2 * pi * 11.2 * t);
      final jitter = (random.nextDouble() - 0.5) * 0.15;
      final energy = (syllable + consonant + jitter).clamp(0.0, 1.0);

      final freq = (0.5 + 0.35 * sin(2 * pi * 2.1 * t + 1.2) + jitter).clamp(0.0, 1.0);

      outEnergy.add(energy);
      outFrequency.add(freq);
    }
  }
}
