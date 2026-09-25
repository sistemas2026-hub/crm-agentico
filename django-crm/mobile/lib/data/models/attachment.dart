/// Backend-side `Attachments` row attached to a parent record via
/// ContentType. The detail endpoints return these as a top-level
/// `attachments` list separate from the parent object.
class Attachment {
  final String id;
  final String fileName;
  final String? filePath;
  final DateTime? createdAt;
  final String? createdBy;

  const Attachment({
    required this.id,
    required this.fileName,
    this.filePath,
    this.createdAt,
    this.createdBy,
  });

  factory Attachment.fromJson(Map<String, dynamic> json) {
    String? createdByEmail;
    final cb = json['created_by'];
    if (cb is Map<String, dynamic>) {
      createdByEmail =
          (cb['email'] as String?) ?? (cb['user_details']?['email'] as String?);
    } else if (cb is String) {
      createdByEmail = cb;
    }
    return Attachment(
      id: json['id']?.toString() ?? '',
      fileName: json['file_name'] as String? ?? 'Attachment',
      filePath: json['file_path'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      createdBy: createdByEmail,
    );
  }
}
