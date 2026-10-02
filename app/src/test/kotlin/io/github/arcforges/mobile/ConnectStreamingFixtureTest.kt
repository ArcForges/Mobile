// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import com.connectrpc.Code
import com.connectrpc.ConnectException
import com.connectrpc.Idempotency
import com.connectrpc.MethodSpec
import com.connectrpc.ServerOnlyStreamInterface
import com.connectrpc.StreamType
import com.connectrpc.getOrThrow
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import io.github.arcforges.contracts.hello.v1.HelloServiceClient
import io.github.arcforges.contracts.hello.v1.SayHelloRequest
import io.github.arcforges.contracts.hello.v1.SayHelloResponse
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import java.io.IOException
import java.io.OutputStream
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Server-stream, trailer, cancellation, loss and expiry behavior of the pinned Connect-Kotlin
 * OkHttp/Java-lite transport, using the shipped protocol client configuration against a loopback
 * binary gRPC-Web fixture.
 *
 * This is fixture evidence for the pinned client library, not for any ArcForges service. The
 * published Contracts client contains no server-streaming method (only `HelloService.SayHello` is
 * unary), so the streaming [MethodSpec] reuses the Hello messages under a fixture-only stream type.
 * The fixture speaks HTTP/1.1 on loopback; the deployed ingress is TLS HTTP/2. No Worker,
 * Container, D1, Durable Object, R2, device or emulator is involved.
 */
class ConnectStreamingFixtureTest {
    private class Fixture(val handle: (HttpExchange) -> Unit) : AutoCloseable {
        val calls = AtomicInteger()
        val release = CountDownLatch(1)
        val server: HttpServer =
            HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
                createContext("/") { exchange ->
                    calls.incrementAndGet()
                    try {
                        handle(exchange)
                    } catch (_: IOException) {
                        // The peer vanished: the scenario under test.
                    } finally {
                        try {
                            exchange.close()
                        } catch (_: IOException) {
                            // A deliberately truncated body cannot be closed cleanly.
                        }
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

    private val spec =
        MethodSpec(
            "arcforges.hello.v1.HelloService/SayHello",
            SayHelloRequest::class,
            SayHelloResponse::class,
            StreamType.SERVER,
            Idempotency.UNKNOWN,
        )

    private fun frame(flag: Int, bytes: ByteArray): ByteArray =
        ByteBuffer.allocate(bytes.size + 5).put(flag.toByte()).putInt(bytes.size).put(bytes).array()

    private fun message(text: String): ByteArray =
        frame(0, SayHelloResponse.newBuilder().setMessage(text).build().toByteArray())

    private fun trailers(vararg lines: String): ByteArray =
        frame(128, (lines.joinToString("\r\n") + "\r\n").toByteArray())

    private fun OutputStream.send(bytes: ByteArray) {
        write(bytes)
        flush()
    }

    private fun streamHeaders(exchange: HttpExchange) {
        exchange.requestBody.readAllBytes()
        exchange.responseHeaders.add("Content-Type", "application/grpc-web+proto")
        exchange.sendResponseHeaders(200, 0)
    }

    private class Outcome(val messages: List<String>, val failure: ConnectException?) {
        fun mustFail(): ConnectException = failure ?: error("The stream completed without failure")
    }

    /** Reads until the channel completes, so that frames received before a failure are kept. */
    private suspend fun drain(channel: ReceiveChannel<SayHelloResponse>): Outcome {
        val messages = mutableListOf<String>()
        return try {
            for (item in channel) messages += item.message
            Outcome(messages, null)
        } catch (failure: ConnectException) {
            Outcome(messages, failure)
        }
    }

    private suspend fun open(
        url: String,
        http: OkHttpClient = CloudHelloClient.transport(),
        deadline: Duration = 5.seconds,
    ): ServerOnlyStreamInterface<SayHelloRequest, SayHelloResponse> {
        val stream =
            CloudHelloClient.protocolClient(url, http, deadline).serverStream(emptyMap(), spec)
        stream.sendAndClose(sayHelloRequest { name = "stream" }).getOrThrow()
        return stream
    }

    private fun shutdown(http: OkHttpClient) {
        http.connectionPool.evictAll()
        http.dispatcher.executorService.shutdown()
    }

    @Test
    fun serverStreamDeliversFramesInOrderThenTrailers() = runBlocking {
        Fixture { exchange ->
            assertEquals("POST", exchange.requestMethod)
            assertEquals("/api/arcforges.hello.v1.HelloService/SayHello", exchange.requestURI.path)
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
            assertEquals("stream", SayHelloRequest.parseFrom(bytes.copyOfRange(5, bytes.size)).name)
            exchange.responseHeaders.add("Content-Type", "application/grpc-web+proto")
            exchange.sendResponseHeaders(200, 0)
            exchange.responseBody.send(message("one"))
            exchange.responseBody.send(message("two"))
            exchange.responseBody.send(message("three"))
            exchange.responseBody.send(trailers("grpc-status: 0", "x-proof-cursor: 3"))
        }
            .use { fixture ->
                val http = CloudHelloClient.transport()
                try {
                    val stream = open(fixture.url, http)
                    val outcome = withTimeout(5000) { drain(stream.responseChannel()) }
                    assertEquals(listOf("one", "two", "three"), outcome.messages)
                    assertNull(outcome.failure)
                    val received = withTimeout(5000) { stream.responseTrailers().await() }
                    assertEquals(listOf("3"), received["x-proof-cursor"])
                    assertEquals(listOf("0"), received["grpc-status"])
                    assertEquals(1, fixture.calls.get())
                } finally {
                    shutdown(http)
                }
            }
    }

    @Test
    fun errorTrailerAfterFramesKeepsFramesStatusAndMetadata() = runBlocking {
        for ((status, expected) in
            listOf(
                7 to Code.PERMISSION_DENIED,
                16 to Code.UNAUTHENTICATED,
                9 to Code.FAILED_PRECONDITION,
                5 to Code.NOT_FOUND,
                8 to Code.RESOURCE_EXHAUSTED,
                4 to Code.DEADLINE_EXCEEDED,
                14 to Code.UNAVAILABLE,
            )) {
            Fixture { exchange ->
                streamHeaders(exchange)
                exchange.responseBody.send(message("first"))
                exchange.responseBody.send(
                    trailers(
                        "grpc-status: $status",
                        "grpc-message: refused",
                        "x-proof-scope: stale",
                    )
                )
            }
                .use { fixture ->
                    val http = CloudHelloClient.transport()
                    try {
                        val stream = open(fixture.url, http)
                        val outcome = withTimeout(5000) { drain(stream.responseChannel()) }
                        assertEquals(listOf("first"), outcome.messages)
                        val failure = outcome.mustFail()
                        assertEquals(expected, failure.code)
                        assertEquals("refused", failure.message)
                        assertEquals(listOf("stale"), failure.metadata["x-proof-scope"])
                        assertEquals(1, fixture.calls.get())
                    } finally {
                        shutdown(http)
                    }
                }
        }
    }

    @Test
    fun unaryResponseTrailersCarryMetadata() = runBlocking {
        Fixture { exchange ->
            exchange.requestBody.readAllBytes()
            val body =
                message("Hello, trailers!") + trailers("grpc-status: 0", "x-proof-trailer: kept")
            exchange.responseHeaders.add("Content-Type", "application/grpc-web+proto")
            exchange.sendResponseHeaders(200, body.size.toLong())
            exchange.responseBody.write(body)
        }
            .use { fixture ->
                val http = CloudHelloClient.transport()
                try {
                    val response =
                        HelloServiceClient(
                                CloudHelloClient.protocolClient(fixture.url, http, 5.seconds)
                            )
                            .sayHello(sayHelloRequest { name = "trailers" })
                    assertEquals("Hello, trailers!", response.getOrThrow().message)
                    assertEquals(listOf("kept"), response.trailers["x-proof-trailer"])
                    assertEquals(1, fixture.calls.get())
                } finally {
                    shutdown(http)
                }
            }
    }

    @Test
    fun streamEndedWithoutTrailerFrameLooksCompleteToTheLibrary() = runBlocking {
        Fixture { exchange ->
            streamHeaders(exchange)
            exchange.responseBody.send(message("partial"))
            // The chunked body ends cleanly but the mandatory trailer frame never arrives.
        }
            .use { fixture ->
                val http = CloudHelloClient.transport()
                try {
                    val stream = open(fixture.url, http)
                    val outcome = withTimeout(5000) { drain(stream.responseChannel()) }
                    assertEquals(listOf("partial"), outcome.messages)
                    // Characterization of Connect-Kotlin 0.9.0: no failure is raised and no status
                    // is
                    // reported, so channel completion alone never proves the server finished. The
                    // service's own terminal frame and cursor must decide; revisit on a library
                    // move.
                    assertNull(outcome.failure)
                    val received = withTimeoutOrNull(1000) { stream.responseTrailers().await() }
                    assertNull(received?.get("grpc-status"))
                    assertEquals(1, fixture.calls.get())
                } finally {
                    shutdown(http)
                }
            }
    }

    @Test
    fun connectionLostMidStreamKeepsReceivedFramesAndIsNotReplayed() = runBlocking {
        Fixture { exchange ->
            exchange.requestBody.readAllBytes()
            val first = message("before-loss")
            exchange.responseHeaders.add("Content-Type", "application/grpc-web+proto")
            // Promise more bytes than are sent, then drop the connection.
            exchange.sendResponseHeaders(200, (first.size + 1000).toLong())
            exchange.responseBody.send(first)
            exchange.close()
        }
            .use { fixture ->
                val http = CloudHelloClient.transport()
                try {
                    val stream = open(fixture.url, http)
                    val outcome = withTimeout(5000) { drain(stream.responseChannel()) }
                    assertEquals(listOf("before-loss"), outcome.messages)
                    // Observed mapping of Connect-Kotlin 0.9.0 for a body cut short by connection
                    // loss.
                    assertEquals(Code.UNKNOWN, outcome.mustFail().code)
                    // Observed: the library does not replay the request; a new stream is the
                    // caller's choice.
                    delay(300)
                    assertEquals(1, fixture.calls.get())
                } finally {
                    shutdown(http)
                }
            }
    }

    @Test
    fun deadlineExpiryMidStreamKeepsFramesAndFailsWithDeadlineExceeded() = runBlocking {
        lateinit var fixture: Fixture
        fixture = Fixture { exchange ->
            streamHeaders(exchange)
            exchange.responseBody.send(message("early"))
            fixture.release.await(5, TimeUnit.SECONDS)
        }
        fixture.use {
            val http = CloudHelloClient.transport()
            try {
                val stream = open(fixture.url, http, deadline = 500.milliseconds)
                val outcome = withTimeout(4000) { drain(stream.responseChannel()) }
                assertEquals(listOf("early"), outcome.messages)
                assertEquals(Code.DEADLINE_EXCEEDED, outcome.mustFail().code)
                assertEquals(1, fixture.calls.get())
            } finally {
                shutdown(http)
            }
        }
    }

    @Test
    fun closingTheReceiveSideStopsTheServerAndEndsTheStream() = runBlocking {
        val firstSent = CountDownLatch(1)
        val peerGone = CountDownLatch(1)
        val writes = AtomicInteger()
        Fixture { exchange ->
            streamHeaders(exchange)
            try {
                // Bounded: a client that never cancels fails the assertions, not the build.
                repeat(250) {
                    exchange.responseBody.send(message("tick-$it"))
                    writes.incrementAndGet()
                    firstSent.countDown()
                    Thread.sleep(20)
                }
            } catch (failure: IOException) {
                peerGone.countDown()
                throw failure
            }
        }
            .use { fixture ->
                val http = CloudHelloClient.transport()
                try {
                    val stream = open(fixture.url, http)
                    val first = withTimeout(5000) { stream.responseChannel().receive() }
                    assertEquals("tick-0", first.message)
                    assertTrue(withContext(Dispatchers.IO) { firstSent.await(3, TimeUnit.SECONDS) })
                    stream.receiveClose()
                    assertTrue(
                        "Server must observe the cancellation",
                        withContext(Dispatchers.IO) {
                            peerGone.await(4, TimeUnit.SECONDS)
                        },
                    )
                    assertTrue(stream.isReceiveClosed())
                    assertTrue("Server stopped well before its bound", writes.get() < 250)
                    withTimeout(2000) { while (http.dispatcher.runningCallsCount() != 0) delay(10) }
                    assertEquals(1, fixture.calls.get())
                } finally {
                    shutdown(http)
                }
            }
    }

    @Test
    fun clientCloseCancelsAnOpenStreamWithoutBlockingTheCaller() = runBlocking {
        val started = CountDownLatch(1)
        val peerGone = CountDownLatch(1)
        val closed = AtomicBoolean()
        Fixture { exchange ->
            streamHeaders(exchange)
            try {
                repeat(250) {
                    exchange.responseBody.send(message("tick-$it"))
                    started.countDown()
                    Thread.sleep(20)
                }
            } catch (failure: IOException) {
                closed.set(true)
                peerGone.countDown()
                throw failure
            }
        }
            .use { fixture ->
                val http = CloudHelloClient.transport()
                CloudHelloClient(fixture.url, http).use { client ->
                    val stream =
                        CloudHelloClient.protocolClient(fixture.url, http, 5.seconds)
                            .serverStream(emptyMap(), spec)
                    stream.sendAndClose(sayHelloRequest { name = "stream" }).getOrThrow()
                    assertTrue(withContext(Dispatchers.IO) { started.await(3, TimeUnit.SECONDS) })
                    // Activity destruction path: closes the owned transport off the caller's
                    // thread.
                    client.close()
                    assertTrue(withContext(Dispatchers.IO) { peerGone.await(4, TimeUnit.SECONDS) })
                    assertTrue(closed.get())
                    val outcome = withTimeout(4000) { drain(stream.responseChannel()) }
                    assertEquals(Code.CANCELED, outcome.mustFail().code)
                    assertEquals(1, fixture.calls.get())
                }
            }
    }
}
