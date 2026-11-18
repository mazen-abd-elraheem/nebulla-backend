import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../services/locale_service.dart';

/// Glowing neon card with optional gradient border
class NebulaCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final Color? borderColor;
  final bool glowing;

  const NebulaCard({
    super.key,
    required this.child,
    this.padding,
    this.borderColor,
    this.glowing = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding ?? const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: AppColors.cardGradient,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: borderColor ?? AppColors.cardBorder,
          width: glowing ? 1.5 : 1,
        ),
        boxShadow: glowing
            ? [
                BoxShadow(
                  color: (borderColor ?? AppColors.teal).withValues(alpha: 0.2),
                  blurRadius: 16,
                  spreadRadius: 2,
                ),
              ]
            : null,
      ),
      child: child,
    );
  }
}

/// Teal gradient primary button
class NebulaPrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  final bool loading;
  final IconData? icon;

  const NebulaPrimaryButton({
    super.key,
    required this.label,
    this.onTap,
    this.loading = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: loading ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        height: 54,
        decoration: BoxDecoration(
          gradient: onTap != null
              ? AppColors.tealGradient
              : const LinearGradient(
                  colors: [AppColors.tealDim, AppColors.tealDim]),
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            if (onTap != null)
              BoxShadow(
                color: AppColors.teal.withValues(alpha: 0.35),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
          ],
        ),
        child: Center(
          child: loading
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    color: AppColors.bg,
                  ),
                )
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (icon != null) ...[
                      Icon(icon, color: AppColors.bg, size: 20),
                      const SizedBox(width: 8),
                    ],
                    Text(
                      label,
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        color: AppColors.bg,
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

/// Red danger button for emergency stop
class NebulaDangerButton extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  final IconData? icon;

  const NebulaDangerButton({
    super.key,
    required this.label,
    this.onTap,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 54,
        decoration: BoxDecoration(
          color: const Color(0xFF2A0D18),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFFF3D60), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFFFF3D60).withValues(alpha: 0.22),
              blurRadius: 16,
              spreadRadius: 1,
            ),
          ],
        ),
        child: Center(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, color: const Color(0xFFFF4D6D), size: 22),
                const SizedBox(width: 8),
              ],
              Text(
                label,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  color: Color(0xFFFF6584),
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Status dot with color and label
class StatusDot extends StatelessWidget {
  final bool connected;
  final String label;

  const StatusDot({super.key, required this.connected, required this.label});

  @override
  Widget build(BuildContext context) {
    final color = connected ? AppColors.success : const Color(0xFF94A3B8);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            boxShadow: connected
                ? [
                    BoxShadow(
                        color: color.withValues(alpha: 0.6), blurRadius: 6)
                  ]
                : null,
          ),
        ),
        const SizedBox(width: 6),
        Text(label,
            style: TextStyle(
                color: color, fontSize: 13, fontFamily: 'Cairo')),
      ],
    );
  }
}

/// Section header with teal left border
class SectionHeader extends StatelessWidget {
  final String title;
  final Widget? trailing;

  const SectionHeader({super.key, required this.title, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 3.5,
          height: 18,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF00D4E8), Color(0xFF0891B2)],
            ),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
        ),
        ?trailing,
      ],
    );
  }
}

/// Loading overlay
class LoadingOverlay extends StatelessWidget {
  final String? message;

  const LoadingOverlay({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.bg.withValues(alpha: 0.75),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: AppColors.teal),
            if (message != null) ...[
              const SizedBox(height: 16),
              Text(message!,
                  style: const TextStyle(
                      color: AppColors.textSecondary, fontFamily: 'Cairo')),
            ],
          ],
        ),
      ),
    );
  }
}

/// Clean inline field error badge displayed directly above or below input fields
/// instead of displaying floating snackbars / toasts.
class InlineFieldError extends StatelessWidget {
  final String message;
  final EdgeInsetsGeometry margin;

  const InlineFieldError({
    super.key,
    required this.message,
    this.margin = const EdgeInsets.only(bottom: 8),
  });

  @override
  Widget build(BuildContext context) {
    if (message.trim().isEmpty) return const SizedBox.shrink();

    return Container(
      margin: margin,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFFECACA), width: 1.2),
      ),
      child: Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              color: Color(0xFFEF4444),
              size: 16,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFFB91C1C),
                  height: 1.35,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Convert any raw technical, plugin, or server error string into a clean,
/// human-friendly UI/UX message in the active language.
String sanitizeUiErrorMessage(String raw) {
  final t = LocaleService.instance.tr;
  final trimmed = raw.trim();
  if (trimmed.isEmpty) {
    return t(
      'حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى.',
      'Something went wrong. Please try again.',
    );
  }

  final lower = trimmed.toLowerCase();

  if (lower.contains('missingpluginexception') ||
      lower.contains('no implementation found') ||
      lower.contains('unimplementederror')) {
    if (lower.contains('contact') || trimmed.contains('جهات الاتصال')) {
      return t(
        'مزامنة دليل الموبايل متاحة على الهاتف فقط، يمكنك إضافة جهات الاتصال من زر «جهة جديدة».',
        'Phone book sync is only available on mobile. Use "New Contact" to add contacts manually.',
      );
    }
    return t(
      'هذه الميزة غير مدعومة على هذا الجهاز حالياً.',
      'This feature is not supported on this device.',
    );
  }

  if (lower.contains('socketexception') ||
      lower.contains('connection refused') ||
      lower.contains('failed host lookup') ||
      lower.contains('network is unreachable') ||
      lower.contains('clientexception')) {
    return t(
      'تعذر الاتصال حالياً، تأكد من اتصالك بالشبكة وحاول مرة أخرى.',
      'Unable to connect right now. Please check your network and try again.',
    );
  }

  if (lower.contains('timeoutexception') || lower.contains('timed out')) {
    return t(
      'استغرق الطلب وقتاً أطول من المعتاد، يرجى المحاولة مرة أخرى.',
      'The request timed out. Please try again.',
    );
  }

  if (lower.contains('unauthorized') || lower.contains('status 401') || lower.contains('(401)')) {
    return t(
      'انتهت جلستك الحالية، يرجى تسجيل الدخول مرة أخرى.',
      'Your session has expired. Please sign in again.',
    );
  }

  if (lower.contains('forbidden') || lower.contains('status 403') || lower.contains('(403)')) {
    return t(
      'ليست لديك صلاحية لتنفيذ هذا الإجراء.',
      'You do not have permission to perform this action.',
    );
  }

  if (lower.contains('internal server error') ||
      lower.contains('status 500') ||
      lower.contains('(500)') ||
      lower.contains('bad gateway') ||
      lower.contains('service unavailable')) {
    return t(
      'حدث خطأ مؤقت، يرجى المحاولة مرة أخرى بعد قليل.',
      'A temporary issue occurred. Please try again shortly.',
    );
  }

  // Strip raw technical exception tails (e.g. "رسالة: Exception: ...", URLs, channels, Dart errors)
  final hasTechTokens = RegExp(
    r'(Exception|Error|Throwable|PlatformException|FormatException|HttpException|ApiException|github\.com/|package:|http://|https://|errno|OS Error|channel\s+\S+|Instance of\s+)',
    caseSensitive: false,
  ).hasMatch(trimmed);

  if (hasTechTokens) {
    final colonIdx = trimmed.indexOf(':');
    if (colonIdx > 3) {
      final prefix = trimmed.substring(0, colonIdx).trim();
      final prefixHasArabic = RegExp(r'[\u0600-\u06FF]').hasMatch(prefix);
      final prefixIsClean = !RegExp(
        r'(Exception|Error|http|package|channel)',
        caseSensitive: false,
      ).hasMatch(prefix);
      if (prefixIsClean && (LocaleService.instance.isArabic ? prefixHasArabic : !prefixHasArabic)) {
        return '$prefix.';
      }
    }
    return t(
      'تعذر إتمام العملية حالياً، يرجى المحاولة مرة أخرى.',
      'Could not complete the action right now. Please try again.',
    );
  }

  return trimmed;
}

/// Snackbar helpers — styled to match the light futuristic UI cards
void showSuccessSnackbar(BuildContext context, String message) {
  ScaffoldMessenger.of(context).hideCurrentSnackBar();
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      elevation: 4,
      backgroundColor: Colors.white,
      behavior: SnackBarBehavior.floating,
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 94),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Color(0xFFA7F3D0), width: 1.3),
      ),
      content: Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: Row(
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: const Color(0xFFECFDF5),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.check_circle_rounded,
                color: Color(0xFF10B981),
                size: 18,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF0F172A),
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

void showErrorSnackbar(BuildContext context, String message) {
  final cleanMessage = sanitizeUiErrorMessage(message);
  ScaffoldMessenger.of(context).hideCurrentSnackBar();
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      elevation: 4,
      backgroundColor: Colors.white,
      behavior: SnackBarBehavior.floating,
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 94),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Color(0xFFFECACA), width: 1.3),
      ),
      content: Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: Row(
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: const Color(0xFFFEF2F2),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.error_outline_rounded,
                color: Color(0xFFEF4444),
                size: 18,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                cleanMessage,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF0F172A),
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
