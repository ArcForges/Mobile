// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import com.connectrpc.Code
import com.connectrpc.ConnectException
import com.connectrpc.ProtocolClientConfig
import com.connectrpc.ServerOnlyStreamInterface
import com.connectrpc.extensions.GoogleJavaLiteProtobufStrategy
import com.connectrpc.getOrThrow
import com.connectrpc.impl.ProtocolClient
import com.connectrpc.okhttp.ConnectOkHttpClient
import com.connectrpc.protocols.NetworkProtocol
import io.github.arcforges.contracts.hello.v1.HelloServiceClient
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import io.github.arcforges.mobile.shared.GreetingFailure
import java.net.URI
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.CookieJar
import okhttp3.OkHttpClient

/** Activity-owned transport. Recomposition never creates a connection or sends an RPC. */
internal class CloudHelloClient(
    baseUrl: String = BASE_URL,
    private val http: OkHttpClient = transport(),
    private val deadline: Duration = 5.seconds,
) : AutoCloseable {
    private val closed = AtomicBoolean(false)
    private val lifecycle = Any()
    private val activeCalls = mutableSetOf<Job>()

    init {
        val endpoint = URI(baseUrl)
        require(
            endpoint.rawPath == "/api" && endpoint.rawQuery == null && endpoint.rawFragment == null
        )
        require(endpoint.userInfo == null)
        require(!endpoint.host.isNullOrEmpty())
        require(
            endpoint.scheme == "https" ||
                (endpoint.scheme == "http" && endpoint.host == "127.0.0.1")
        )
        require(deadline.isPositive() && deadline <= 5.seconds)
    }

    private val protocol = protocolClient(baseUrl, http, deadline)
    private val service = HelloServiceClient(protocol)

    suspend fun sayHello(name: String): String = ownedCall {
        service.sayHello(sayHelloRequest { this.name = name }).getOrThrow().message
    }

    /**
     * Consume a stream opened by a published generated service client. No production MethodSpec or
     * wire route is invented here. Messages remain delivered when the server later refuses.
     * Completion requires its one canonical successful grpc-status; a clean HTTP EOF alone is never
     * success. Opening, consumption and trailer arrival share the configured RPC deadline.
     */
    suspend fun <Input : Any, Output : Any> consumeGeneratedStream(
        request: Input,
        open: suspend (ProtocolClient) -> ServerOnlyStreamInterface<Input, Output>,
        receive: suspend (Output) -> Unit,
    ): Map<String, List<String>> = ownedCall {
        withTimeoutOrNull(deadline) {
            val stream = open(protocol)
            try {
                stream.sendAndClose(request).getOrThrow()
                for (message in stream.responseChannel()) receive(message)
                val trailers = stream.responseTrailers().await()
                if (trailers["grpc-status"] != listOf("0")) {
                    throw ConnectException(
                        Code.DATA_LOSS,
                        "The stream has no valid completion status",
                    )
                }
                trailers.mapValues { (_, values) -> values.toList() }.toMap()
            } finally {
                // Callback failure and caller/activity cancellation must release the real call.
                withContext(NonCancellable) { stream.receiveClose() }
            }
        } ?: throw ConnectException(Code.DEADLINE_EXCEEDED, "The stream deadline expired")
    }

    private suspend fun <T> ownedCall(action: suspend () -> T): T = coroutineScope {
        val call = checkNotNull(coroutineContext[Job])
        synchronized(lifecycle) {
            if (closed.get()) throw CancellationException("The Cloud transport is closed")
            activeCalls.add(call)
        }
        try {
            action()
        } finally {
            synchronized(lifecycle) { activeCalls.remove(call) }
        }
    }

    suspend fun greet(name: String): String =
        try {
            sayHello(name)
        } catch (failure: ConnectException) {
            throw GreetingFailure(
                when (failure.code) {
                    Code.INVALID_ARGUMENT -> "Cloud rejected this name. Check it and try again."
                    Code.RESOURCE_EXHAUSTED -> "Cloud's request limit was reached. Try again later."
                    Code.DEADLINE_EXCEEDED -> "Cloud did not respond in time. Try again."
                    Code.CANCELED -> "The request was canceled. Try again."
                    else -> "Could not reach Cloud. Check your connection and try again."
                }
            )
        }

    override fun close() {
        val calls =
            synchronized(lifecycle) {
                if (!closed.compareAndSet(false, true)) return
                activeCalls.toList()
            }
        // TLS close_notify can perform I/O. Activity destruction must never close sockets
        // on Android's main thread, or weaken StrictMode to allow it.
        val executor = http.dispatcher.executorService
        executor.execute {
            try {
                calls.forEach { it.cancel(CancellationException("The Cloud transport is closed")) }
                http.dispatcher.cancelAll()
                http.connectionPool.evictAll()
            } finally {
                executor.shutdown()
            }
        }
    }

    companion object {
        const val BASE_URL = "https://arcforges.com/api"

        /**
         * The one protocol client configuration: explicit binary gRPC-Web, the Java-lite message
         * strategy and a fixed deadline. Unary and streaming calls share it, so fixture tests of
         * stream behavior exercise the shipped transport settings.
         */
        fun protocolClient(
            baseUrl: String,
            http: OkHttpClient,
            deadline: Duration,
        ): ProtocolClient =
            ProtocolClient(
                httpClient = ConnectOkHttpClient(http),
                config =
                    ProtocolClientConfig(
                        host = baseUrl,
                        serializationStrategy = GoogleJavaLiteProtobufStrategy(),
                        networkProtocol = NetworkProtocol.GRPC_WEB,
                        ioCoroutineContext = Dispatchers.IO,
                        timeoutOracle = { deadline },
                    ),
            )

        fun transport(): OkHttpClient =
            OkHttpClient.Builder()
                .cookieJar(CookieJar.NO_COOKIES)
                .callTimeout(10, TimeUnit.SECONDS)
                .retryOnConnectionFailure(false)
                .followRedirects(false)
                .followSslRedirects(false)
                .build()
    }
}
