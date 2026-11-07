import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class OfflineSavedBanner extends StatelessWidget {
  final bool visible;

  const OfflineSavedBanner({super.key, required this.visible});

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
      color: AppTheme.successGreen.withValues(alpha: 0.15),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.check_circle, size: 14, color: AppTheme.successGreen),
          SizedBox(width: 6),
          Text(
            '✓ Guardado en este dispositivo (persistido)',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: AppTheme.successGreen,
            ),
          ),
        ],
      ),
    );
  }
}
