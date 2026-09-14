# SPDX-License-Identifier: Apache-2.0
# Generated protobuf-lite and gRPC runtime rules are supplied by their artifacts.
# Keep the local contract round trip working under R8 without preserving the entire SDK.
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    <fields>;
}
