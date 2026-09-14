# Security policy

This repository is an Android Hello World bootstrap. Security fixes target `main` and the newest published Android build. It does not implement ArcChat authentication, account storage or production services yet.

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/ArcForges/Mobile/security/advisories/new). Include the affected commit/version, reproduction steps and impact. Do not include production credentials, signing keys or personal data in public issues.

Android release signing credentials are stored in the `android-release` GitHub environment, restricted to `main`. Pull request jobs do not receive those credentials. Dependency review, secret scanning, CodeQL, lockfiles and dependency checksum verification supplement tests; they are not evidence that the complete future product has been audited.

If a release key is exposed, notify maintainers privately before distributing another update. Preserve the existing application signing identity unless an Android signing-key rotation has been deliberately prepared and tested. An unrelated new certificate cannot update existing installations.
