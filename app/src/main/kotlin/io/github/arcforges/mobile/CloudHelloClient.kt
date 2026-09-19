// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import com.connectrpc.Code
import com.connectrpc.ConnectException
import com.connectrpc.ProtocolClientConfig
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
import kotlinx.coroutines.Dispatchers
import okhttp3.CookieJar
import okhttp3.OkHttpClient

/** Activity-owned transport. Recomposition never creates a connection or sends an RPC. */
internal class CloudHelloClient(
    baseUrl: String = BASE_URL,
    private val http: OkHttpClient = transport(),
    deadline: Duration = 5.seconds,
) : AutoCloseable {
    private val closed = AtomicBoolean(false)

    init {
        val endpoint = URI(baseUrl)
        require(
            endpoint.rawPath == "/api" && endpoint.rawQuery == null && endpoint.rawFragment == null
        )
        require(endpoint.userInfo == null)
        require(
            endpoint.scheme == "https" ||
                (endpoint.scheme == "http" && endpoint.host == "127.0.0.1")
        )
        require(deadline.isPositive() && deadline <= 5.seconds)
    }

    private val service =
        HelloServiceClient(
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
        )

    suspend fun sayHello(name: String): String =
        service.sayHello(sayHelloRequest { this.name = name }).getOrThrow().message

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
        if (!closed.compareAndSet(false, true)) return
        // TLS close_notify can perform I/O. Activity destruction must never close sockets
        // on Android's main thread, or weaken StrictMode to allow it.
        val executor = http.dispatcher.executorService
        executor.execute {
            try {
                http.dispatcher.cancelAll()
                http.connectionPool.evictAll()
            } finally {
                executor.shutdown()
            }
        }
    }

    companion object {
        const val BASE_URL = "https://arcforges.com/api"

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
