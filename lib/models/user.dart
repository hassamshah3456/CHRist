class AppUser {
  final String id;
  final String name;
  final String email;
  final String upiAddress;
  final String? upiName;

  const AppUser({
    required this.id,
    required this.name,
    required this.email,
    required this.upiAddress,
    this.upiName,
  });

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        id: json['id'] as String,
        name: json['name'] as String,
        email: json['email'] as String,
        upiAddress: json['upi_address'] as String? ?? '',
        upiName: json['upi_name'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'email': email,
        'upi_address': upiAddress,
        'upi_name': upiName,
      };
}
