// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import com.connectrpc.Code
import com.connectrpc.ConnectException
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import io.github.arcforges.contracts.hello.v1.SayHelloRequest
import io.github.arcforges.contracts.hello.v1.SayHelloResponse
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CloudHelloClientTest {
    private class Fixture(val handle: (HttpExchange) -> Unit) : AutoCloseable {
        val calls = AtomicInteger()
        val arrived = CountDownLatch(1)
        val release = CountDownLatch(1)
        val server =
            HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
                createContext("/") { exchange ->
                    calls.incrementAndGet()
                    arrived.countDown()
                    try {
                        handle(exchange)
                    } finally {
                        exchange.close()
                    }
                }
                start()
            }
        val url
            get() = "http://127.0.0.1:${server.address.port}/api"

        override fun close() {
            release.countDown()
            server.stop(0)
        }
    }

    private fun frame(flag: Byte, bytes: ByteArray): ByteArray =
        ByteBuffer.allocate(bytes.size + 5).put(flag).putInt(bytes.size).put(bytes).array()

    private fun reply(exchange: HttpExchange, status: Int, message: String? = null) {
        val data =
            message?.let {
                frame(0, SayHelloResponse.newBuilder().setMessage(it).build().toByteArray())
            } ?: byteArrayOf()
        val body = data + frame(128.toByte(), "grpc-status: $status\r\n".toByteArray())
        // ASP.NET can legitimately omit +proto on its binary protobuf response.
        exchange.responseHeaders.add("Content-Type", "application/grpc-web")
        exchange.sendResponseHeaders(200, body.size.toLong())
        exchange.responseBody.write(body)
    }

    private suspend fun expect(code: Code, operation: suspend () -> Unit) {
        try {
            operation()
            error("Expected $code")
        } catch (failure: ConnectException) {
            assertEquals(code, failure.code)
        }
    }

    @Test
    fun publishedSdkUsesBinaryGrpcWebAndOneApiPrefix() = runBlocking {
        Fixture { exchange ->
            assertEquals("/api/arcforges.hello.v1.HelloService/SayHello", exchange.requestURI.path)
            assertEquals("POST", exchange.requestMethod)
            assertEquals(
                "application/grpc-web+proto",
                exchange.requestHeaders.getFirst("Content-Type"),
            )
            assertTrue(
                exchange.requestHeaders
                    .getFirst("grpc-timeout")
                    .matches(Regex("[0-9]{1,8}[HMSmun]"))
            )
            val bytes = exchange.requestBody.readAllBytes()
            assertEquals(0, bytes[0].toInt())
            assertEquals(bytes.size - 5, ByteBuffer.wrap(bytes, 1, 4).int)
            val name = SayHelloRequest.parseFrom(bytes.copyOfRange(5, bytes.size)).name
            reply(exchange, 0, "Hello, $name!")
        }
            .use { fixture ->
                CloudHelloClient(fixture.url).use { client ->
                    assertEquals("Hello,  世界 👋 !", client.sayHello(" 世界 👋 "))
                }
                assertEquals(1, fixture.calls.get())
            }
    }

    @Test
    fun sdkPreservesApplicationAndHttpErrorsWithoutRetry() = runBlocking {
        for ((status, expected) in
            listOf(
                3 to Code.INVALID_ARGUMENT,
                8 to Code.RESOURCE_EXHAUSTED,
                404 to Code.UNIMPLEMENTED,
            )) {
            Fixture { exchange ->
                exchange.requestBody.readAllBytes()
                if (status == 404) exchange.sendResponseHeaders(404, -1)
                else reply(exchange, status)
            }
                .use { fixture ->
                    CloudHelloClient(fixture.url).use { client ->
                        expect(expected) { client.sayHello("Failure") }
                    }
                    assertEquals(1, fixture.calls.get())
                }
        }
    }

    @Test
    fun deadlineBoundsHeadersAndPartialBodyWithoutRetry() = runBlocking {
        for (partial in listOf(false, true)) {
            lateinit var fixture: Fixture
            fixture = Fixture { exchange ->
                exchange.requestBody.readAllBytes()
                if (partial) {
                    exchange.responseHeaders.add("Content-Type", "application/grpc-web+proto")
                    exchange.sendResponseHeaders(200, 0)
                    exchange.responseBody.write(0)
                    exchange.responseBody.flush()
                }
                fixture.release.await(5, TimeUnit.SECONDS)
            }
            fixture.use {
                CloudHelloClient(fixture.url, deadline = 500.milliseconds).use { client ->
                    withTimeout(3000) {
                        expect(Code.DEADLINE_EXCEEDED) { client.sayHello("Deadline") }
                    }
                }
                assertEquals(1, fixture.calls.get())
            }
        }
    }

    @Test
    fun coroutineCancellationStopsTheHttpCall() = runBlocking {
        lateinit var fixture: Fixture
        fixture = Fixture { exchange ->
            exchange.requestBody.readAllBytes()
            fixture.release.await(5, TimeUnit.SECONDS)
        }
        fixture.use {
            val http = CloudHelloClient.transport()
            CloudHelloClient(fixture.url, http).use { client ->
                val request = launch { client.sayHello("Cancel") }
                assertTrue(
                    withContext(Dispatchers.IO) { fixture.arrived.await(3, TimeUnit.SECONDS) }
                )
                request.cancelAndJoin()
                withTimeout(2000) { while (http.dispatcher.runningCallsCount() != 0) delay(10) }
                assertEquals(1, fixture.calls.get())
            }
        }
    }
}
