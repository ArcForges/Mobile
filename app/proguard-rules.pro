# SPDX-License-Identifier: Apache-2.0
# Protobuf-lite uses message fields; Connect's GoogleJavaLiteProtobufStrategy
# calls Internal.getDefaultInstance(Class), which reflects this static method.
# The device gate invokes the minified client against the real Cloud API.
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    <fields>;
    public static ** getDefaultInstance();
}
