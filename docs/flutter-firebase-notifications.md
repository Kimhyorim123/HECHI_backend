# Flutter Firebase Notifications

## 1. 패키지

`pubspec.yaml`

```yaml
firebase_core: ^3.0.0
firebase_messaging: ^15.0.0
flutter_local_notifications: ^17.0.0
```

## 2. 초기화 흐름

```dart
Future<void> bootstrapNotifications() async {
  await Firebase.initializeApp();

  final messaging = FirebaseMessaging.instance;
  await messaging.requestPermission(
    alert: true,
    badge: true,
    sound: true,
    provisional: false,
  );

  final token = await messaging.getToken();
  if (token != null) {
    await registerFcmToken(token);
  }

  FirebaseMessaging.instance.onTokenRefresh.listen((token) async {
    await registerFcmToken(token);
  });
}
```

## 3. 백엔드 토큰 등록

```dart
Future<void> registerFcmToken(String token) async {
  final accessToken = await authRepository.accessToken;

  await dio.post(
    '/notifications/register-token',
    data: {
      'fcmToken': token,
    },
    options: Options(
      headers: {
        'Authorization': 'Bearer $accessToken',
      },
    ),
  );
}
```

## 4. 알림함 연동

### 일반 탭

```dart
GET /users/me/notifications?tabCategory=GENERAL&limit=20&offset=0
```

### 그룹 탭

```dart
GET /users/me/notifications?tabCategory=GROUP&limit=20&offset=0
```

### 안 읽은 개수

```dart
GET /users/me/notifications/unread-count
```

### 단건 읽음

```dart
PATCH /notifications/{notificationId}/read
```

### 전체 읽음

```dart
PATCH /notifications/read-all
```

### 단건 삭제

```dart
DELETE /notifications/{notificationId}
```

### 전체 삭제

```dart
DELETE /notifications/all
```

## 5. 클릭 라우팅 예시

```dart
void routeFromNotification(Map<String, dynamic> targetInfo, String type) {
  switch (type) {
    case 'BOOK_RECOMMEND':
      context.go('/books/${targetInfo['bookId']}');
      break;
    case 'GROUP_ANNOUNCEMENT':
    case 'SOCIAL_COMMENT':
    case 'SOCIAL_LIKE':
      context.go('/groups/${targetInfo['groupId']}/posts/${targetInfo['postId']}');
      break;
    case 'GROUP_MISSION_UPDATE':
      context.go('/groups/${targetInfo['groupId']}');
      break;
    case 'BADGE_EARNED':
      context.go('/my/badges');
      break;
    default:
      context.go('/notifications');
  }
}
```

## 6. 응답에서 바로 쓰는 필드

- `notificationId`
- `tabCategory`
- `type`
- `title`
- `message`
- `thumbnailUrl`
- `isRead`
- `createdAt`
- `targetInfo`
