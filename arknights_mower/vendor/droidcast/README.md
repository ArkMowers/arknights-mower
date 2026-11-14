# DroidCast 1.3.0

This directory vendors the unmodified debug APK published by
[rayworks/DroidCast](https://github.com/rayworks/DroidCast). Mower uses its
`com.rayworks.droidcast.Main` screenshot helper through `app_process`.

| Field | Verified value |
| --- | --- |
| Artifact | `DroidCast-debug-1.3.0.apk` |
| Package | `com.rayworks.droidcast` |
| APK `versionName` | `1.3.0` |
| APK `versionCode` | `146` |
| Size | 3,977,212 bytes |
| SHA-256 | `29364c603a6c293a07aaa5ba27c1ae2fa0531df91e581682731ddea6e5917e01` |
| Upstream commit | `c779c6609aee1d3deaec68f7efaa6e761414a659` (2026-07-02, “Bump app version to 1.3.0”) |
| License | Apache-2.0; unmodified upstream text in [`LICENSE`](LICENSE) |
| Retrieved | 2026-09-27 |

The upstream publishes this APK in its source repository, without a 1.3.0
release or tag. The pinned sources are:

- [APK download](https://raw.githubusercontent.com/rayworks/DroidCast/c779c6609aee1d3deaec68f7efaa6e761414a659/apk/DroidCast-debug-1.3.0.apk)
- [Upstream checksum](https://github.com/rayworks/DroidCast/blob/c779c6609aee1d3deaec68f7efaa6e761414a659/apk/checksum256.txt), copied verbatim to [`checksum256.txt`](checksum256.txt)
- [License](https://github.com/rayworks/DroidCast/blob/c779c6609aee1d3deaec68f7efaa6e761414a659/LICENSE)
- [Build configuration](https://github.com/rayworks/DroidCast/blob/c779c6609aee1d3deaec68f7efaa6e761414a659/app/build.gradle)
- [Helper entry point and HTTP protocol](https://github.com/rayworks/DroidCast/blob/c779c6609aee1d3deaec68f7efaa6e761414a659/app/src/main/java/com/rayworks/droidcast/Main.java)

The downloaded APK's binary `AndroidManifest.xml` was inspected to verify its
package and version, independently of the filename and build configuration.
The local SHA-256 matches the pinned upstream checksum. This checksum identifies
the vendored bytes; it is not an upstream signature attestation.

## Signing and upgrade compatibility

The certificate embedded in `META-INF/CERT.RSA` has subject
`C=US,O=Android,CN=Android Debug` and SHA-256 fingerprint
`0e8d1a5d5d08fe60fc39b39a0ef230a6f3cc6c98dd1fc188788927bf6d4ca77f`.
The previously vendored 1.2.1 APK (`versionCode` 131) contains the same certificate.
These values were extracted from the APKs with Python `zipfile` and
`cryptography.hazmat.primitives.serialization.pkcs7`; this inspection does not
replace Android Package Manager's signature verification during installation.

Mower may replace a compatible installed version with `adb install -r`.
A package signed by somebody else must not be silently uninstalled. If Android
reports a signature conflict, the user must choose whether to retain that package
or explicitly uninstall it before installing this artifact; uninstalling removes
the package's data.

## Helper protocol

Use the installed APK path as `CLASSPATH`, then start
`app_process /system/bin com.rayworks.droidcast.Main --port=<device-port>`.
The port argument must be the first helper argument. The default port is 53516.
`GET /screenshot` returns JPEG by default; `?format=png` requests PNG.

Mower must validate the decoded frame's actual dimensions. The optional upstream
`width` and `height` query parameters change capture dimensions, and the upstream
helper may retry capture at half size when its first capture returns no bitmap.
An HTTP success alone does not establish a valid 1920×1080 frame.

Verify the vendored bytes from the repository root with PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath arknights_mower/vendor/droidcast/DroidCast-debug-1.3.0.apk
```
