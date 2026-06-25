/// A single data-collection record.
///
/// Created on-device (possibly offline), stored in local SQLite, and later
/// synced to the server. [synced] is a device-only flag that is never sent.
class Collection {
  final String id; // client-generated UUID
  final String collectorName;
  final bool verbalConsent;
  final int? childAge;
  final String? childSex; // male / female / other
  final String? responder; // father / mother / other
  final String? responderOther; // free text when responder == other
  final double? locationLat;
  final double? locationLng;
  final String? locationAddress;
  final DateTime collectedAt;
  final bool synced;

  const Collection({
    required this.id,
    required this.collectorName,
    required this.verbalConsent,
    this.childAge,
    this.childSex,
    this.responder,
    this.responderOther,
    this.locationLat,
    this.locationLng,
    this.locationAddress,
    required this.collectedAt,
    this.synced = false,
  });

  Collection copyWith({bool? synced}) => Collection(
        id: id,
        collectorName: collectorName,
        verbalConsent: verbalConsent,
        childAge: childAge,
        childSex: childSex,
        responder: responder,
        responderOther: responderOther,
        locationLat: locationLat,
        locationLng: locationLng,
        locationAddress: locationAddress,
        collectedAt: collectedAt,
        synced: synced ?? this.synced,
      );

  /// For the sync request body sent to the server.
  Map<String, dynamic> toApiJson() => {
        'id': id,
        'verbal_consent': verbalConsent,
        'child_age': childAge,
        'child_sex': childSex,
        'responder': responder,
        'responder_other': responderOther,
        'location_lat': locationLat,
        'location_lng': locationLng,
        'location_address': locationAddress,
        'collected_at': collectedAt.toUtc().toIso8601String(),
      };

  /// For local SQLite (booleans stored as 0/1).
  Map<String, dynamic> toDbMap() => {
        'id': id,
        'collector_name': collectorName,
        'verbal_consent': verbalConsent ? 1 : 0,
        'child_age': childAge,
        'child_sex': childSex,
        'responder': responder,
        'responder_other': responderOther,
        'location_lat': locationLat,
        'location_lng': locationLng,
        'location_address': locationAddress,
        'collected_at': collectedAt.toIso8601String(),
        'synced': synced ? 1 : 0,
      };

  factory Collection.fromDbMap(Map<String, dynamic> m) => Collection(
        id: m['id'] as String,
        collectorName: m['collector_name'] as String? ?? '',
        verbalConsent: (m['verbal_consent'] as int? ?? 0) == 1,
        childAge: m['child_age'] as int?,
        childSex: m['child_sex'] as String?,
        responder: m['responder'] as String?,
        responderOther: m['responder_other'] as String?,
        locationLat: (m['location_lat'] as num?)?.toDouble(),
        locationLng: (m['location_lng'] as num?)?.toDouble(),
        locationAddress: m['location_address'] as String?,
        collectedAt: DateTime.parse(m['collected_at'] as String),
        synced: (m['synced'] as int? ?? 0) == 1,
      );

  /// Records returned by the server are always considered synced.
  factory Collection.fromApiJson(Map<String, dynamic> j) => Collection(
        id: j['id'] as String,
        collectorName: j['collector_name'] as String? ?? '',
        verbalConsent: j['verbal_consent'] as bool? ?? false,
        childAge: j['child_age'] as int?,
        childSex: j['child_sex'] as String?,
        responder: j['responder'] as String?,
        responderOther: j['responder_other'] as String?,
        locationLat: (j['location_lat'] as num?)?.toDouble(),
        locationLng: (j['location_lng'] as num?)?.toDouble(),
        locationAddress: j['location_address'] as String?,
        collectedAt: DateTime.parse(j['collected_at'] as String).toLocal(),
        synced: true,
      );
}
