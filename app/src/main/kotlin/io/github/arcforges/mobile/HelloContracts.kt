// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import io.github.arcforges.contracts.hello.v1.HelloServiceGrpcKt
import io.github.arcforges.contracts.hello.v1.SayHelloRequest
import io.github.arcforges.contracts.hello.v1.SayHelloResponse
import io.github.arcforges.contracts.hello.v1.sayHelloRequest
import io.github.arcforges.mobile.shared.hello
import io.grpc.Channel
import java.util.concurrent.TimeUnit

/** Offline sample using the published protobuf types, including the minified Android runtime. */
internal fun localContractGreeting(name: String): String {
    val request = sayHelloRequest { this.name = name }
    val decoded = SayHelloRequest.parseFrom(request.toByteArray())
    val response = SayHelloResponse.newBuilder().setMessage(hello(decoded.name)).build()
    return SayHelloResponse.parseFrom(response.toByteArray()).message
}

/** Native gRPC adapter. The caller owns the channel and supplies its TLS endpoint and lifecycle. */
internal class HelloClient(channel: Channel) {
    private val stub = HelloServiceGrpcKt.HelloServiceCoroutineStub(channel)

    suspend fun sayHello(name: String): String =
        stub
            .withDeadlineAfter(5, TimeUnit.SECONDS)
            .sayHello(sayHelloRequest { this.name = name })
            .message
}
