import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/api_config.dart';
import '../data/models/profile.dart';
import '../services/api_service.dart';
import 'auth_provider.dart';

/// Owns the current user's profile fetched from /auth/profile/.
///
/// PATCH-only fields per backend contract: `name` (on User) and `phone`
/// (on Profile). Everything else is display-only.
class ProfileNotifier extends AsyncNotifier<Profile> {
  final ApiService _api = ApiService();

  @override
  Future<Profile> build() => _fetch();

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(_fetch);
  }

  Future<Profile> _fetch() async {
    final response = await _api.get(ApiConfig.profile);
    if (!response.success || response.data == null) {
      throw Exception(response.message ?? 'Failed to load profile');
    }
    return Profile.fromJson(response.data!);
  }

  /// Update name and/or phone. Returns true on success.
  /// Refreshes [authProvider] so the rest of the app sees the new name
  /// (greeting, More sheet header, etc.).
  Future<bool> save({String? name, String? phone}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (phone != null) body['phone'] = phone;
    if (body.isEmpty) return true;

    final response = await _api.patch(ApiConfig.profileUpdate, body);
    if (!response.success) {
      debugPrint('ProfileNotifier.update failed: ${response.message}');
      return false;
    }

    // Optimistically apply locally before refetching, so the UI updates
    // without waiting for the round-trip.
    final current = state.value;
    if (current != null) {
      state = AsyncValue.data(current.copyWith(phone: phone ?? current.phone));
    }

    // Push the new name into auth state so the greeting / More sheet update
    // without a re-login. Then refetch the canonical profile.
    if (name != null) {
      await ref.read(authProvider.notifier).updateUserName(name);
    }
    await refresh();
    return true;
  }
}

final profileProvider = AsyncNotifierProvider<ProfileNotifier, Profile>(
  ProfileNotifier.new,
);
