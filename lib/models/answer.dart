/// A collector's answer to one screening question, stored with a collection.
///
/// [photoLocalPath] is the on-device file (offline). [photoFilename] is the
/// server-side name after upload; it stays null until synced.
class CollectionAnswer {
  final String? questionId;
  final String questionCode;
  final String? questionTitle;
  final String? qtype;
  final bool? valueBool;
  final double? valueNumber;
  final String? valueText;
  String? photoLocalPath;
  String? photoFilename;

  CollectionAnswer({
    this.questionId,
    required this.questionCode,
    this.questionTitle,
    this.qtype,
    this.valueBool,
    this.valueNumber,
    this.valueText,
    this.photoLocalPath,
    this.photoFilename,
  });

  /// Sent to the server (only the uploaded filename, never the local path).
  Map<String, dynamic> toApiJson() => {
        'question_id': questionId,
        'question_code': questionCode,
        'question_title': questionTitle,
        'qtype': qtype,
        'value_bool': valueBool,
        'value_number': valueNumber,
        'value_text': valueText,
        'photo_filename': photoFilename,
      };

  /// Persisted locally (keeps the local photo path for offline upload).
  Map<String, dynamic> toJson() => {
        'question_id': questionId,
        'question_code': questionCode,
        'question_title': questionTitle,
        'qtype': qtype,
        'value_bool': valueBool,
        'value_number': valueNumber,
        'value_text': valueText,
        'photo_local_path': photoLocalPath,
        'photo_filename': photoFilename,
      };

  factory CollectionAnswer.fromJson(Map<String, dynamic> j) => CollectionAnswer(
        questionId: j['question_id'] as String?,
        questionCode: j['question_code'] as String? ?? '',
        questionTitle: j['question_title'] as String?,
        qtype: j['qtype'] as String?,
        valueBool: j['value_bool'] as bool?,
        valueNumber: (j['value_number'] as num?)?.toDouble(),
        valueText: j['value_text'] as String?,
        photoLocalPath: j['photo_local_path'] as String?,
        photoFilename: j['photo_filename'] as String?,
      );
}
