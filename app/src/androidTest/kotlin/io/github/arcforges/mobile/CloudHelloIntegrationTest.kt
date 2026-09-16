// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import android.os.Bundle
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import com.connectrpc.Code
import com.connectrpc.ConnectException
import java.io.File
import java.util.Collections
import kotlinx.coroutines.runBlocking
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Readiness polls are separate from RPCs; application requests are never retried. */
internal fun cloudHealth(): JSONObject {
    val http = CloudHelloClient.transport()
    val until = SystemClock.elapsedRealtime() + 60000
    var last = "no response"
    try {
        while (SystemClock.elapsedRealtime() < until) {
            try {
                http
                    .newCall(Request.Builder().url("${CloudHelloClient.BASE_URL}/healthz").build())
                    .execute()
                    .use { response ->
                        last = "HTTP ${response.code}"
                        if (response.isSuccessful) {
                            val health = JSONObject(response.body.string())
                            check(health.getString("service") == "arcforges-cloud")
                            check(health.getBoolean("nativeAot"))
                            check(health.getString("revision").matches(Regex("[0-9a-f]{40}")))
                            check(
                                response.header("x-arcforges-worker-revision") ==
                                    health.getString("revision")
                            )
                            return health
                        }
                    }
            } catch (failure: Exception) {
                last = failure.toString()
            }
            Thread.sleep(3000)
        }
        error("Cloud readiness failed: $last")
    } finally {
        http.connectionPool.evictAll()
        http.dispatcher.executorService.shutdown()
    }
}

class CloudHelloIntegrationTest {
    @Test
    fun androidSdkCallsDeployedAotThroughWorker() = runBlocking {
        val health = cloudHealth()
        val requests = Collections.synchronizedList(mutableListOf<JSONObject>())
        var forcedTimeout: String? = null
        val transport =
            CloudHelloClient.transport()
                .newBuilder()
                .addInterceptor { chain ->
                    val original = chain.request()
                    check(original.method == "POST")
                    check(
                        original.url.toString() ==
                            "${CloudHelloClient.BASE_URL}/arcforges.hello.v1.HelloService/SayHello"
                    )
                    check(original.body!!.contentType().toString() == "application/grpc-web+proto")
                    check(original.header("grpc-timeout")!!.matches(Regex("[0-9]{1,8}[HMSmun]")))
                    val outgoing =
                        forcedTimeout?.let {
                            original.newBuilder().header("grpc-timeout", it).build()
                        } ?: original
                    chain.proceed(outgoing).also { response ->
                        check(response.code == 200)
                        val type =
                            response.header("Content-Type")!!.substringBefore(';').lowercase()
                        check(type in listOf("application/grpc-web", "application/grpc-web+proto"))
                        if (forcedTimeout == null)
                            check(
                                response.header("x-arcforges-worker-revision") ==
                                    health.getString("revision")
                            )
                        requests.add(
                            JSONObject()
                                .put("url", outgoing.url.toString())
                                .put("requestContentType", outgoing.body!!.contentType().toString())
                                .put("sdkTimeout", original.header("grpc-timeout"))
                                .put("wireTimeout", outgoing.header("grpc-timeout"))
                                .put("responseContentType", type)
                                .put("httpStatus", response.code)
                        )
                    }
                }
                .build()
        val codes = mutableListOf<String>()
        CloudHelloClient(http = transport).use { client ->
            for (name in listOf("Android", "世界 👋", " \t ", "x".repeat(256))) {
                assertEquals("Hello, $name!", client.sayHello(name))
                codes.add("OK")
            }
            suspend fun failure(name: String, expected: Code) {
                try {
                    client.sayHello(name)
                    error("Expected $expected")
                } catch (error: ConnectException) {
                    assertEquals(expected, error.code)
                    codes.add(error.code.name)
                }
            }
            failure("", Code.INVALID_ARGUMENT)
            failure("x".repeat(257), Code.RESOURCE_EXHAUSTED)
            forcedTimeout = "0m"
            failure("Expired", Code.DEADLINE_EXCEEDED)
            forcedTimeout = "invalid"
            failure("Malformed", Code.INVALID_ARGUMENT)
        }
        assertEquals(8, requests.size)
        assertTrue(health.getBoolean("nativeAot"))
        val evidence =
            JSONObject()
                .put("contractsVersion", BuildConfig.CONTRACTS_VERSION)
                .put("health", health)
                .put("requests", JSONArray(requests))
                .put("grpcCodes", JSONArray(codes))
                .put("deviceSdk", android.os.Build.VERSION.SDK_INT)
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        File(instrumentation.targetContext.filesDir, "cloud-hello-evidence.json")
            .writeText(evidence.toString(2))
        instrumentation.sendStatus(
            0,
            Bundle().apply {
                putString(
                    "stream",
                    "\nCLOUD_HELLO_VERIFIED ${health.getString("revision")} Contracts ${BuildConfig.CONTRACTS_VERSION}\n",
                )
            },
        )
    }
}
